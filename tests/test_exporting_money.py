"""Netting a person's debit against their credit."""
import os
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from exporting import check_doubles


def positions(rows):
    return pd.DataFrame(rows, columns=["Empfänger Name", "Dokumenttyp", "Pos. Bruttobetrag"])


def test_debits_and_credits_are_paired_per_person():
    """Two people with both: zip over row indices crossed them over."""
    data = positions([
        ("Anna", "Rechnung", 10.0), ("Anna", "Rechnung", 5.0), ("Peter", "Rechnung", 2.0),
        ("Peter", "Gutschrift", 30.0), ("Anna", "Gutschrift", 4.0),
    ])
    _, _, doubles = check_doubles(data)
    result = dict(zip(doubles["Name"], zip(doubles["Type"], doubles["Final"])))
    assert result == {"Anna": ("Lastschrift", 11.0), "Peter": ("Überweisung", 28.0)}


import exporting
from exporting import net_member_positions, produce_sepa_export_dfs


def doc_positions(kind, name, net, vat):
    return pd.DataFrame([{"Empfänger Name": name, "Dokumenttyp": kind, "Pos. Nettobetrag": net,
                          "Pos. UST Betrag": vat, "Pos. Bruttobetrag": net + vat}])


def test_an_invoice_nets_the_credit_including_its_vat():
    kind, rows = net_member_positions(doc_positions("Rechnung", "Anna", 20.0, 4.0),
                                      doc_positions("Gutschrift", "Anna", 5.0, 1.0))
    assert kind == "Rechnung"
    assert list(rows["Pos. UST Betrag"]) == [4.0, -1.0]
    assert rows["Pos. Bruttobetrag"].sum() == 18.0


def test_debit_equal_to_credit_totals_zero_not_double():
    kind, rows = net_member_positions(doc_positions("Rechnung", "Anna", 10.0, 2.0),
                                      doc_positions("Gutschrift", "Anna", 10.0, 2.0))
    assert kind == "Rechnung" and rows["Pos. Bruttobetrag"].sum() == 0.0


def sepa_row(name, kind, gross):
    return {"Empfänger Name": name, "Dokumenttyp": kind, "Pos. Bruttobetrag": gross,
            "Empfänger Adresse 1": "", "Empfänger Adresse 2": "",
            "Empfänger Konto IBAN": "AT611904300234573201", "Ersteller IBAN": "AT483200000012345864",
            "Empfänger Mandatsausstellung": "01.01.2024", "Empfänger Mandatsreferenz": "M1",
            "Ersteller Creditor Id": "AT98ZZZ00000012345", "Empfänger Einzugsart": "CORE",
            "Abrechnung": "Abr_YQ-2026-3"}


def test_a_debit_and_credit_that_cancel_out_move_no_money(monkeypatch):
    """Merged per person, 10,00 debit and 10,00 credit used to leave a 0,00 transfer."""
    monkeypatch.setattr(exporting.QMessageBox, "question",
                        staticmethod(lambda *a, **k: exporting.QMessageBox.No))
    data = pd.DataFrame([sepa_row("Anna", "Rechnung", 10.0), sepa_row("Anna", "Gutschrift", 10.0),
                         sepa_row("Peter", "Rechnung", 5.0)])
    debit, transfer, _ = produce_sepa_export_dfs(data, "GEI")
    assert list(debit["Zahlungspflichtiger Name"]) == ["Peter"]
    assert list(debit["Betrag in EUR"]) == ["5,00"]
    assert transfer is None or transfer.empty


from exporting import format_quantity, format_unit_price


def test_netted_zero_vat_is_not_negative():
    _, rows = net_member_positions(doc_positions("Rechnung", "Anna", 20.0, 4.0),
                                   doc_positions("Gutschrift", "Anna", 5.0, 0.0))
    assert f"{rows['Pos. UST Betrag'].iloc[1]:.2f}" == "0.00"


def test_fees_show_no_quantity_rather_than_nan():
    assert format_quantity(float("nan"), "") == ""
    assert format_quantity(2.81, "kWh") == "2.81 kWh"
    assert format_quantity(6.0, "kWh") == "6.00 kWh"


def test_unit_prices_keep_fractions_of_a_cent():
    assert format_unit_price(0.125) == "0.125"
    assert format_unit_price(0.12) == "0.12"
    assert format_unit_price(5.0) == "5.00"
    assert format_unit_price(0.08) == "0.08"


def test_self_payers_are_not_debited_and_their_debt_reduces_their_credit(monkeypatch):
    monkeypatch.setattr(exporting.QMessageBox, "question",
                        staticmethod(lambda *a, **k: exporting.QMessageBox.No))
    rows = [sepa_row("Anna", "Rechnung", 3.0), sepa_row("Anna", "Gutschrift", 10.0),
            sepa_row("Eva", "Rechnung", 3.0), sepa_row("Peter", "Rechnung", 5.0)]
    rows[0]["Empfänger Einzugsart"] = rows[1]["Empfänger Einzugsart"] = "NONE"
    rows[2]["Empfänger Einzugsart"] = "NONE"
    debit, transfer, _ = produce_sepa_export_dfs(pd.DataFrame(rows), "GEI")
    assert list(debit["Zahlungspflichtiger Name"]) == ["Peter"]
    assert list(transfer["Empfänger Name"]) == ["Anna"] and list(transfer["Betrag in EUR"]) == ["7,00"]


def test_one_person_with_two_memberships_pays_from_each_account(monkeypatch):
    """Hubert: two memberships, two accounts. Merged by name, both amounts left one account."""
    monkeypatch.setattr(exporting.QMessageBox, "question",
                        staticmethod(lambda *a, **k: exporting.QMessageBox.No))
    first, second = sepa_row("Hubert", "Rechnung", 9.94), sepa_row("Hubert", "Rechnung", 11.22)
    first["Empfänger Konto IBAN"], second["Empfänger Konto IBAN"] = "AT611904300234573201", "DE89370400440532013000"
    debit, transfer, _ = produce_sepa_export_dfs(pd.DataFrame([first, second]), "GEI")
    assert sorted(zip(debit["Zahlungspflichtiger IBAN"], debit["Betrag in EUR"])) == [
        ("AT611904300234573201", "9,94"), ("DE89370400440532013000", "11,22")]
