"""Checks run before anything irreversible happens.

Every check here exists because its failure mode is *quiet*: the run completes,
the PDFs look plausible, and the mistake only surfaces at the bank, in a
member's inbox, or not at all. Loud failures do not need a validator.

All checks are defensive about missing columns - a Faktura export with a
renamed column should produce a finding, not a traceback - and all are pure
functions over DataFrames so they can be tested without Qt or Office.
"""

import datetime as dt
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

import numpy as np
import pandas as pd

from i18n import tr
from selection import document_id, document_ids

ERROR = "error"      # will produce a wrong result or be rejected downstream
WARNING = "warning"  # probably wrong, worth a look
INFO = "info"        # worth knowing

SEVERITY_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}


class Finding:
    """One problem, with what it affects.

    ``rows`` is what the findings list shows. ``names`` (recipient names) and
    ``documents`` (document number -> short text) say which invoices it
    concerns, so the review can show it against each document.
    """
    __slots__ = ("severity", "category", "message", "rows", "names", "documents")

    def __init__(self, severity, category, message, rows=(), names=(), documents=None):
        self.severity = severity
        self.category = category
        self.message = message
        self.rows = list(rows)
        self.names = {str(n).strip() for n in names if str(n).strip()}
        self.documents = dict(documents or {})

    def __repr__(self):
        return f"Finding({self.severity}, {self.category!r}, {self.message!r}, {len(self.rows)} rows)"


# --- helpers ---------------------------------------------------------------

def _has(df, *columns):
    return df is not None and all(c in df.columns for c in columns)


def iban_is_valid(iban):
    """ISO 13616 mod-97 check.

    Catches transposed digits, which a length check does not and which the bank
    rejects only after the file has been submitted.
    """
    if iban is None or (isinstance(iban, float) and pd.isna(iban)):
        return False
    cleaned = re.sub(r"\s+", "", str(iban)).upper()
    if not re.fullmatch(r"[A-Z]{2}[0-9A-Z]{13,32}", cleaned):
        return False
    rearranged = cleaned[4:] + cleaned[:4]
    digits = "".join(str(int(ch, 36)) for ch in rearranged)
    return int(digits) % 97 == 1


def quarter_date_range(year, quarter):
    """First and last day of a calendar quarter."""
    year, quarter = int(year), int(quarter)
    first_month = 3 * (quarter - 1) + 1
    start = dt.date(year, first_month, 1)
    if quarter == 4:
        end = dt.date(year, 12, 31)
    else:
        end = dt.date(year, first_month + 3, 1) - dt.timedelta(days=1)
    return start, end


def billing_period(invoice_details):
    """(year, quarter) from the Abrechnung column, e.g. 'Abr_YQ-2025-2'.

    EEG Faktura also runs yearly, half-yearly and monthly billing
    ('Abr_Y-2025', 'Abr_YH-2025-1', 'Abr_YM-2025-11'). Those are not
    quarters, and reading 'Abr_YM-2025-11' as quarter 11 used to crash the
    period check, so anything that is not a quarter gives None.
    """
    if not _has(invoice_details, "Abrechnung") or invoice_details.empty:
        return None
    raw = str(invoice_details["Abrechnung"].iloc[0])
    parts = raw.split("-")
    if len(parts) < 3 or re.search(r"_(Y|YH|YM)$", parts[0]):
        return None
    try:
        year, quarter = int(parts[-2]), int(parts[-1])
    except ValueError:
        return None
    return (year, quarter) if 1 <= quarter <= 4 else None


# --- checks ----------------------------------------------------------------

def check_billing_period_matches_energy(invoice_details, energydata):
    """The invoices and the energy data must describe the same quarter.

    Generating Q2 invoices against Q1 energy data produces charts and kWh
    figures that are wrong but entirely plausible, and nothing downstream
    notices. This is the single most expensive silent mistake available.
    """
    findings = []
    period = billing_period(invoice_details)
    if period is None:
        return [Finding(WARNING, tr("Abrechnungszeitraum"),
                        tr("Der Abrechnungszeitraum konnte nicht aus den Rechnungsdaten gelesen werden."))]
    if energydata is None or energydata.empty:
        return findings
    year, quarter = period
    start, end = quarter_date_range(year, quarter)
    try:
        index = pd.to_datetime(energydata.index)
        data_start, data_end = index.min().date(), index.max().date()
    except Exception:
        return [Finding(WARNING, tr("Energiedaten"),
                        tr("Der Zeitraum der Energiedaten konnte nicht bestimmt werden."))]

    if data_end < start or data_start > end:
        findings.append(Finding(
            ERROR, tr("Abrechnungszeitraum"),
            tr("Die Energiedaten ({from_} - {to}) liegen komplett außerhalb des "
               "Abrechnungsquartals {year} Q{quarter} ({start} - {end}). "
               "Vermutlich wurde die falsche Datei geladen.",
               from_=f"{data_start:%d.%m.%Y}", to=f"{data_end:%d.%m.%Y}",
               year=year, quarter=quarter,
               start=f"{start:%d.%m.%Y}", end=f"{end:%d.%m.%Y}")))
        return findings

    missing_days = (max(0, (data_start - start).days) + max(0, (end - data_end).days))
    if missing_days > 1:
        findings.append(Finding(
            WARNING, tr("Abrechnungszeitraum"),
            tr("Die Energiedaten decken {year} Q{quarter} nicht ganz ab: "
               "vorhanden {from_} - {to}, erwartet {start} - {end}.",
               year=year, quarter=quarter,
               from_=f"{data_start:%d.%m.%Y}", to=f"{data_end:%d.%m.%Y}",
               start=f"{start:%d.%m.%Y}", end=f"{end:%d.%m.%Y}")))
    return findings


def check_names_in_energydata(invoice_details, energydata, resolve_name):
    """Members whose name has no column in the energy export.

    Previously found one at a time, mid-batch, after the run had started.
    """
    if energydata is None or not _has(invoice_details, "Empfänger Name"):
        return []
    unmatched = [name for name in invoice_details["Empfänger Name"].dropna().unique()
                 if resolve_name(energydata, name) is None]
    if not unmatched:
        return []
    return [Finding(
        ERROR, tr("Namen"),
        tr("{n} Name(n) aus den Rechnungsdaten kommen in den Energiedaten nicht vor. "
           "Diese Rechnungen bekommen keine Grafik.", n=len(unmatched)),
        unmatched, names=unmatched)]


def check_ibans(invoice_details):
    """Missing or invalid IBANs - the bank rejects these after submission."""
    if not _has(invoice_details, "Empfänger Konto IBAN", "Empfänger Name"):
        return []
    findings = []
    per_member = invoice_details.groupby("Empfänger Name")["Empfänger Konto IBAN"].first()
    missing = [name for name, iban in per_member.items()
               if iban is None or (isinstance(iban, float) and pd.isna(iban)) or not str(iban).strip()]
    invalid = [f"{name}: {iban}" for name, iban in per_member.items()
               if str(iban).strip() and not pd.isna(iban) and not iban_is_valid(iban)]
    if missing:
        findings.append(Finding(ERROR, tr("IBAN"),
                                tr("{n} Mitglied(er) ohne IBAN.", n=len(missing)), missing,
                                names=missing))
    if invalid:
        findings.append(Finding(ERROR, tr("IBAN"),
                                tr("{n} IBAN(s) mit ungültiger Prüfsumme.", n=len(invalid)), invalid,
                                names=[row.split(":")[0] for row in invalid]))
    return findings


NO_DEBIT = "NONE"     # Einzugsart of members who pay by transfer themselves


def collected_debits(frame, amount_column):
    """The invoices that will really be collected by direct debit.

    Not those with Einzugsart NONE (no mandate - the member pays), and not
    those of members whose credit notes cover them: the SEPA export nets a
    producer's fee against their credit into one transfer, so nothing is
    debited and no mandate is needed.
    """
    if not _has(frame, "Dokumenttyp", "Empfänger Name"):
        return frame.iloc[0:0] if frame is not None else frame
    kind = frame["Dokumenttyp"]
    debits = frame[kind == "Rechnung"]
    if "Empfänger Einzugsart" in frame:
        debits = debits[debits["Empfänger Einzugsart"].astype(str).str.strip().str.upper() != NO_DEBIT]
    if amount_column in frame:
        amounts = pd.to_numeric(frame[amount_column], errors="coerce").fillna(0)
        owed = amounts[kind == "Rechnung"].groupby(frame["Empfänger Name"]).sum()
        credited = amounts[kind.isin(["Gutschrift", "Information"])].groupby(frame["Empfänger Name"]).sum()
        covered = {name for name, debit in owed.items() if credited.get(name, 0) >= debit}
        debits = debits[~debits["Empfänger Name"].isin(covered)]
    return debits


def check_mandates(invoice_details):
    """Direct debits without a mandate reference cannot be collected."""
    if not _has(invoice_details, "Dokumenttyp", "Empfänger Name"):
        return []
    debits = collected_debits(invoice_details, "Pos. Bruttobetrag")
    if debits.empty:
        return []
    findings = []
    for column, label in (("Empfänger Mandatsreferenz", tr("Mandatsreferenz")),
                          ("Empfänger Mandatsausstellung", tr("Mandatsausstellungsdatum"))):
        if column not in debits.columns:
            continue
        per_member = debits.groupby("Empfänger Name")[column].first()
        missing = [name for name, value in per_member.items()
                   if value is None or pd.isna(value) or not str(value).strip()]
        if missing:
            findings.append(Finding(
                ERROR, tr("SEPA-Mandat"),
                tr("{n} Lastschrift(en) ohne {field}. Die Bank weist diese zurück.",
                   n=len(missing), field=label),
                missing, names=missing))
    return findings


def check_duplicate_names(invoice_details):
    """One name with more than one account: usually one person with two
    memberships. Invoices and payments are kept apart per member number and
    account; this only asks the operator to confirm it is intended.
    """
    if not _has(invoice_details, "Empfänger Name", "Empfänger Konto IBAN"):
        return []
    ibans_per_name = invoice_details.groupby("Empfänger Name")["Empfänger Konto IBAN"].nunique()
    clashes = [name for name, count in ibans_per_name.items() if count > 1]
    if not clashes:
        return []
    return [Finding(
        INFO, tr("Doppelte Namen"),
        tr("{n} Name(n) gehören zu mehreren Mitgliedschaften mit eigenem Konto. Sie bekommen "
           "getrennte Rechnungen und Zahlungen - bitte kurz prüfen, ob das stimmt.",
           n=len(clashes)),
        clashes, names=clashes)]


def check_amounts(invoice_details):
    """Zero-value positions, and credits or debits with the wrong sign."""
    if not _has(invoice_details, "Pos. Bruttobetrag", "Empfänger Name"):
        return []
    findings = []
    amounts = pd.to_numeric(invoice_details["Pos. Bruttobetrag"], errors="coerce")
    zero = invoice_details.loc[amounts.fillna(0) == 0, "Empfänger Name"].unique().tolist()
    if zero:
        findings.append(Finding(WARNING, tr("Beträge"),
                                tr("{n} Mitglied(er) mit einer Position von 0,00 €.", n=len(zero)), zero,
                                names=zero))
    unparsable = invoice_details.loc[amounts.isna(), "Empfänger Name"].unique().tolist()
    if unparsable:
        findings.append(Finding(ERROR, tr("Beträge"),
                                tr("{n} Position(en) mit unlesbarem Betrag.", n=len(unparsable)), unparsable,
                                names=unparsable))
    return findings


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def check_email_addresses(masterdata, invoice_details, members_with_invoices):
    """Members due an invoice who cannot be mailed, and addresses used twice."""
    if masterdata is None or invoice_details is None:
        return []
    try:
        recipients = members_with_invoices(masterdata, invoice_details)
    except Exception:
        return []
    if recipients.empty:
        return [Finding(WARNING, tr("Mailadressen"),
                        tr("Zu den geladenen Rechnungen wurde niemand in den Stammdaten gefunden."))]
    findings = []
    missing, invalid = [], []
    for _, row in recipients.iterrows():
        who = f"{row.get('Name 1', '')} {row.get('Name 2', '')}".strip()
        address = row.get("E-Mail")
        if address is None or pd.isna(address) or not str(address).strip():
            missing.append(who)
        elif not EMAIL_RE.match(str(address).strip()):
            invalid.append(f"{who}: {address}")
    if missing:
        findings.append(Finding(WARNING, tr("Mailadressen"),
                                tr("{n} Mitglied(er) mit Rechnung haben keine Mailadresse.", n=len(missing)),
                                missing, names=missing))
    if invalid:
        findings.append(Finding(ERROR, tr("Mailadressen"),
                                tr("{n} Mailadresse(n) sehen nicht wie Adressen aus.", n=len(invalid)),
                                invalid, names=[row.split(":")[0] for row in invalid]))
    addresses = [str(a).strip().lower() for a in recipients["E-Mail"].dropna() if str(a).strip()]
    duplicates = sorted({a for a in addresses if addresses.count(a) > 1})
    if duplicates:
        findings.append(Finding(
            WARNING, tr("Mailadressen"),
            tr("{n} Adresse(n) kommen mehrfach vor - diese Personen bekommen mehrere Mails.",
               n=len(duplicates)), duplicates))
    return findings


def check_community_metadata(masterdata):
    """Fields the invoice and mail templates fill in from the community sheet."""
    required = ["Bezeichnung", "Straße", "StraßenNr.", "PLZ", "Wohnort", "E-Mail",
                "Web Seite", "IBAN"]
    if masterdata is None or not getattr(masterdata, "metadata", None):
        return []
    missing = [key for key in required
               if not str(masterdata.metadata.get(key, "") or "").strip()]
    if not missing:
        return []
    return [Finding(WARNING, tr("Stammdaten der EEG"),
                    tr("{n} Feld(er) fehlen in den Stammdaten und bleiben auf der Rechnung leer.",
                       n=len(missing)), missing)]


# --- money: what EEG Faktura billed, recomputed --------------------------------
#
# The billing service (eegfaktura-billing, BillingService.createBillingDocumentItem)
# computes every position with BigDecimal and HALF_UP to the cent:
#   kWh     = allocation rounded to 2 places, minus any free kWh
#   net     = kWh x price in cent / 100, rounded; minus the rounded discount
#   VAT     = net x rate, rounded (0 when the tariff has VAT switched off)
#   gross   = net + VAT
# and the allocation is, per metering point and quarter (eegfaktura-web,
# buildAllocationMapFromSelected): consumers - the sum of "Eigendeckung";
# producers - "Gesamte gemeinschaftliche Erzeugung" minus "Überschuss".
# So every euro on an invoice can be re-derived from the export and the
# energy data, and anything that does not re-derive is worth stopping for.

DOCUMENT_TYPES = ("Rechnung", "Gutschrift", "Information")
METER_TYPES = {"Verbraucher": "CONSUMPTION", "Erzeuger": "GENERATION"}
UTILIZATION = "Eigendeckung gemeinschaftliche Erzeugung [KWH]"
PRODUCTION = "Gesamte gemeinschaftliche Erzeugung [KWH]"
SURPLUS = "Gesamt/Überschusserzeugung, Gemeinschaftsüberschuss [KWH]"
METER_RE = re.compile(r"AT[0-9A-Z]{31}")
FREE_KWH_RE = re.compile(r"Verbrauch \(([\d.,]+)\s*kWh\)\s*abzgl\. freie kWh")
CENT = Decimal("0.01")
KWH_TOLERANCE = Decimal("0.011")     # the allocation is rounded to 2 places


def _blank(value):
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _dec(value):
    """Decimal of a number cell (float, int or German-formatted text), or None."""
    if _blank(value):
        return None
    try:
        if isinstance(value, str):
            text = value.strip().replace("€", "").replace(" ", "")
            if "," in text:
                text = text.replace(".", "").replace(",", ".")
            return Decimal(text)
        return Decimal(repr(float(value)))
    except (InvalidOperation, ValueError):
        return None


def _cent(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def format_euro(value):
    """1234.5 -> '1.234,50 €' for messages."""
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} €"


def format_kwh_signed(value):
    return ("+" if value > 0 else "") + format_kwh(value)


def format_kwh(value):
    text = f"{value:,.2f}".replace(",", " ").replace(".", ",").replace(" ", ".")
    return f"{text} kWh"


def document_key(value):
    """Document numbers as text: Excel hands back 1017 as 1017.0."""
    if _blank(value):
        return ""
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def normalise_iban(value):
    return "" if _blank(value) else re.sub(r"\s+", "", str(value)).upper()


def meter_in_text(text):
    found = METER_RE.findall("" if _blank(text) else str(text))
    return found[-1] if found else None


def billed_meters(invoice_details):
    """Metering points named in the position texts."""
    if not _has(invoice_details, "Pos. Text"):
        return set()
    return {m for m in (meter_in_text(t) for t in invoice_details["Pos. Text"]) if m}


def short_meter(meter):
    return f"ZP …{str(meter)[-6:]}"


def _qov_labels(qov):
    """(meter, metercode) -> labels, from a QoV frame laid out as the export's
    "QoV Log": each value column followed by its QoV column."""
    labels = {}
    if qov is None or getattr(qov, "empty", True):
        return labels
    columns = list(qov.columns)
    for i, column in enumerate(columns[:-1]):
        if column[0] != "QoV" and columns[i + 1][0] == "QoV":
            labels.setdefault((column[0], column[-1]), []).append(qov.iloc[:, i + 1])
    return labels


def _holder_columns(energy, meter, recipient):
    """The meter's columns for this recipient.

    A meter that changed hands has one set of columns per holder; pick the
    one named like the invoice recipient, else all of them.
    """
    meters = energy.columns.get_level_values(0)
    if meter not in set(meters):
        return None
    sub = energy.loc[:, meters == meter]
    holders = sub.columns.get_level_values(1)
    if len(set(holders)) > 1:
        wanted = " ".join(str(recipient).split())
        mine = [" ".join(str(h).split()) == wanted for h in holders]
        if any(mine):
            sub = sub.loc[:, mine]
    return sub


def _column_sum(sub, metercode):
    cols = [c for c in sub.columns if c[-1] == metercode]
    if not cols:
        return None
    return float(np.nansum(sub[cols].to_numpy(dtype=float)))


def measured_kwh(sub, direction):
    """What EEG Faktura bills for these columns: utilization or delivered."""
    if direction == "CONSUMPTION":
        return _column_sum(sub, UTILIZATION)
    produced = _column_sum(sub, PRODUCTION)
    surplus = _column_sum(sub, SURPLUS)
    if produced is None:
        return None
    return produced - (surplus or 0.0)


def quality_counts(labels, meter):
    """Quarter-hours with L0, L2 and L3 in any of the meter's columns."""
    series = [s for (m, _), group in labels.items() if m == meter for s in group]
    if not series:
        return None
    frame = pd.concat(series, axis=1)
    return {level: int((frame == level).any(axis=1).sum()) for level in ("L0", "L2", "L3")}


def energy_positions(invoice_details, energy, qov=None):
    """One row per energy position: what was billed, and what the energy data says.

    Columns: Nummer, Name, Dokumenttyp, Meter, Direction, Billed, Expected,
    Diff (kWh, billed minus expected), Impact (gross euro of Diff, approx.),
    and L0/L2/L3 quarter-hour counts (None when no quality data is loaded).
    Expected is None when the energy data has no columns for the meter.
    """
    rows = []
    if not _has(invoice_details, "Pos. Zählpunkttyp", "Pos. Text", "Pos. Menge"):
        return pd.DataFrame(rows)
    labels = _qov_labels(qov)
    for _, pos in invoice_details.iterrows():
        direction = METER_TYPES.get(str(pos.get("Pos. Zählpunkttyp", "")).strip())
        meter = meter_in_text(pos.get("Pos. Text"))
        if direction is None or meter is None:
            continue
        billed = _dec(pos.get("Pos. Menge"))
        text = str(pos.get("Pos. Text", ""))
        free = FREE_KWH_RE.search(text)
        if free:
            # The quantity is net of free kWh; the text keeps the full figure.
            billed = _dec(free.group(1))
        expected = None
        if energy is not None and not energy.empty:
            sub = _holder_columns(energy, meter, pos.get("Empfänger Name", ""))
            if sub is not None:
                value = measured_kwh(sub, direction)
                expected = None if value is None else _cent(Decimal(repr(value)))
        diff = impact = None
        if billed is not None and expected is not None:
            diff = billed - expected
            price = _dec(pos.get("Pos. Preis / Einheit")) or Decimal(0)
            discount = _dec(pos.get("Pos. Rabatt %")) or Decimal(0)
            vat = _dec(pos.get("Pos. UST %")) or Decimal(0)
            if (_dec(pos.get("Pos. UST Betrag")) or Decimal(0)) == 0:
                vat = Decimal(0)
            impact = _cent(diff * price / 100 * (1 - discount / 100) * (1 + vat / 100))
        counts = quality_counts(labels, meter) if labels else None
        rows.append({
            "Nummer": document_id(pos),
            "Name": str(pos.get("Empfänger Name", "")),
            "Dokumenttyp": str(pos.get("Dokumenttyp", "")),
            "Meter": meter, "Direction": direction,
            "Billed": billed, "Expected": expected, "Diff": diff, "Impact": impact,
            "L0": None if counts is None else counts["L0"],
            "L2": None if counts is None else counts["L2"],
            "L3": None if counts is None else counts["L3"],
        })
    return pd.DataFrame(rows)


def check_billed_energy(positions, quality_loaded):
    """Billed kWh against the energy data, and the quality of what was billed.

    A mismatch means the billing run and the energy data disagree: usually
    the grid operator corrected the data after the billing run, sometimes
    the energy data is from another quarter or community. Either way the
    invoice would print one kWh figure in its table and another in its chart.
    """
    if positions is None or positions.empty:
        return []
    findings = []
    missing = positions[positions["Expected"].isna()]
    if not missing.empty:
        findings.append(Finding(
            ERROR, tr("Abgleich kWh"),
            tr("{n} abgerechnete Zählpunkt(e) fehlen in den Energiedaten - die "
               "abgerechneten kWh lassen sich nicht nachprüfen.", n=len(missing)),
            [f"{r.Name}, {short_meter(r.Meter)}" for r in missing.itertuples()],
            documents={r.Nummer: tr("{meter}: keine Energiedaten", meter=short_meter(r.Meter))
                       for r in missing.itertuples()}))
    compared = positions[positions["Diff"].notna()]
    off = compared[[abs(d) > KWH_TOLERANCE for d in compared["Diff"]]]
    if not off.empty:
        total_kwh = sum(off["Diff"], Decimal(0))
        total_eur = sum(off["Impact"], Decimal(0))
        findings.append(Finding(
            ERROR, tr("Abgleich kWh"),
            tr("Bei {n} Position(en) weichen die abgerechneten kWh von den Energiedaten ab "
               "(zusammen {kwh}, rund {eur}). Meist wurden die Daten nach dem "
               "Abrechnungslauf korrigiert: Abrechnung in EEG Faktura neu erstellen, "
               "oder prüfen, ob die richtigen Energiedaten geladen sind.",
               n=len(off), kwh=format_kwh(total_kwh), eur=format_euro(total_eur)),
            [tr("{name}, {meter}: abgerechnet {billed}, Energiedaten {expected} ({diff}, rund {eur})",
                name=r.Name, meter=short_meter(r.Meter), billed=format_kwh(r.Billed),
                expected=format_kwh(r.Expected), diff=format_kwh_signed(r.Diff),
                eur=format_euro(r.Impact))
             for r in off.itertuples()],
            documents={r.Nummer: tr("{meter}: {diff} gegenüber Energiedaten",
                                    meter=short_meter(r.Meter), diff=format_kwh_signed(r.Diff))
                       for r in off.itertuples()}))
    if not quality_loaded:
        findings.append(Finding(
            WARNING, tr("Datenqualität"),
            tr("Keine QoV-Daten geladen - ob die abgerechneten Werte gemessen, ersetzt oder "
               "fehlerhaft sind, wurde nicht geprüft.")))
        return findings
    for level, severity, text in (
            ("L3", ERROR, tr("{n} abgerechnete(r) Zählpunkt(e) haben fehlerhafte Werte (L3) "
                             "im Quartal. Abgerechnet wurde mit diesen Werten.")),
            ("L0", ERROR, tr("{n} abgerechnete(r) Zählpunkt(e) haben Viertelstunden ohne "
                             "Messwert (L0) - die abgerechneten kWh sind unvollständig.")),
            ("L2", INFO, tr("{n} abgerechnete(r) Zählpunkt(e) enthalten Ersatzwerte (L2) "
                            "des Netzbetreibers. Für die Abrechnung zulässig."))):
        hit = positions[[(v or 0) > 0 for v in positions[level]]]
        hit = hit.drop_duplicates(subset=["Meter", "Name"])
        if hit.empty:
            continue
        findings.append(Finding(
            severity, tr("Datenqualität"), text.format(n=len(hit)) if "{n}" in text else text,
            [tr("{name}, {meter}: {count} Viertelstunde(n) {level}", name=r.Name,
                meter=short_meter(r.Meter), count=getattr(r, level), level=level)
             for r in hit.itertuples()],
            documents={r.Nummer: tr("{meter}: {count}× {level}", meter=short_meter(r.Meter),
                                    count=getattr(r, level), level=level)
                       for r in hit.itertuples()} if severity != INFO else None))
    return findings


def check_documents(invoice_list, invoice_details):
    """The two sheets of one export must describe the same documents.

    The SEPA export pays and collects the sum of the Details positions, while
    the screen and the operator see the Liste totals. If they disagree, the
    amount approved is not the amount moved.
    """
    if not _has(invoice_list, "Nummer", "Dokumenttyp") or invoice_details is None:
        return []
    findings = []
    numbers = document_ids(invoice_list)
    if invoice_list["Nummer"].map(lambda x: not document_key(x)).all():
        findings.append(Finding(
            INFO, tr("Dokumente"),
            tr("Vorschau-Export: die Dokumente haben noch keine Rechnungsnummern. Für den "
               "echten Lauf in EEG Faktura »Abrechnung durchführen« und die Excel-Datei "
               "erneut laden.")))
    duplicated = sorted(set(numbers[numbers.duplicated()]))
    if duplicated:
        findings.append(Finding(ERROR, tr("Dokumente"),
                                tr("{n} Dokumentnummer(n) kommen mehrfach vor.", n=len(duplicated)),
                                duplicated, documents={d: tr("Nummer doppelt") for d in duplicated}))
    types = invoice_list["Dokumenttyp"].astype(str)
    unknown = invoice_list[~types.isin(DOCUMENT_TYPES)]
    if not unknown.empty:
        findings.append(Finding(
            ERROR, tr("Dokumente"),
            tr("{n} Dokument(e) mit unbekanntem Typ - der SEPA-Export würde sie übergehen.",
               n=len(unknown)),
            [f"{document_id(r)}: {r['Dokumenttyp']}" for _, r in unknown.iterrows()],
            documents={document_id(r): tr("unbekannter Typ") for _, r in unknown.iterrows()}))
    for frame in (invoice_list, invoice_details):
        if _has(frame, "Abrechnung"):
            periods = sorted(frame["Abrechnung"].dropna().astype(str).unique())
            if len(periods) > 1:
                findings.append(Finding(
                    ERROR, tr("Abrechnungszeitraum"),
                    tr("Die Rechnungsdaten enthalten mehrere Abrechnungszeiträume."), periods))
                break
    if _has(invoice_list, "Rechnungsbetrag Brutto"):
        negative = invoice_list[[(_dec(v) or Decimal(0)) < 0
                                 for v in invoice_list["Rechnungsbetrag Brutto"]]]
        if not negative.empty:
            findings.append(Finding(
                ERROR, tr("Beträge"),
                tr("{n} Dokument(e) mit negativem Betrag.", n=len(negative)),
                list(document_ids(negative)),
                documents={d: tr("negativer Betrag") for d in document_ids(negative)}))

    if not _has(invoice_details, "Nummer", "Pos. Bruttobetrag"):
        return findings
    positions = invoice_details.assign(_key=document_ids(invoice_details))
    in_list, in_details = set(numbers), set(positions["_key"])
    without_positions = sorted(in_list - in_details)
    orphans = sorted(in_details - in_list)
    if without_positions:
        findings.append(Finding(ERROR, tr("Dokumente"),
                                tr("{n} Dokument(e) ohne Positionen in den Details.",
                                   n=len(without_positions)), without_positions,
                                documents={d: tr("keine Positionen") for d in without_positions}))
    if orphans:
        findings.append(Finding(ERROR, tr("Dokumente"),
                                tr("{n} Dokumentnummer(n) nur in den Details, nicht in der Liste.",
                                   n=len(orphans)), orphans))
    sums = {}
    for key, group in positions.groupby("_key"):
        gross = [_dec(v) for v in group["Pos. Bruttobetrag"]]
        net = [_dec(v) for v in group["Pos. Nettobetrag"]] if "Pos. Nettobetrag" in group else []
        if None in gross or None in net:
            continue                        # check_amounts reports unreadable cells
        sums[key] = (sum(gross, Decimal(0)), sum(net, Decimal(0)) if net else None)
    mismatched, rows = {}, []
    for _, doc in invoice_list.iterrows():
        key = document_id(doc)
        if key not in sums:
            continue
        for column, value in (("Rechnungsbetrag Brutto", sums[key][0]),
                              ("Rechnungsbetrag Netto", sums[key][1])):
            stated = _dec(doc.get(column)) if column in invoice_list else None
            if stated is None or value is None:
                continue
            if _cent(stated) != _cent(value):
                mismatched[key] = tr("Summe der Positionen {sum} ≠ Dokument {stated}",
                                     sum=format_euro(value), stated=format_euro(stated))
                rows.append(tr("{number} ({name}): {column} {stated}, Positionen ergeben {sum}",
                               number=key, name=doc.get("Empfänger Name", ""), column=column,
                               stated=format_euro(stated), sum=format_euro(value)))
    if mismatched:
        findings.append(Finding(
            ERROR, tr("Beträge"),
            tr("Bei {n} Dokument(en) ergeben die Positionen nicht den Dokumentbetrag. "
               "Angezeigt wird der Dokumentbetrag, bewegt würde die Summe der Positionen.",
               n=len(mismatched)), rows, documents=mismatched))
    return findings


def check_position_arithmetic(invoice_details):
    """Every position must re-derive from quantity, price, discount and VAT.

    The billing service computes these exactly; a position that does not
    re-derive was edited after export or misread on the way in.
    """
    needed = ("Pos. Nettobetrag", "Pos. Bruttobetrag", "Pos. Preis / Einheit")
    if not _has(invoice_details, *needed):
        return []
    wrong, rows = {}, []
    for _, pos in invoice_details.iterrows():
        price = _dec(pos.get("Pos. Preis / Einheit"))
        net, gross = _dec(pos.get("Pos. Nettobetrag")), _dec(pos.get("Pos. Bruttobetrag"))
        if price is None or net is None or gross is None:
            continue
        discount = _dec(pos.get("Pos. Rabatt %")) or Decimal(0)
        vat_rate = _dec(pos.get("Pos. UST %")) or Decimal(0)
        vat = _dec(pos.get("Pos. UST Betrag")) or Decimal(0)
        if str(pos.get("Pos. Preis / Einheit Euro/Cent", "")).strip() == "Ct":
            quantity = _dec(pos.get("Pos. Menge"))
            if quantity is None:
                continue
            base = _cent(quantity * price / 100)
        else:
            base = price                    # fees: a price in euro, no quantity
        expected_net = base - _cent(base * discount / 100)
        expected_vat = _cent(expected_net * vat_rate / 100)
        problems = []
        if _cent(net) != expected_net:
            problems.append(tr("netto {stated} statt {expected}", stated=format_euro(net),
                               expected=format_euro(expected_net)))
        if _cent(vat) not in (expected_vat, Decimal("0.00")):
            problems.append(tr("USt {stated} statt {expected}", stated=format_euro(vat),
                               expected=format_euro(expected_vat)))
        if _cent(gross) != _cent(net + vat):
            problems.append(tr("brutto {stated} statt {expected}", stated=format_euro(gross),
                               expected=format_euro(net + vat)))
        if problems:
            key = document_id(pos)
            wrong[key] = "; ".join(problems)
            rows.append(f"{key} ({pos.get('Empfänger Name', '')}): " + "; ".join(problems))
    if not wrong:
        return []
    return [Finding(ERROR, tr("Beträge"),
                    tr("{n} Position(en) ergeben sich nicht aus Menge, Preis, Rabatt und USt. "
                       "Wurde die Datei nach dem Export bearbeitet?", n=len(rows)),
                    rows, documents=wrong)]


def check_same_community(invoice_list, invoice_details, members, community_meta, energy):
    """Invoices, member list and energy data must all be one community's.

    With two communities run from the same machine, loading GEA H32's member
    list next to GWE Innsbruck's invoices is an easy mistake, and every later
    step would carry it through.
    """
    findings = []
    stated = normalise_iban((community_meta or {}).get("IBAN"))
    if _has(invoice_list, "Ersteller IBAN"):
        creditors = {normalise_iban(v) for v in invoice_list["Ersteller IBAN"].dropna()} - {""}
        if len(creditors) > 1:
            findings.append(Finding(ERROR, tr("Gemeinschaft"),
                                    tr("Die Rechnungsdaten stammen von mehr als einem Konto der "
                                       "Gemeinschaft."), sorted(creditors)))
        elif creditors and stated and stated not in creditors:
            findings.append(Finding(
                ERROR, tr("Gemeinschaft"),
                tr("Die Rechnungsdaten gehören zu einer anderen Gemeinschaft als die geladenen "
                   "Stammdaten (anderes Gemeinschaftskonto).")))
    if not _has(members, "Zählpunkt"):
        return findings
    known = {str(m).strip() for m in members["Zählpunkt"].dropna()}
    if _has(invoice_details, "Pos. Text"):
        foreign = sorted(billed_meters(invoice_details) - known)
        if foreign:
            findings.append(Finding(
                ERROR, tr("Gemeinschaft"),
                tr("{n} abgerechnete(r) Zählpunkt(e) stehen nicht in den Stammdaten - "
                   "andere Gemeinschaft oder veraltete Stammdaten?", n=len(foreign)),
                [short_meter(m) for m in foreign]))
    if energy is not None and not energy.empty:
        meters = set(energy.columns.get_level_values(0))
        if meters and len(meters & known) < len(meters) / 2:
            findings.append(Finding(
                ERROR, tr("Gemeinschaft"),
                tr("Die meisten Zählpunkte der Energiedaten stehen nicht in den Stammdaten - "
                   "die Energiedaten gehören vermutlich zu einer anderen Gemeinschaft.")))
    return findings


def check_bank_details_current(invoice_list, members):
    """The bank details the billing run used against today's member list.

    The SEPA file uses the account printed on the invoice. A member who
    changed account after the billing run would be debited - or paid - on
    the old one.
    """
    needed = ("Empfänger Mitgliedsnummer", "Empfänger Konto IBAN", "Dokumenttyp")
    if not _has(invoice_list, *needed) or not _has(members, "Mit. Nr.", "IBAN."):
        return []
    def person(first, last):
        return " ".join(f"{'' if _blank(first) else first} {'' if _blank(last) else last}".split()).casefold()

    by_number = {}
    for _, row in members.iterrows():
        by_number.setdefault(document_key(row["Mit. Nr."]), []).append(row)
    shared = sorted(number for number, rows_ in by_number.items()
                    if len({person(r.get("Name 1"), r.get("Name 2")) for r in rows_}) > 1)
    changed, mandate, rows, mandate_rows = {}, {}, [], []
    for _, doc in invoice_list.iterrows():
        if doc["Dokumenttyp"] not in ("Rechnung", "Gutschrift"):
            continue
        candidates = by_number.get(document_key(doc["Empfänger Mitgliedsnummer"]), [])
        # Match the person too: one member number can belong to two people,
        # and comparing against the other one's account is a false alarm.
        wanted = " ".join(str(doc.get("Empfänger Name", "")).split()).casefold()
        member = next((r for r in candidates
                       if person(r.get("Name 1"), r.get("Name 2")) == wanted), None)
        if member is None and len(candidates) == 1:
            member = candidates[0]
        if member is None:
            continue
        key, name = document_id(doc), doc.get("Empfänger Name", "")
        now = normalise_iban(member["IBAN."])
        then = normalise_iban(doc["Empfänger Konto IBAN"])
        if now and then and now != then:
            changed[key] = tr("IBAN seit der Abrechnung geändert")
            rows.append(tr("{name}: Abrechnung …{then}, Stammdaten …{now}",
                           name=name, then=then[-4:], now=now[-4:]))
        if doc["Dokumenttyp"] == "Rechnung" and _has(members, "Mandat-Ref.") \
                and "Empfänger Mandatsreferenz" in invoice_list:
            ref_now = "" if _blank(member["Mandat-Ref."]) else str(member["Mandat-Ref."]).strip()
            ref_then = ("" if _blank(doc["Empfänger Mandatsreferenz"])
                        else str(doc["Empfänger Mandatsreferenz"]).strip())
            if ref_now and ref_then and ref_now != ref_then:
                mandate[key] = tr("Mandat seit der Abrechnung geändert")
                mandate_rows.append(tr("{name}: {then} → {now}", name=name,
                                       then=ref_then, now=ref_now))
    findings = []
    if shared:
        findings.append(Finding(
            WARNING, tr("Stammdaten"),
            tr("{n} Mitgliedsnummer(n) sind in den Stammdaten mehreren Personen zugeordnet - "
               "bitte in EEG Faktura korrigieren.", n=len(shared)), shared))
    if changed:
        findings.append(Finding(
            ERROR, tr("Bankverbindung"),
            tr("{n} Mitglied(er) haben seit dem Abrechnungslauf eine andere IBAN. "
               "Der SEPA-Export würde das alte Konto verwenden.", n=len(changed)),
            rows, documents=changed))
    if mandate:
        findings.append(Finding(
            WARNING, tr("SEPA-Mandat"),
            tr("{n} Mandatsreferenz(en) haben sich seit dem Abrechnungslauf geändert.",
               n=len(mandate)), mandate_rows, documents=mandate))
    return findings


def check_sepa_prerequisites(invoice_list, today=None):
    """What the bank needs before it will collect: a signed mandate and a
    creditor id on every debit, and a valid account of our own."""
    if not _has(invoice_list, "Dokumenttyp"):
        return []
    today = today or dt.date.today()
    debits = collected_debits(invoice_list, "Rechnungsbetrag Brutto")
    findings = []
    if "Empfänger Einzugsart" in invoice_list:
        self_pay = invoice_list[(invoice_list["Dokumenttyp"] == "Rechnung")
                                & (invoice_list["Empfänger Einzugsart"].astype(str).str.strip()
                                   .str.upper() == NO_DEBIT)]
        if not self_pay.empty:
            findings.append(Finding(
                INFO, tr("SEPA-Mandat"),
                tr("{n} Rechnung(en) mit Einzugsart NONE werden nicht eingezogen - diese "
                   "Mitglieder überweisen selbst (ihre Rechnung sagt das).", n=len(self_pay)),
                list(self_pay["Empfänger Name"].astype(str)),
                documents={document_id(r): tr("überweist selbst") for _, r in self_pay.iterrows()}))
    if "Empfänger Mandatsausstellung" in debits:
        future = {}
        for _, doc in debits.iterrows():
            signed = pd.to_datetime(doc["Empfänger Mandatsausstellung"], errors="coerce",
                                    dayfirst=True)
            if not pd.isna(signed) and signed.date() > today:
                future[document_id(doc)] = tr("Mandat erst ab {date}",
                                                             date=f"{signed:%d.%m.%Y}")
        if future:
            findings.append(Finding(
                ERROR, tr("SEPA-Mandat"),
                tr("{n} Lastschrift(en) mit einem Mandat, das erst in der Zukunft ausgestellt "
                   "wird.", n=len(future)), list(future.values()), documents=future))
    if not debits.empty and "Ersteller Creditor Id" in debits:
        if debits["Ersteller Creditor Id"].map(_blank).any():
            findings.append(Finding(ERROR, tr("SEPA-Mandat"),
                                    tr("Die Creditor-ID der Gemeinschaft fehlt - ohne sie "
                                       "nimmt die Bank keine Lastschrift an.")))
    if "Ersteller IBAN" in invoice_list:
        own = {str(v) for v in invoice_list["Ersteller IBAN"].dropna()}
        bad = sorted(v for v in own if not iban_is_valid(v))
        if bad:
            findings.append(Finding(ERROR, tr("IBAN"),
                                    tr("Das Konto der Gemeinschaft hat eine ungültige IBAN."), bad))
    information = invoice_list[invoice_list["Dokumenttyp"] == "Information"]
    if not information.empty:
        findings.append(Finding(
            INFO, tr("Dokumente"),
            tr("{n} Informations-Dokument(e) werden im SEPA-Export wie Gutschriften "
               "überwiesen.", n=len(information)),
            [str(n) for n in information.get("Empfänger Name", [])],
            names=information.get("Empfänger Name", [])))
    return findings


def check_unbilled_meters(invoice_details, energy, members=None):
    """Metering points with billable energy and no invoice position.

    Can be deliberate (a free tariff produces no position at all), so it is
    a warning - but it is also what a participant left out of the billing
    run looks like.
    """
    if energy is None or energy.empty or not _has(invoice_details, "Pos. Text"):
        return []
    billed = billed_meters(invoice_details)
    rows = []
    for meter in dict.fromkeys(energy.columns.get_level_values(0)):
        if meter in billed:
            continue
        sub = energy.loc[:, energy.columns.get_level_values(0) == meter]
        direction = sub.columns[0][2]
        value = measured_kwh(sub, direction)
        if value is not None and value >= 0.5:
            rows.append(tr("{name}, {meter}: {kwh}", name=sub.columns[0][1],
                           meter=short_meter(meter), kwh=format_kwh(Decimal(repr(value)))))
    if not rows:
        return []
    return [Finding(WARNING, tr("Abgleich kWh"),
                    tr("{n} Zählpunkt(e) haben abrechenbare Energie, aber keine Position in "
                       "den Rechnungsdaten.", n=len(rows)), rows)]


def check_previous_runs(invoice_list, exported=None, mailed=None):
    """Documents that have already been collected or mailed from this computer.

    Exporting the same documents twice collects twice; nothing at the bank
    stops a second upload of a file with new dates.
    """
    if not _has(invoice_list, "Nummer"):
        return []
    findings = []
    for ledger, severity, message in (
            (exported, ERROR, tr("{n} Dokument(e) wurden schon in einen SEPA-Export "
                                 "übernommen. Ein weiterer Export bucht sie ein zweites Mal.")),
            (mailed, WARNING, tr("{n} Dokument(e) wurden schon per Mail verschickt."))):
        if not ledger:
            continue
        hits = {}
        for _, doc in invoice_list.iterrows():
            key = document_id(doc)
            if key in ledger:
                hits[key] = ledger[key]
        if hits:
            label = tr("SEPA-Export am {date}") if ledger is exported else tr("verschickt am {date}")
            findings.append(Finding(
                severity, tr("Frühere Läufe"), message.format(n=len(hits)),
                [f"{key}: {label.format(date=date)}" for key, date in hits.items()],
                documents={key: label.format(date=date) for key, date in hits.items()}))
    return findings


def validate(invoices=None, masterdata=None, energydata=None,
             resolve_name=None, members_with_invoices=None,
             exported=None, mailed=None, today=None):
    """Run every applicable check. Skips anything whose inputs are not loaded.

    ``exported`` and ``mailed`` map document numbers to the date they were
    last exported or mailed from this computer (see ledger.py).
    """
    findings = []
    data = invoices.data if (invoices is not None and invoices.data) else None
    details = data["detailed"] if data else None
    invoice_list = data["list"] if data else None
    energy = energydata.data if energydata is not None else None
    qov = getattr(energydata, "metadata", None) if energydata is not None else None
    master = masterdata.data if masterdata is not None else None
    meta = getattr(masterdata, "metadata", None) if masterdata is not None else None

    if details is not None:
        findings += check_ibans(details)
        findings += check_mandates(details)
        findings += check_duplicate_names(details)
        findings += check_amounts(details)
        findings += check_position_arithmetic(details)
        if invoice_list is not None:
            findings += check_documents(invoice_list, details)
            findings += check_sepa_prerequisites(invoice_list, today=today)
            findings += check_previous_runs(invoice_list, exported, mailed)
            findings += check_bank_details_current(invoice_list, master)
            findings += check_same_community(invoice_list, details, master, meta, energy)
        if energy is not None:
            findings += check_billing_period_matches_energy(details, energy)
            if resolve_name is not None:
                findings += check_names_in_energydata(details, energy, resolve_name)
            findings += check_billed_energy(energy_positions(details, energy, qov),
                                            quality_loaded=qov is not None)
            findings += check_unbilled_meters(details, energy, master)
        if master is not None and members_with_invoices is not None:
            findings += check_email_addresses(master, details, members_with_invoices)
    if masterdata is not None:
        findings += check_community_metadata(masterdata)

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return findings
