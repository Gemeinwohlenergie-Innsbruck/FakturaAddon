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

import pandas as pd

from i18n import tr

ERROR = "error"      # will produce a wrong result or be rejected downstream
WARNING = "warning"  # probably wrong, worth a look
INFO = "info"        # worth knowing

SEVERITY_ORDER = {ERROR: 0, WARNING: 1, INFO: 2}


class Finding:
    __slots__ = ("severity", "category", "message", "rows")

    def __init__(self, severity, category, message, rows=()):
        self.severity = severity
        self.category = category
        self.message = message
        self.rows = list(rows)

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
    """(year, quarter) from the Abrechnung column, e.g. 'EEG-2025-2'."""
    if not _has(invoice_details, "Abrechnung") or invoice_details.empty:
        return None
    raw = str(invoice_details["Abrechnung"].iloc[0])
    parts = raw.split("-")
    if len(parts) < 3:
        return None
    try:
        return int(parts[-2]), int(parts[-1])
    except ValueError:
        return None


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
        unmatched)]


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
                                tr("{n} Mitglied(er) ohne IBAN.", n=len(missing)), missing))
    if invalid:
        findings.append(Finding(ERROR, tr("IBAN"),
                                tr("{n} IBAN(s) mit ungültiger Prüfsumme.", n=len(invalid)), invalid))
    return findings


def check_mandates(invoice_details):
    """Direct debits without a mandate reference cannot be collected."""
    if not _has(invoice_details, "Dokumenttyp", "Empfänger Name"):
        return []
    debits = invoice_details[invoice_details["Dokumenttyp"] == "Rechnung"]
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
                missing))
    return findings


def check_duplicate_names(invoice_details):
    """Two members with the same full name get merged into one payment.

    produce_sepa_export_dfs groups by name, so the second member's positions
    are paid to the first member's IBAN.
    """
    if not _has(invoice_details, "Empfänger Name", "Empfänger Konto IBAN"):
        return []
    ibans_per_name = invoice_details.groupby("Empfänger Name")["Empfänger Konto IBAN"].nunique()
    clashes = [name for name, count in ibans_per_name.items() if count > 1]
    if not clashes:
        return []
    return [Finding(
        ERROR, tr("Doppelte Namen"),
        tr("{n} Name(n) kommen mit mehr als einer IBAN vor. Der SEPA-Export fasst nach Namen "
           "zusammen, diese Zahlungen gingen auf ein einziges Konto.", n=len(clashes)),
        clashes)]


def check_amounts(invoice_details):
    """Zero-value positions, and credits or debits with the wrong sign."""
    if not _has(invoice_details, "Pos. Bruttobetrag", "Empfänger Name"):
        return []
    findings = []
    amounts = pd.to_numeric(invoice_details["Pos. Bruttobetrag"], errors="coerce")
    zero = invoice_details.loc[amounts.fillna(0) == 0, "Empfänger Name"].unique().tolist()
    if zero:
        findings.append(Finding(WARNING, tr("Beträge"),
                                tr("{n} Mitglied(er) mit einer Position von 0,00 €.", n=len(zero)), zero))
    unparsable = invoice_details.loc[amounts.isna(), "Empfänger Name"].unique().tolist()
    if unparsable:
        findings.append(Finding(ERROR, tr("Beträge"),
                                tr("{n} Position(en) mit unlesbarem Betrag.", n=len(unparsable)), unparsable))
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
                                missing))
    if invalid:
        findings.append(Finding(ERROR, tr("Mailadressen"),
                                tr("{n} Mailadresse(n) sehen nicht wie Adressen aus.", n=len(invalid)),
                                invalid))
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


def validate(invoices=None, masterdata=None, energydata=None,
             resolve_name=None, members_with_invoices=None):
    """Run every applicable check. Skips anything whose inputs are not loaded."""
    findings = []
    details = invoices.data["detailed"] if (invoices is not None and invoices.data) else None
    energy = energydata.data if energydata is not None else None
    master = masterdata.data if masterdata is not None else None

    if details is not None:
        findings += check_ibans(details)
        findings += check_mandates(details)
        findings += check_duplicate_names(details)
        findings += check_amounts(details)
        if energy is not None:
            findings += check_billing_period_matches_energy(details, energy)
            if resolve_name is not None:
                findings += check_names_in_energydata(details, energy, resolve_name)
        if master is not None and members_with_invoices is not None:
            findings += check_email_addresses(master, details, members_with_invoices)
    if masterdata is not None:
        findings += check_community_metadata(masterdata)

    findings.sort(key=lambda f: SEVERITY_ORDER.get(f.severity, 9))
    return findings
