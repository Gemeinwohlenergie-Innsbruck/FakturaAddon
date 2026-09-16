import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from validation import (ERROR, WARNING, iban_is_valid, quarter_date_range, billing_period,
                        check_billing_period_matches_energy, check_ibans, check_mandates,
                        check_duplicate_names, check_amounts, check_email_addresses,
                        check_names_in_energydata)
from selection import members_with_invoices


# --- IBAN ------------------------------------------------------------------

@pytest.mark.parametrize("iban", [
    "AT61 1904 3002 3457 3201",   # the canonical ISO example
    "AT611904300234573201",
    "DE89370400440532013000",
])
def test_valid_ibans_pass(iban):
    assert iban_is_valid(iban)


@pytest.mark.parametrize("iban", [
    "AT61 1904 3002 3457 3202",   # last digit changed
    "AT61 1904 3002 3457 3210",   # transposed - a length check would miss this
    "", None, float("nan"), "not an iban", "AT61",
])
def test_bad_ibans_fail(iban):
    assert not iban_is_valid(iban)


# --- quarters --------------------------------------------------------------

@pytest.mark.parametrize("year,quarter,start,end", [
    (2025, 1, "2025-01-01", "2025-03-31"),
    (2025, 2, "2025-04-01", "2025-06-30"),
    (2025, 4, "2025-10-01", "2025-12-31"),
    (2024, 1, "2024-01-01", "2024-03-31"),   # leap year
])
def test_quarter_date_range(year, quarter, start, end):
    got_start, got_end = quarter_date_range(year, quarter)
    assert str(got_start) == start and str(got_end) == end


def test_billing_period_parsed_from_abrechnung():
    df = pd.DataFrame({"Abrechnung": ["EEG-2025-2"]})
    assert billing_period(df) == (2025, 2)


def energy_frame(start, periods):
    index = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({"x": range(periods)}, index=index)


def test_energy_from_the_wrong_quarter_is_an_error():
    """The expensive silent mistake: Q2 invoices against Q1 energy data."""
    details = pd.DataFrame({"Abrechnung": ["EEG-2025-2"]})
    findings = check_billing_period_matches_energy(details, energy_frame("2025-01-01", 90))
    assert [f.severity for f in findings] == [ERROR]
    assert "außerhalb" in findings[0].message


def test_matching_quarter_is_clean():
    details = pd.DataFrame({"Abrechnung": ["EEG-2025-2"]})
    assert check_billing_period_matches_energy(details, energy_frame("2025-04-01", 91)) == []


def test_partial_quarter_coverage_warns():
    details = pd.DataFrame({"Abrechnung": ["EEG-2025-2"]})
    findings = check_billing_period_matches_energy(details, energy_frame("2025-04-01", 40))
    assert [f.severity for f in findings] == [WARNING]


# --- banking ---------------------------------------------------------------

def test_missing_and_invalid_ibans_are_reported():
    details = pd.DataFrame({
        "Empfänger Name": ["Anna Müller", "Peter Schmidt", "Eva Gruber"],
        "Empfänger Konto IBAN": ["AT611904300234573201", "", "AT611904300234573202"],
    })
    findings = check_ibans(details)
    messages = " ".join(f.message for f in findings)
    assert "ohne IBAN" in messages and "Prüfsumme" in messages
    assert all(f.severity == ERROR for f in findings)


def test_debit_without_mandate_reference_is_an_error():
    details = pd.DataFrame({
        "Empfänger Name": ["Anna Müller", "Eva Gruber"],
        "Dokumenttyp": ["Rechnung", "Gutschrift"],
        "Empfänger Mandatsreferenz": ["", ""],
    })
    findings = check_mandates(details)
    assert len(findings) == 1
    # Only the debit counts; a credit needs no mandate.
    assert findings[0].rows == ["Anna Müller"]


def test_same_name_two_ibans_is_flagged():
    """produce_sepa_export_dfs groups by name, so this would pay both to one account."""
    details = pd.DataFrame({
        "Empfänger Name": ["Anna Müller", "Anna Müller"],
        "Empfänger Konto IBAN": ["AT611904300234573201", "DE89370400440532013000"],
    })
    findings = check_duplicate_names(details)
    assert len(findings) == 1 and findings[0].rows == ["Anna Müller"]


def test_one_member_with_several_positions_is_not_a_clash():
    details = pd.DataFrame({
        "Empfänger Name": ["Anna Müller", "Anna Müller"],
        "Empfänger Konto IBAN": ["AT611904300234573201", "AT611904300234573201"],
    })
    assert check_duplicate_names(details) == []


def test_zero_and_unparsable_amounts():
    details = pd.DataFrame({
        "Empfänger Name": ["Anna", "Peter", "Eva"],
        "Pos. Bruttobetrag": [52.0, 0.0, "keine Zahl"],
    })
    findings = check_amounts(details)
    severities = sorted(f.severity for f in findings)
    assert severities == [ERROR, WARNING]


# --- mail ------------------------------------------------------------------

def test_missing_and_duplicate_mail_addresses():
    master = pd.DataFrame({
        "Name 1": ["Anna", "Peter", "Eva"],
        "Name 2": ["Müller", "Schmidt", "Gruber"],
        "E-Mail": ["anna@example.at", "", "anna@example.at"],
    })
    details = pd.DataFrame({
        "Empfänger Vorame": ["Anna", "Peter", "Eva"],
        "Empfänger Nachname": ["Müller", "Schmidt", "Gruber"],
    })
    findings = check_email_addresses(master, details, members_with_invoices)
    messages = " ".join(f.message for f in findings)
    assert "keine Mailadresse" in messages
    assert "mehrfach" in messages


# --- robustness ------------------------------------------------------------

def test_checks_tolerate_missing_columns():
    """A renamed Faktura column must produce no finding, not a traceback."""
    empty = pd.DataFrame({"irgendwas": [1]})
    assert check_ibans(empty) == []
    assert check_mandates(empty) == []
    assert check_duplicate_names(empty) == []
    assert check_amounts(empty) == []
    assert check_names_in_energydata(empty, pd.DataFrame(), lambda d, n: None) == []
