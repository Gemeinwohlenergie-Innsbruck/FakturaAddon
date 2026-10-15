"""The manual review before anything is charged.

The automatic checks in validation.py find what can be found mechanically.
This puts every document in front of the operator with what was checked
against it - billed kWh next to the energy data, data quality, account,
mandate, mail - and records who approved which data, when, and which errors
they accepted.

An approval belongs to the exact data it was given for: ``fingerprint``
hashes everything loaded, and reloading any file voids it. No Qt in here, so
it can be tested without a display.
"""

import hashlib
import json
from collections import defaultdict
from decimal import Decimal

import pandas as pd

import validation as v
from i18n import tr

OK = "ok"
STATUS_ORDER = {v.ERROR: 0, v.WARNING: 1, v.INFO: 2, OK: 3}

COLUMNS = ["Nummer", "Typ", "Name", "Betrag", "kWh abgerechnet", "kWh Energiedaten",
           "Abweichung kWh", "Qualität", "IBAN", "Mandat", "Mail", "Status", "Hinweise"]


def fingerprint(invoices, masterdata, energydata):
    """A hash of everything the review saw. Any reload changes it."""
    digest = hashlib.sha256()

    def add(frame):
        if frame is None:
            digest.update(b"<none>")
            return
        digest.update(repr(list(frame.columns)).encode("utf-8"))
        digest.update(repr(list(frame.index[:1]) + list(frame.index[-1:])).encode("utf-8"))
        digest.update(pd.util.hash_pandas_object(frame, index=True).values.tobytes())

    data = getattr(invoices, "data", None) or {}
    add(data.get("list"))
    add(data.get("detailed"))
    add(getattr(masterdata, "data", None))
    add(getattr(energydata, "data", None))
    add(getattr(energydata, "metadata", None))
    meta = getattr(masterdata, "metadata", None) or {}
    digest.update(json.dumps(meta, sort_keys=True, default=str).encode("utf-8"))
    return digest.hexdigest()


def _name_key(name):
    return " ".join(str(name).split()).casefold()


def _mask_iban(iban):
    cleaned = v.normalise_iban(iban)
    return f"{cleaned[:2]} …{cleaned[-4:]}" if cleaned else tr("fehlt")


def _sum(values):
    values = [x for x in values if x is not None and not (isinstance(x, float) and pd.isna(x))]
    return sum(values, Decimal(0)) if values else None


def _quality(rows):
    if rows.empty:
        return "–"
    if rows["L0"].isna().all():
        return tr("nicht geprüft")
    parts = [f"{level}: {int(rows[level].sum())}" for level in ("L3", "L0", "L2")
             if rows[level].fillna(0).sum() > 0]
    return " · ".join(parts) if parts else tr("ok")


def issues_by_document(invoice_list, findings):
    """Document number -> [(severity, text)], from every finding that concerns it."""
    by_name = defaultdict(list)
    for _, doc in invoice_list.iterrows():
        by_name[_name_key(doc.get("Empfänger Name", ""))].append(v.document_key(doc["Nummer"]))
    issues = defaultdict(list)
    for finding in findings:
        for number, text in finding.documents.items():
            issues[number].append((finding.severity, f"{finding.category}: {text}"))
        for name in finding.names:
            for number in by_name.get(_name_key(name), []):
                if number not in finding.documents:
                    issues[number].append((finding.severity, f"{finding.category}: {finding.message}"))
    return issues


def review_table(invoices, masterdata, energydata, findings):
    """One row per document, in the order of the export's Liste."""
    data = invoices.data
    invoice_list, details = data["list"], data["detailed"]
    energy = getattr(energydata, "data", None)
    qov = getattr(energydata, "metadata", None)
    positions = v.energy_positions(details, energy, qov) if energy is not None else pd.DataFrame()
    issues = issues_by_document(invoice_list, findings)

    mail_by_member = {}
    members = getattr(masterdata, "data", None)
    if members is not None and "Mit. Nr." in members and "E-Mail" in members:
        for _, row in members.iterrows():
            address = row.get("E-Mail")
            ok = not v._blank(address) and bool(v.EMAIL_RE.match(str(address).strip()))
            mail_by_member.setdefault(v.document_key(row["Mit. Nr."]), ok)

    rows = []
    for _, doc in invoice_list.iterrows():
        number = v.document_key(doc["Nummer"])
        mine = positions[positions["Nummer"] == number] if not positions.empty else positions
        billed = _sum(mine["Billed"]) if not mine.empty else None
        expected = (_sum(mine["Expected"]) if not mine.empty and mine["Expected"].notna().all()
                    else None)
        kind = str(doc.get("Dokumenttyp", ""))
        if kind == "Rechnung":
            has_mandate = not (v._blank(doc.get("Empfänger Mandatsreferenz"))
                               or v._blank(doc.get("Empfänger Mandatsausstellung")))
            mandate = "✓" if has_mandate else "✗"
        else:
            mandate = "–"
        member = v.document_key(doc.get("Empfänger Mitgliedsnummer"))
        mail = {True: "✓", False: "✗"}.get(mail_by_member.get(member), "?")
        found = list(issues.get(number, []))
        if mail == "✗" and not any(text.startswith(tr("Mailadressen")) for _, text in found):
            # Said here as well: the mail check only runs with the selection
            # helper, and a ✗ beside an "ok" would contradict itself.
            found.append((v.WARNING, tr("Mailadressen: keine gültige Adresse in den Stammdaten")))
        found.sort(key=lambda i: STATUS_ORDER.get(i[0], 9))
        rows.append({
            "Nummer": number,
            "Typ": kind,
            "Name": str(doc.get("Empfänger Name", "")),
            "Betrag": v._dec(doc.get("Rechnungsbetrag Brutto")),
            "kWh abgerechnet": billed,
            "kWh Energiedaten": expected,
            "Abweichung kWh": (billed - expected) if billed is not None and expected is not None else None,
            "Qualität": _quality(mine) if not mine.empty else "–",
            "IBAN": _mask_iban(doc.get("Empfänger Konto IBAN")),
            "Mandat": mandate,
            "Mail": mail,
            "Status": found[0][0] if found else OK,
            "Hinweise": [text for _, text in found],
        })
    return pd.DataFrame(rows, columns=COLUMNS)


def summary(invoices, masterdata, energydata, findings, table, energy_source=""):
    """The figures the operator approves, as (label, value) pairs."""
    invoice_list = invoices.data["list"]
    totals = defaultdict(lambda: Decimal(0))
    counts = defaultdict(int)
    for _, doc in invoice_list.iterrows():
        kind = str(doc.get("Dokumenttyp", ""))
        counts[kind] += 1
        totals[kind] += v._dec(doc.get("Rechnungsbetrag Brutto")) or Decimal(0)
    period = v.billing_period(invoices.data["detailed"])
    creditor = next((str(x) for x in invoice_list.get("Ersteller Name", pd.Series()).dropna()), "")
    compared = table["Abweichung kWh"].notna().sum()
    differing = sum(1 for d in table["Abweichung kWh"].dropna() if abs(d) > v.KWH_TOLERANCE)
    errors = sum(1 for f in findings if f.severity == v.ERROR)
    warnings = sum(1 for f in findings if f.severity == v.WARNING)
    return [
        (tr("Gemeinschaft"), creditor),
        (tr("Abrechnung"), f"{period[0]} Q{period[1]}" if period else "?"),
        (tr("Rechnungen (Lastschrift)"),
         tr("{n} · {total}", n=counts["Rechnung"], total=v.format_euro(totals["Rechnung"]))),
        (tr("Gutschriften (Überweisung)"),
         tr("{n} · {total}", n=counts["Gutschrift"] + counts["Information"],
            total=v.format_euro(totals["Gutschrift"] + totals["Information"]))),
        (tr("Energiedaten"), energy_source or tr("nicht geladen")),
        (tr("kWh-Abgleich"), tr("{n} Dokument(e) geprüft, {bad} mit Abweichung",
                                n=int(compared), bad=differing)),
        (tr("Befunde"), tr("{errors} Fehler, {warnings} Warnung(en)",
                           errors=errors, warnings=warnings)),
    ]


def approval_record(fp, table, findings, reason="", by=""):
    """What an approval says: which data, which documents, which errors were accepted."""
    import datetime as dt
    return {
        "fingerprint": fp,
        "approved_at": dt.datetime.now().isoformat(timespec="seconds"),
        "approved_by": by,
        "documents": {row["Nummer"]: (None if row["Betrag"] is None else float(row["Betrag"]))
                      for _, row in table.iterrows()},
        "accepted_errors": [f"{f.category}: {f.message}" for f in findings
                            if f.severity == v.ERROR],
        "reason": reason,
    }


def write_protocol(path, table, summary_rows, findings, approval=None):
    """The review as an Excel file, for the records."""
    head = list(summary_rows)
    if approval:
        head += [(tr("Freigegeben am"), approval.get("approved_at", "")),
                 (tr("Freigegeben von"), approval.get("approved_by", "")),
                 (tr("Begründung"), approval.get("reason", "")),
                 (tr("Prüfsumme der Daten"), approval.get("fingerprint", ""))]
    documents = table.copy()
    documents["Hinweise"] = documents["Hinweise"].map(lambda items: "\n".join(items))
    for column in ("Betrag", "kWh abgerechnet", "kWh Energiedaten", "Abweichung kWh"):
        documents[column] = documents[column].map(lambda x: None if x is None else float(x))
    found = pd.DataFrame([{tr("Schwere"): f.severity, tr("Bereich"): f.category,
                           tr("Befund"): f.message, tr("Betroffen"): "\n".join(map(str, f.rows))}
                          for f in findings])
    with pd.ExcelWriter(path, engine="openpyxl") as writer:
        pd.DataFrame(head, columns=["", ""]).to_excel(writer, sheet_name=tr("Freigabe"), index=False)
        documents.to_excel(writer, sheet_name=tr("Dokumente"), index=False)
        found.to_excel(writer, sheet_name=tr("Befunde"), index=False)
