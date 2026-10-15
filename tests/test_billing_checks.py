"""The checks that decide whether members are charged correctly.

The fixture is built the way eegfaktura-billing builds a billing run: kWh is
the quarter's allocation rounded half-up to the cent, net is kWh x price in
cent, VAT and gross follow - so a clean fixture must produce no errors, and
each test breaks exactly one thing.
"""
import datetime as dt
import os
import sys
from decimal import Decimal, ROUND_HALF_UP

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import validation as v
from validation import ERROR, WARNING, INFO

ANNA_ZP = "AT0050000000000000000000000000001"
PETER_ZP = "AT0050000000000000000000000000002"
OTHER_ZP = "AT0050000000000000000000000000003"
OWN_IBAN = "AT611904300234573201"
ANNA_IBAN = "DE89370400440532013000"
PETER_IBAN = "AT483200000012345864"
CENT = Decimal("0.01")

INDEX = pd.date_range("2026-07-01", periods=4, freq="15min")
COLUMNS = pd.MultiIndex.from_tuples([
    (ANNA_ZP, "Anna Müller", "CONSUMPTION", "Gesamtverbrauch lt. Messung (bei Teilnahme gem. Erzeugung) [KWH]"),
    (ANNA_ZP, "Anna Müller", "CONSUMPTION", "Anteil gemeinschaftliche Erzeugung [KWH]"),
    (ANNA_ZP, "Anna Müller", "CONSUMPTION", v.UTILIZATION),
    (PETER_ZP, "Peter Schmidt", "GENERATION", v.PRODUCTION),
    (PETER_ZP, "Peter Schmidt", "GENERATION", v.SURPLUS),
], names=["MeteringpointID", "Name", "Energy direction", "Metercode"])


def cent(x):
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


@pytest.fixture
def energy():
    return pd.DataFrame([
        [1.0, 0.8, 0.703, 2.0, 0.5],
        [1.0, 0.8, 0.701, 2.0, 0.5],
        [1.0, 0.8, 0.702, 2.0, 0.5],
        [1.0, 0.8, 0.700, 2.0, 0.5],
    ], index=INDEX, columns=COLUMNS)


def qov_for(energy, labels=None):
    """A QoV frame in the export's layout: value column, then its QoV column."""
    labels = labels or {}
    series, columns = [], []
    for i, column in enumerate(energy.columns):
        series += [energy[column], pd.Series(labels.get(column[0], ["L1"] * len(energy)),
                                             index=energy.index)]
        columns += [column, ("QoV", f"Unnamed: {i}_level_1", "x", "y")]
    frame = pd.concat(series, axis=1)
    frame.columns = pd.MultiIndex.from_tuples(columns)
    return frame


def position(number, kind, name, member, iban, meter_type, meter, kwh, price_ct, vat_pct,
             use_vat=True, discount=0, text_extra=""):
    kwh = cent(kwh)
    net = cent(kwh * Decimal(price_ct) / 100)
    net -= cent(net * Decimal(discount) / 100)
    vat = cent(net * Decimal(vat_pct) / 100) if use_vat else Decimal(0)
    return {
        "Dokumenttyp": kind, "Nummer": number, "Abrechnung": "Abr_YQ-2026-3",
        "Empfänger Name": name, "Empfänger Mitgliedsnummer": member,
        "Empfänger Konto IBAN": iban, "Empfänger Mandatsausstellung": dt.datetime(2024, 3, 1),
        "Empfänger Mandatsreferenz": f"M{member}", "Empfänger Einzugsart": "CORE",
        "Ersteller IBAN": OWN_IBAN, "Ersteller Creditor Id": "AT98ZZZ00000012345",
        "Pos. Zählpunkttyp": meter_type,
        "Pos. Text": f"Anlage-Name: Haus\n{meter}{text_extra}",
        "Pos. Menge": float(kwh), "Pos. Mengeneinheit": "kWh",
        "Pos. Preis / Einheit": float(price_ct), "Pos. Preis / Einheit Euro/Cent": "Ct",
        "Pos. Rabatt %": float(discount), "Pos. Nettobetrag": float(net),
        "Pos. UST %": float(vat_pct), "Pos. UST Betrag": float(vat),
        "Pos. Bruttobetrag": float(net + vat), "Pos. Tarif": "Standard",
    }


def fee(number, name, member, iban, euro, vat_pct=20):
    net = cent(euro)
    vat = cent(net * Decimal(vat_pct) / 100)
    row = position(number, "Rechnung", name, member, iban, "", "", 0, 0, vat_pct)
    row.update({"Pos. Zählpunkttyp": "", "Pos. Text": "Mitgliedsgebuehr", "Pos. Menge": None,
                "Pos. Mengeneinheit": "", "Pos. Preis / Einheit": float(net),
                "Pos. Preis / Einheit Euro/Cent": "€", "Pos. Nettobetrag": float(net),
                "Pos. UST Betrag": float(vat), "Pos. Bruttobetrag": float(net + vat)})
    return row


@pytest.fixture
def details():
    return pd.DataFrame([
        # Anna: utilization 0.703+0.701+0.702+0.700 = 2.806 -> 2.81 kWh billed
        position("1001", "Rechnung", "Anna Müller", 1, ANNA_IBAN, "Verbraucher", ANNA_ZP,
                 "2.81", "12.5", 20),
        fee("1001", "Anna Müller", 1, ANNA_IBAN, "5.00"),
        # Peter: delivered 4 x (2.0 - 0.5) = 6.00 kWh, no VAT charged
        position("1002", "Gutschrift", "Peter Schmidt", 2, PETER_IBAN, "Erzeuger", PETER_ZP,
                 "6.00", "8", 20, use_vat=False),
    ])


def liste_from(details):
    rows = []
    for number, group in details.groupby("Nummer", sort=False):
        first = group.iloc[0]
        rows.append({k: first[k] for k in ("Dokumenttyp", "Nummer", "Abrechnung", "Empfänger Name",
                                           "Empfänger Mitgliedsnummer", "Empfänger Konto IBAN",
                                           "Empfänger Mandatsausstellung", "Empfänger Mandatsreferenz",
                                           "Empfänger Einzugsart", "Ersteller IBAN",
                                           "Ersteller Creditor Id")}
                    | {"Rechnungsbetrag Netto": round(group["Pos. Nettobetrag"].sum(), 2),
                       "Rechnungsbetrag Brutto": round(group["Pos. Bruttobetrag"].sum(), 2)})
    return pd.DataFrame(rows)


@pytest.fixture
def liste(details):
    return liste_from(details)


@pytest.fixture
def members():
    return pd.DataFrame({
        "Mit. Nr.": [1, 2], "Name 1": ["Anna", "Peter"], "Name 2": ["Müller", "Schmidt"],
        "IBAN.": [ANNA_IBAN, PETER_IBAN], "Mandat-Ref.": ["M1", "M2"],
        "Zählpunkt": [ANNA_ZP, PETER_ZP],
    })


META = {"IBAN": "AT61 1904 3002 3457 3201", "Tenant": "CC100438"}


def errors(findings):
    return [f for f in findings if f.severity == ERROR]


# --- the clean run ----------------------------------------------------------

class Loaded:
    def __init__(self, data=None, metadata=None):
        self.data, self.metadata = data, metadata


def test_a_correct_billing_run_raises_no_errors(details, liste, members, energy):
    findings = v.validate(
        invoices=Loaded({"list": liste, "detailed": details}),
        masterdata=Loaded(members, META), energydata=Loaded(energy, qov_for(energy)),
        today=dt.date(2026, 10, 15))
    assert errors(findings) == [], [f.message for f in errors(findings)]


# --- billed kWh against the energy data ------------------------------------

def test_billed_kwh_are_recomputed_per_meter(details, energy):
    positions = v.energy_positions(details, energy, qov_for(energy))
    anna = positions[positions["Meter"] == ANNA_ZP].iloc[0]
    peter = positions[positions["Meter"] == PETER_ZP].iloc[0]
    assert anna["Expected"] == Decimal("2.81") and anna["Diff"] == 0
    assert peter["Expected"] == Decimal("6.00") and peter["Diff"] == 0


def test_kwh_that_disagree_with_the_energy_data_are_an_error(energy):
    """Billed 3.50 kWh where the energy data says 2.81: data corrected after the run."""
    details = pd.DataFrame([position("1001", "Rechnung", "Anna Müller", 1, ANNA_IBAN,
                                     "Verbraucher", ANNA_ZP, "3.50", "12.5", 20)])
    findings = v.check_billed_energy(v.energy_positions(details, energy), quality_loaded=True)
    [finding] = errors(findings)
    assert "1001" in finding.documents
    assert "+0,69 kWh" in finding.rows[0]          # 3.50 - 2.81
    assert "0,10 €" in finding.rows[0]             # 0.69 kWh x 12.5 ct x 1.2


def test_a_billed_meter_missing_from_the_energy_data_is_an_error(energy):
    details = pd.DataFrame([position("1009", "Rechnung", "Eva Gruber", 9, ANNA_IBAN,
                                     "Verbraucher", OTHER_ZP, "1.00", "12.5", 20)])
    [finding] = errors(v.check_billed_energy(v.energy_positions(details, energy), True))
    assert "1009" in finding.documents


def test_free_kwh_are_compared_before_they_are_deducted(energy):
    """The quantity is net of free kWh; the text carries the measured figure."""
    details = pd.DataFrame([position(
        "1001", "Rechnung", "Anna Müller", 1, ANNA_IBAN, "Verbraucher", ANNA_ZP, "0.00", "12.5",
        20, text_extra="\nMenge (0,00 kWh) = Verbrauch (2,81 kWh) abzgl. freie kWh (10,00 kWh)")])
    assert errors(v.check_billed_energy(v.energy_positions(details, energy), True)) == []


def test_the_right_holder_is_used_when_a_meter_changed_hands(energy):
    """Two people held Anna's meter this quarter; each is billed their own part."""
    second = energy.loc[:, energy.columns.get_level_values(0) == ANNA_ZP].copy()
    second.columns = pd.MultiIndex.from_tuples(
        [(c[0], "Eva Gruber", c[2], c[3]) for c in second.columns], names=energy.columns.names)
    energy.loc[INDEX[2]:, energy.columns.get_level_values(0) == ANNA_ZP] = float("nan")
    second.loc[:INDEX[1]] = float("nan")
    both = pd.concat([energy, second], axis=1)
    details = pd.DataFrame([
        position("1001", "Rechnung", "Anna Müller", 1, ANNA_IBAN, "Verbraucher", ANNA_ZP,
                 "1.40", "12.5", 20),                    # 0.703 + 0.701
        position("1003", "Rechnung", "Eva Gruber", 3, ANNA_IBAN, "Verbraucher", ANNA_ZP,
                 "1.40", "12.5", 20),                    # 0.702 + 0.700
    ])
    assert errors(v.check_billed_energy(v.energy_positions(details, both), True)) == []


# --- quality of what was billed --------------------------------------------

@pytest.mark.parametrize("label, severity", [("L3", ERROR), ("L0", ERROR), ("L2", INFO)])
def test_quality_of_billed_quarter_hours(details, energy, label, severity):
    qov = qov_for(energy, {ANNA_ZP: ["L1", label, "L1", "L1"]})
    findings = v.check_billed_energy(v.energy_positions(details, energy, qov), True)
    quality = [f for f in findings if f.category == "Datenqualität"]
    assert [f.severity for f in quality] == [severity]
    assert "1 Viertelstunde" in quality[0].rows[0]


def test_unchecked_quality_is_said_out_loud(details, energy):
    findings = v.check_billed_energy(v.energy_positions(details, energy), quality_loaded=False)
    assert [f.severity for f in findings] == [WARNING]


# --- the two sheets agree ---------------------------------------------------

def test_document_total_must_equal_its_positions(details, liste):
    liste.loc[liste["Nummer"] == "1001", "Rechnungsbetrag Brutto"] += 0.01
    [finding] = errors(v.check_documents(liste, details))
    assert "1001" in finding.documents


@pytest.mark.parametrize("breakage, words", [
    (lambda l, d: (pd.concat([l, l.iloc[[0]]]), d), "mehrfach"),
    (lambda l, d: (l.assign(Dokumenttyp=["Mahnung", "Gutschrift"]), d), "unbekanntem Typ"),
    (lambda l, d: (l, d[d["Nummer"] != "1002"]), "ohne Positionen"),
    (lambda l, d: (l.assign(Abrechnung=["Abr_YQ-2026-3", "Abr_YQ_2026-2"]), d), "mehrere"),
    (lambda l, d: (l.assign(**{"Rechnungsbetrag Brutto": [-1.0, 0.48]}), d), "negativ"),
])
def test_broken_exports_are_errors(details, liste, breakage, words):
    broken_list, broken_details = breakage(liste, details)
    messages = [f.message for f in errors(v.check_documents(broken_list, broken_details))]
    assert any(words in m for m in messages), messages


def test_positions_must_rederive(details):
    details.loc[0, "Pos. Nettobetrag"] += 0.05
    details.loc[0, "Pos. Bruttobetrag"] += 0.05
    [finding] = v.check_position_arithmetic(details)
    assert "1001" in finding.documents and "netto" in finding.rows[0]


def test_vat_switched_off_is_not_an_arithmetic_error(details):
    """Peter's tariff shows 20 % but charges none - that is how the export looks."""
    assert v.check_position_arithmetic(details[details["Nummer"] == "1002"]) == []


# --- one community ----------------------------------------------------------

def test_invoices_from_another_community_are_an_error(details, liste, members, energy):
    other = dict(META, IBAN="AT483200000012345864")
    [finding] = v.check_same_community(liste, details, members, other, energy)
    assert finding.severity == ERROR and "anderen Gemeinschaft" in finding.message


def test_billed_meters_unknown_to_the_member_list_are_an_error(details, liste, members, energy):
    findings = v.check_same_community(liste, details, members[members["Mit. Nr."] == 1],
                                      META, energy)
    assert any("Stammdaten" in f.message for f in errors(findings))


def test_energy_data_of_another_community_is_an_error(details, liste, members, energy):
    foreign = energy.copy()
    foreign.columns = pd.MultiIndex.from_tuples(
        [(c[0].replace("AT005", "AT009"),) + c[1:] for c in energy.columns])
    findings = v.check_same_community(liste, details, members, META, foreign)
    assert any("Energiedaten" in f.message for f in errors(findings))


# --- bank details still current ---------------------------------------------

def test_an_iban_changed_since_the_billing_run_is_an_error(liste, members):
    members.loc[members["Mit. Nr."] == 1, "IBAN."] = "AT611904300234573201"
    [finding] = v.check_bank_details_current(liste, members)
    assert finding.severity == ERROR and "1001" in finding.documents
    assert "3000" in finding.rows[0] and "3201" in finding.rows[0]   # last 4 digits only


def test_a_changed_mandate_reference_is_a_warning(liste, members):
    members.loc[members["Mit. Nr."] == 1, "Mandat-Ref."] = "M1-neu"
    [finding] = v.check_bank_details_current(liste, members)
    assert finding.severity == WARNING


# --- what the bank needs ----------------------------------------------------

def test_a_mandate_signed_in_the_future_is_an_error(liste):
    liste.loc[0, "Empfänger Mandatsausstellung"] = dt.datetime(2026, 12, 1)
    [finding] = errors(v.check_sepa_prerequisites(liste, today=dt.date(2026, 10, 15)))
    assert "1001" in finding.documents


def test_debits_need_a_creditor_id(liste):
    liste.loc[0, "Ersteller Creditor Id"] = None
    assert errors(v.check_sepa_prerequisites(liste, today=dt.date(2026, 10, 15)))


def test_information_documents_are_flagged_as_paid_out(liste):
    liste.loc[1, "Dokumenttyp"] = "Information"
    findings = v.check_sepa_prerequisites(liste, today=dt.date(2026, 10, 15))
    assert [f.severity for f in findings] == [INFO]


# --- nobody forgotten, nothing twice ----------------------------------------

def test_meters_with_energy_but_no_position_are_a_warning(details, energy):
    extra = energy.loc[:, energy.columns.get_level_values(0) == ANNA_ZP].copy()
    extra.columns = pd.MultiIndex.from_tuples(
        [(OTHER_ZP, "Eva Gruber", c[2], c[3]) for c in extra.columns])
    [finding] = v.check_unbilled_meters(details, pd.concat([energy, extra], axis=1))
    assert finding.severity == WARNING and "ZP …000003" in finding.rows[0]


def test_documents_already_exported_are_an_error_and_mailed_a_warning(liste):
    findings = v.check_previous_runs(liste, exported={"1001": "02.10.2026"},
                                     mailed={"1002": "03.10.2026"})
    by_severity = {f.severity: f for f in findings}
    assert "1001" in by_severity[ERROR].documents
    assert "02.10.2026" in by_severity[ERROR].documents["1001"]
    assert "1002" in by_severity[WARNING].documents


def test_document_numbers_read_as_floats_still_match():
    assert v.document_key(1001.0) == "1001" and v.document_key(" RE-7 ") == "RE-7"
