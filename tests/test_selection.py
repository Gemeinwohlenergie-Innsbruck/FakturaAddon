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
