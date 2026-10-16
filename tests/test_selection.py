import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from selection import select_invoice_positions


@pytest.fixture
def invoice_list():
    """One row per invoice document, as EEG Faktura's "Liste" sheet has it."""
    return pd.DataFrame({
        "Empfänger Name": ["Anna Müller", "Peter Schmidt", "Eva Gruber"],
        "Dokumenttyp": ["Rechnung", "Rechnung", "Gutschrift"],
    })


@pytest.fixture
def invoice_details():
    """One row per position, as the "Details" sheet has it."""
    return pd.DataFrame({
        "Empfänger Name": ["Anna Müller", "Anna Müller", "Peter Schmidt", "Eva Gruber"],
        "Pos. Bruttobetrag": [40.0, 12.0, 55.0, -30.0],
    })


def test_unticked_person_is_excluded(invoice_list, invoice_details):
    """The regression: unticking somebody must stop them being debited."""
    details, names = select_invoice_positions(invoice_list, invoice_details,
                                              [True, False, True])
    assert "Peter Schmidt" not in set(details["Empfänger Name"])
    assert set(names) == {"Anna Müller", "Eva Gruber"}


def test_all_positions_of_a_selected_person_are_kept(invoice_list, invoice_details):
    """Anna has two positions; selecting her must bring both."""
    details, _ = select_invoice_positions(invoice_list, invoice_details,
                                          [True, False, False])
    assert len(details) == 2
    assert details["Pos. Bruttobetrag"].sum() == pytest.approx(52.0)


def test_nothing_selected_yields_nothing(invoice_list, invoice_details):
    details, names = select_invoice_positions(invoice_list, invoice_details,
                                              [False, False, False])
    assert details.empty
    assert names.empty


def test_everything_selected_yields_everything(invoice_list, invoice_details):
    details, _ = select_invoice_positions(invoice_list, invoice_details,
                                          [True, True, True])
    assert len(details) == len(invoice_details)


def test_mask_length_mismatch_is_rejected(invoice_list, invoice_details):
    """A silently misaligned mask would debit the wrong people."""
    with pytest.raises(ValueError):
        select_invoice_positions(invoice_list, invoice_details, [True, False])


# --- who receives an invoice by mail --------------------------------------

from selection import members_with_invoices


@pytest.fixture
def masterdata():
    """Anna Schmidt is the trap: she shares a first name with one invoice
    recipient and a surname with another, but has no invoice of her own."""
    return pd.DataFrame({
        "Name 1": ["Anna", "Peter", "Anna", "Eva"],
        "Name 2": ["Müller", "Schmidt", "Schmidt", "Gruber"],
        "E-Mail": ["anna.mueller@example.at", "peter.schmidt@example.at",
                   "anna.schmidt@example.at", "eva.gruber@example.at"],
    })


@pytest.fixture
def details_for_two():
    return pd.DataFrame({
        "Empfänger Vorame": ["Anna", "Peter"],
        "Empfänger Nachname": ["Müller", "Schmidt"],
    })


def test_cross_product_match_is_not_made(masterdata, details_for_two):
    """The regression: Anna Schmidt must not be queued for somebody's invoice."""
    result = members_with_invoices(masterdata, details_for_two)
    assert "anna.schmidt@example.at" not in set(result["E-Mail"])
    assert set(result["E-Mail"]) == {"anna.mueller@example.at",
                                     "peter.schmidt@example.at"}


def test_trailing_whitespace_still_matches(masterdata):
    """The two exports disagree about trailing spaces; that must not drop anyone."""
    details = pd.DataFrame({
        "Empfänger Vorame": ["Anna "],
        "Empfänger Nachname": [" Müller"],
    })
    result = members_with_invoices(masterdata, details)
    assert set(result["E-Mail"]) == {"anna.mueller@example.at"}


def test_missing_surname_matches_on_first_name_alone():
    """Members with no surname carry NaN, which must compare equal to itself."""
    master = pd.DataFrame({
        "Name 1": ["Sonnenstrom GmbH", "Eva"],
        "Name 2": [float("nan"), "Gruber"],
        "E-Mail": ["office@sonnenstrom.at", "eva@example.at"],
    })
    details = pd.DataFrame({
        "Empfänger Vorame": ["Sonnenstrom GmbH"],
        "Empfänger Nachname": [float("nan")],
    })
    result = members_with_invoices(master, details)
    assert set(result["E-Mail"]) == {"office@sonnenstrom.at"}


def test_no_invoices_selects_nobody(masterdata):
    empty = pd.DataFrame({"Empfänger Vorame": [], "Empfänger Nachname": []})
    assert members_with_invoices(masterdata, empty).empty


# --- by document, not by person ---------------------------------------------

def test_only_the_ticked_document_of_a_person_is_selected():
    """Anna has an invoice and a credit note; only the credit note is ticked."""
    invoice_list = pd.DataFrame({
        "Nummer": [1001, 1002],
        "Empfänger Name": ["Anna Müller", "Anna Müller"],
        "Dokumenttyp": ["Rechnung", "Gutschrift"],
    })
    invoice_details = pd.DataFrame({
        "Nummer": [1001.0, 1001.0, 1002.0],
        "Empfänger Name": ["Anna Müller"] * 3,
        "Pos. Bruttobetrag": [40.0, 12.0, 30.0],
    })
    details, _ = select_invoice_positions(invoice_list, invoice_details, [False, True])
    assert list(details["Pos. Bruttobetrag"]) == [30.0]


def test_documents_of_a_member_are_found_by_name_pair():
    from selection import documents_of_member
    invoice_list = pd.DataFrame({
        "Nummer": [1001.0, 1002.0, 1003.0],
        "Empfänger Vorame": ["Anna", "Anna ", "Peter"],
        "Empfänger Nachname": ["Müller", "Müller", "Müller"],
    })
    assert documents_of_member(invoice_list, "Anna", "Müller") == ["1001", "1002"]


def test_preview_documents_without_numbers_stay_apart():
    """A preview export has no invoice numbers; every document used to be "the same"."""
    from selection import document_ids
    nan = float("nan")
    invoice_list = pd.DataFrame({
        "Nummer": [nan, nan, nan], "Abrechnung": ["Abr_YQ-2026-3"] * 3,
        "Dokumenttyp": ["Rechnung", "Rechnung", "Gutschrift"],
        "Empfänger Mitgliedsnummer": [12, 13, 12],
        "Empfänger Name": ["Anna Müller", "Peter Schmidt", "Anna Müller"],
    })
    assert list(document_ids(invoice_list)) == ["Vorschau 2026-3/R12 Anna Müller",
                                                "Vorschau 2026-3/R13 Peter Schmidt",
                                                "Vorschau 2026-3/G12 Anna Müller"]
    details = invoice_list.assign(**{"Pos. Bruttobetrag": [40.0, 55.0, 30.0]})
    selected, _ = select_invoice_positions(invoice_list, details, [False, True, False])
    assert list(selected["Pos. Bruttobetrag"]) == [55.0]


def test_invoice_file_names_have_no_nan_and_no_slashes():
    from selection import invoice_file_stem
    assert invoice_file_stem("2026", "3", "Anna ", " Müller") == "Rechnung_2026_q3_Anna_Müller"
    assert invoice_file_stem("2026", "3", "Sonnenstrom GmbH", float("nan")) == "Rechnung_2026_q3_Sonnenstrom GmbH"
    assert invoice_file_stem("2026", "3", "Verein A/B", None) == "Rechnung_2026_q3_Verein A-B"
