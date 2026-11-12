"""Extra invoice positions for energy that never reaches EEG Faktura.

Some members' consumption is measured before the inverter, so part of what
they use never arrives in EEG Faktura. Someone reads that meter each quarter;
the difference to the last reading is billed here, as an extra position on
the member's invoice.

How it stays safe:

* The export from EEG Faktura is never edited. ``apply`` returns a copy with
  one extra Details row per reading and the document's totals in Liste raised
  by the same amounts, so the PDF, the review, the mail and the SEPA debit all
  see the same figures.
* The position copies the member's own consumption position (tariff, price,
  discount, VAT) and is computed with the billing service's rounding, so
  ``validation.check_position_arithmetic`` re-derives it like any other.
* It is marked ``Pos. Zählpunkttyp = Zusatzposition`` and names no metering
  point, so the kWh comparison against the energy data leaves it alone.
* Changing the data changes the fingerprint, which voids an earlier approval;
  every position appears in the review as a warning to be ticked by hand.

Readings are remembered per community (the creditor IBAN) and member in
``extra_positions.json`` next to the ledger, so next quarter's form starts from
this quarter's reading. No Qt in here.
"""

import datetime as dt
import json
import os
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import pandas as pd

import validation as v
from config import user_data_dir
from i18n import tr
from selection import document_id

KIND = "Zusatzposition"            # Pos. Zählpunkttyp of an extra position
CONSUMER = "Verbraucher"
STORE_NAME = "extra_positions.json"
DEFAULT_DESCRIPTION = "Verbrauch vor dem Wechselrichter"
PERIOD_RE = re.compile(r"(\d{4})-(\d)\s*$")


def store_path():
    return os.path.join(user_data_dir(), STORE_NAME)


# --- numbers ---------------------------------------------------------------

def parse_reading(text):
    """A meter reading as typed: 12345 · 12.345 · 12345,6 · 12.345,6 · 12345.6.

    German style first: a dot followed by groups of three digits is a
    thousands separator. Returns a Decimal, or None if it is not a number.
    """
    if text is None:
        return None
    s = str(text).strip().replace(" ", "").replace(" ", "").replace("'", "")
    if not s:
        return None
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    elif re.fullmatch(r"\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        value = Decimal(s)
    except InvalidOperation:
        return None
    return value if value.is_finite() else None


def kwh_between(previous, current):
    """The billed quantity: rounded half-up to 2 places, as EEG Faktura does."""
    return (Decimal(current) - Decimal(previous)).quantize(v.CENT, rounding=ROUND_HALF_UP)


def format_number(value, decimals=2):
    text = f"{Decimal(value):,.{decimals}f}"
    return text.replace(",", "\u0000").replace(".", ",").replace("\u0000", ".")


# --- the record --------------------------------------------------------------

def member_key(number, name):
    """Member number and name: two people can share a number (see selection)."""
    return f"{v.document_key(number)}|{' '.join(str(name).split()).casefold()}"


@dataclass
class Extra:
    member: str                 # Empfänger Mitgliedsnummer as in the export
    name: str                   # Empfänger Name as in the export
    description: str
    previous: Decimal
    current: Decimal
    reason: str
    entered_at: str = ""
    entered_by: str = ""

    @property
    def key(self):
        return member_key(self.member, self.name)

    @property
    def kwh(self):
        return kwh_between(self.previous, self.current)

    def position_text(self):
        return (f"{self.description.strip()} (Zählerstand {format_number(self.previous)} → "
                f"{format_number(self.current)})")


def period_order(period):
    """'Abr_YQ-2026-3' -> (2026, 3); anything else sorts first."""
    match = PERIOD_RE.search(str(period or ""))
    return (int(match.group(1)), int(match.group(2))) if match else (0, 0)


# --- the store -------------------------------------------------------------

def load_store(path=None):
    path = path or store_path()
    try:
        with open(path, encoding="utf-8") as handle:
            store = json.load(handle)
    except FileNotFoundError:
        store = {}
    store.setdefault("version", 1)
    store.setdefault("communities", {})
    return store


def save_store(store, path=None):
    """Written to a temporary file and moved, so a crash cannot truncate it."""
    path = str(path or store_path())
    os.makedirs(os.path.dirname(path), exist_ok=True)
    temporary = path + ".tmp"
    with open(temporary, "w", encoding="utf-8") as handle:
        json.dump(store, handle, ensure_ascii=False, indent=2, sort_keys=True)
    os.replace(temporary, path)


def _members(store, creditor):
    return store["communities"].setdefault(creditor, {})


def entries_for(store, creditor, period):
    """The extras entered for this community and billing period."""
    found = []
    for member in store["communities"].get(creditor, {}).values():
        reading = member.get("readings", {}).get(period)
        if reading:
            found.append(Extra(member=member["member"], name=member["name"],
                               description=reading["description"],
                               previous=Decimal(reading["previous"]),
                               current=Decimal(reading["current"]),
                               reason=reading.get("reason", ""),
                               entered_at=reading.get("entered_at", ""),
                               entered_by=reading.get("entered_by", "")))
    return sorted(found, key=lambda e: e.name.casefold())


def set_entry(store, creditor, period, extra, every_quarter):
    member = _members(store, creditor).setdefault(extra.key, {"readings": {}})
    member.update(member=str(extra.member), name=extra.name, every_quarter=bool(every_quarter),
                  description=extra.description)
    member["readings"][period] = {
        "description": extra.description,
        "previous": str(extra.previous),
        "current": str(extra.current),
        "kwh": str(extra.kwh),
        "reason": extra.reason,
        "entered_at": extra.entered_at or dt.datetime.now().isoformat(timespec="seconds"),
        "entered_by": extra.entered_by,
    }


def remove_entry(store, creditor, period, key):
    member = store["communities"].get(creditor, {}).get(key)
    if member:
        member.get("readings", {}).pop(period, None)


def remembered(store, creditor, key):
    """(description, every_quarter) to start a form with."""
    member = store["communities"].get(creditor, {}).get(key, {})
    return (member.get("description", DEFAULT_DESCRIPTION), member.get("every_quarter", True))


def previous_reading(store, creditor, key, period):
    """The latest reading from a period before this one, or None."""
    member = store["communities"].get(creditor, {}).get(key, {})
    earlier = [(period_order(p), r) for p, r in member.get("readings", {}).items()
               if period_order(p) < period_order(period)]
    if not earlier:
        return None
    return Decimal(max(earlier, key=lambda item: item[0])[1]["current"])


def missing_readings(store, creditor, period):
    """Members marked 'every quarter' who have no reading for this period: (key, name)."""
    return sorted(((key, m["name"]) for key, m in store["communities"].get(creditor, {}).items()
                   if m.get("every_quarter") and period not in m.get("readings", {})),
                  key=lambda item: item[1].casefold())


# --- the invoice data --------------------------------------------------------

def _consumption_rows(details):
    if not v._has(details, "Pos. Zählpunkttyp", "Dokumenttyp"):
        return details.iloc[0:0]
    return details[(details["Pos. Zählpunkttyp"].astype(str).str.strip() == CONSUMER)
                   & (details["Dokumenttyp"].astype(str).str.strip() == "Rechnung")]


def candidates(data):
    """Every member with a consumption position on an invoice in this run.

    Returns {key: {member, name, document, tariff, price, unit, discount,
    vat_rate, vat_applies}} - the tariff an extra position will copy.
    """
    found = {}
    for _, row in _consumption_rows(data["detailed"]).iterrows():
        key = member_key(row.get("Empfänger Mitgliedsnummer"), row.get("Empfänger Name"))
        if key in found:
            continue
        found[key] = {
            "member": str(row.get("Empfänger Mitgliedsnummer")),
            "name": str(row.get("Empfänger Name")),
            "document": document_id(row),
            "tariff": "" if v._blank(row.get("Pos. Tarif")) else str(row.get("Pos. Tarif")),
            "price": v._dec(row.get("Pos. Preis / Einheit")) or Decimal(0),
            "unit": str(row.get("Pos. Preis / Einheit Euro/Cent", "")).strip(),
            "discount": v._dec(row.get("Pos. Rabatt %")) or Decimal(0),
            "vat_rate": v._dec(row.get("Pos. UST %")) or Decimal(0),
            # A position with a rate but no VAT amount (a member not liable to
            # VAT): the extra must not charge VAT either.
            "vat_applies": (v._dec(row.get("Pos. UST Betrag")) or Decimal(0)) != 0
                           or (v._dec(row.get("Pos. UST %")) or Decimal(0)) == 0,
        }
    return found


def amounts(kwh, tariff):
    """(net, vat, gross) of kwh at a member's consumption tariff.

    The billing service's rounding, which check_position_arithmetic repeats:
    the base and the discount each rounded to the cent, then the VAT.
    """
    price = tariff["price"] / 100 if tariff["unit"] == "Ct" else tariff["price"]
    base = v._cent(Decimal(kwh) * price)
    net = base - v._cent(base * tariff["discount"] / 100)
    vat = v._cent(net * tariff["vat_rate"] / 100) if tariff["vat_applies"] else Decimal("0.00")
    return net, vat, net + vat


def _add(value, amount):
    base = v._dec(value) or Decimal(0)
    return float(v._cent(base + amount))


def apply(data, extras):
    """A copy of the invoice data with each extra added to its member's invoice.

    Returns (data, applied, problems): applied is [(extra, document, net, vat,
    gross)], problems is [(extra, text)] for readings that could not be placed.
    """
    invoice_list = data["list"].copy()
    details = data["detailed"].copy()
    tariffs = candidates(data)
    applied, problems = [], []
    for extra in extras:
        tariff = tariffs.get(extra.key)
        if tariff is None:
            problems.append((extra, tr("{name} hat in dieser Abrechnung keine Rechnung mit "
                                       "Verbrauchsposition - die Zusatzposition wurde nicht "
                                       "übernommen.", name=extra.name)))
            continue
        if extra.kwh <= 0:
            problems.append((extra, tr("{name}: der neue Zählerstand ist nicht größer als der "
                                       "alte - nicht übernommen.", name=extra.name)))
            continue
        document = tariff["document"]
        rows = [i for i, (_, r) in enumerate(invoice_list.iterrows()) if document_id(r) == document]
        if not rows:
            problems.append((extra, tr("{name}: Dokument {document} fehlt in der Liste.",
                                       name=extra.name, document=document)))
            continue
        source = _consumption_rows(details)
        source = source[[document_id(r) == document and member_key(
            r.get("Empfänger Mitgliedsnummer"), r.get("Empfänger Name")) == extra.key
            for _, r in source.iterrows()]].iloc[0]
        net, vat, gross = amounts(extra.kwh, tariff)
        position = source.copy()
        position["Pos. Zählpunkttyp"] = KIND
        position["Pos. Text"] = extra.position_text()
        position["Pos. Menge"] = float(extra.kwh)
        position["Pos. Mengeneinheit"] = "kWh"
        position["Pos. Nettobetrag"] = float(net)
        position["Pos. UST Betrag"] = float(vat)
        position["Pos. Bruttobetrag"] = float(gross)
        if not tariff["vat_applies"]:
            position["Pos. UST %"] = source.get("Pos. UST %")
        # After the document's last position, so the PDF lists it last.
        same = [i for i, (_, r) in enumerate(details.iterrows()) if document_id(r) == document]
        at = same[-1] + 1
        details = pd.concat([details.iloc[:at], position.to_frame().T, details.iloc[at:]],
                            ignore_index=True)

        index = invoice_list.index[rows[0]]
        invoice_list.loc[index, "Rechnungsbetrag Netto"] = _add(
            invoice_list.loc[index, "Rechnungsbetrag Netto"], net)
        invoice_list.loc[index, "Rechnungsbetrag Brutto"] = _add(
            invoice_list.loc[index, "Rechnungsbetrag Brutto"], gross)
        if vat:
            rate = float(tariff["vat_rate"])
            for slot in ("1", "2"):
                rate_column, sum_column = f"UST Satz {slot} (%)", f"UST Satz {slot} Summe (Euro)"
                if rate_column not in invoice_list:
                    continue
                current_rate = invoice_list.loc[index, rate_column]
                if v._blank(current_rate) or float(current_rate) == rate:
                    invoice_list.loc[index, rate_column] = rate
                    invoice_list.loc[index, sum_column] = _add(invoice_list.loc[index, sum_column], vat)
                    break
        applied.append((extra, document, net, vat, gross))
    return {**data, "list": invoice_list, "detailed": details}, applied, problems


def findings(applied, problems, missing):
    """What the review shows: each extra as a warning, so it is ticked by hand."""
    found = []
    category = tr("Zusatzposition")
    for extra, document, net, vat, gross in applied:
        text = tr("{description}: Zählerstand {previous} → {current} = {kwh} kWh, "
                  "+{gross} brutto. Grund: {reason}",
                  description=extra.description, previous=format_number(extra.previous),
                  current=format_number(extra.current), kwh=format_number(extra.kwh),
                  gross=v.format_euro(gross), reason=extra.reason or "–")
        found.append(v.Finding(v.WARNING, category, f"{extra.name}: {text}",
                               [f"{document}: {extra.name}"], documents={document: text}))
    for extra, text in problems:
        found.append(v.Finding(v.ERROR, category, text, [extra.name], names=[extra.name]))
    for _, name in missing:
        found.append(v.Finding(
            v.WARNING, category,
            tr("{name}: jedes Quartal ist eine Zusatzposition vorgesehen, für diese Abrechnung "
               "fehlt die Ablesung.", name=name), [name], names=[name]))
    return found
