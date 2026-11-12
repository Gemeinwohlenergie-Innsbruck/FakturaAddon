import os
import sys
from decimal import Decimal

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import extras
import validation as v
import exporting
from exporting import produce_sepa_export_dfs

PERIOD = "Abr_YQ-2026-3"
CREDITOR = "AT963412900008939258"
COMMON = {"Abrechnung": PERIOD, "Datum": "2026-10-16", "Ersteller Name": "GEI",
          "Ersteller IBAN": CREDITOR, "Ersteller Creditor Id": "AT94ZZZ00000079821",
          "Ersteller BankName": "Bank", "Empfänger Adresse 1": "Weg 1",
          "Empfänger Adresse 2": "6020 Innsbruck", "Empfänger Einzugsart": "CORE",
          "Empfänger Mandatsausstellung": "2026-04-15", "Empfänger Mandatsreferenz": "029"}


def person(number, name, iban, kind, doc):
    first, last = name.split(" ", 1)
    return {**COMMON, "Dokumenttyp": kind, "Nummer": doc, "Empfänger Name": name,
            "Empfänger Mitgliedsnummer": number, "Empfänger Kontoeigner": name,
            "Empfänger Konto IBAN": iban, "Empfänger Vorame": first, "Empfänger Nachname": last}


ANNA = person(29, "Anna Beispiel", "AT13 3412 9000 0021 2498", "Rechnung", "RE202600070")
BERT = person(33, "Bert Sonne", "AT48 2050 3033 0222 2272", "Gutschrift", "GU202600027")


def position(who, kind, text, qty, unit, price, euro_cent, net, vat_rate, vat, tariff):
    return {**who, "Pos. Zählpunkttyp": kind, "Pos. Text": text, "Pos. Menge": qty,
            "Pos. Mengeneinheit": unit, "Pos. Preis / Einheit": price,
            "Pos. Preis / Einheit Euro/Cent": euro_cent, "Pos. Rabatt %": 0,
            "Pos. Nettobetrag": net, "Pos. UST %": vat_rate, "Pos. UST Betrag": vat,
            "Pos. Bruttobetrag": round(net + vat, 2), "Pos. Tarif": tariff}


def invoice_data():
    details = pd.DataFrame([
        position(ANNA, None, "Mitgliedsgebuer Gemeinwohlenergie Standard", 1.0, None, 3.0, "€",
                 3.0, 0, 0.0, "Mitgliedsgebuer Gemeinwohlenergie Standard"),
        position(ANNA, "Verbraucher", "AT0081000801000000000000000100313", 55.3, "kWh", 10.0, "Ct",
                 5.53, 20, 1.11, "Energiewende Standard Verbrauch"),
        position(BERT, "Erzeuger", "AT0081000801000000000000000200999", 100.0, "kWh", 7.5, "Ct",
                 7.5, 0, 0.0, "Energiewende Einspeisung"),
    ])
    invoice_list = pd.DataFrame([
        {**ANNA, "UST Satz 1 (%)": 20.0, "UST Satz 1 Summe (Euro)": 1.11, "UST Satz 2 (%)": None,
         "UST Satz 2 Summe (Euro)": None, "Rechnungsbetrag Netto": 8.53, "Rechnungsbetrag Brutto": 9.64},
        {**BERT, "UST Satz 1 (%)": None, "UST Satz 1 Summe (Euro)": None, "UST Satz 2 (%)": None,
         "UST Satz 2 Summe (Euro)": None, "Rechnungsbetrag Netto": 7.5, "Rechnungsbetrag Brutto": 7.5},
    ])
    return {"list": invoice_list, "detailed": details}


def reading(previous="12.345", current="12.456,4", name="Anna Beispiel", member="29"):
    return extras.Extra(member=member, name=name, description="Verbrauch vor dem Wechselrichter",
                        previous=extras.parse_reading(previous), current=extras.parse_reading(current),
                        reason="Ablesung 30.09.2026")


@pytest.mark.parametrize("text, value", [
    ("12345", "12345"), ("12.345", "12345"), ("12.345,6", "12345.6"), ("12345,6", "12345.6"),
    ("12345.6", "12345.6"), (" 1 234,5 ", "1234.5"), ("", None), ("abc", None)])
def test_parse_reading(text, value):
    assert extras.parse_reading(text) == (None if value is None else Decimal(value))


def test_kwh_is_rounded_half_up_to_two_places():
    assert extras.kwh_between(Decimal("100"), Decimal("211.405")) == Decimal("111.41")


def test_apply_adds_the_position_and_raises_the_totals():
    data, applied, problems = extras.apply(invoice_data(), [reading()])
    assert problems == []
    (_, document, net, vat, gross), = applied
    # 111.40 kWh at 10 ct = 11.14 net, 20 % VAT 2.23
    assert (document, net, vat, gross) == ("RE202600070", Decimal("11.14"), Decimal("2.23"), Decimal("13.37"))
    details = data["detailed"]
    anna = details[details["Nummer"] == "RE202600070"]
    assert list(anna["Pos. Zählpunkttyp"])[-1] == extras.KIND
    assert "12.345,00 → 12.456,40" in list(anna["Pos. Text"])[-1]
    assert list(anna["Pos. Tarif"])[-1] == "Energiewende Standard Verbrauch"
    row = data["list"].iloc[0]
    assert row["Rechnungsbetrag Netto"] == 19.67
    assert row["Rechnungsbetrag Brutto"] == 23.01
    assert row["UST Satz 1 Summe (Euro)"] == 3.34
    # the original is untouched
    assert len(invoice_data()["detailed"]) == 3


def test_applied_data_passes_every_arithmetic_check():
    data, _, _ = extras.apply(invoice_data(), [reading()])
    assert v.check_position_arithmetic(data["detailed"]) == []
    assert [f for f in v.check_documents(data["list"], data["detailed"])
            if f.severity == v.ERROR] == []


def test_kwh_comparison_ignores_the_extra_position():
    data, _, _ = extras.apply(invoice_data(), [reading()])
    positions = v.energy_positions(data["detailed"], None)
    assert len(positions) == 2
    assert v.billed_meters(data["detailed"]) == v.billed_meters(invoice_data()["detailed"])


def test_sepa_debit_includes_the_extra_amount(monkeypatch):
    monkeypatch.setattr(exporting.QMessageBox, "question",
                        staticmethod(lambda *a, **k: exporting.QMessageBox.No))
    data, _, _ = extras.apply(invoice_data(), [reading()])
    debits = data["detailed"][data["detailed"]["Dokumenttyp"] == "Rechnung"]
    assert round(debits["Pos. Bruttobetrag"].sum(), 2) == 23.01
    result = produce_sepa_export_dfs(data["detailed"], "GEI")
    debit_frame = result[0]
    amounts = debit_frame["Betrag in EUR"].astype(str).str.replace(",", ".").astype(float)
    assert round(amounts.sum(), 2) == 23.01


def test_member_without_an_invoice_is_reported_not_dropped():
    data, applied, problems = extras.apply(invoice_data(), [reading(name="Clara Neu", member="77")])
    assert applied == [] and len(problems) == 1
    found = extras.findings(applied, problems, [])
    assert found[0].severity == v.ERROR


def test_reading_that_goes_backwards_is_refused():
    _, applied, problems = extras.apply(invoice_data(), [reading(previous="200", current="100")])
    assert applied == [] and len(problems) == 1


def test_no_vat_when_the_member_pays_none():
    data = invoice_data()
    consumption = data["detailed"]["Pos. Zählpunkttyp"] == "Verbraucher"
    data["detailed"].loc[consumption, ["Pos. UST Betrag", "Pos. Bruttobetrag"]] = [0.0, 5.53]
    _, applied, _ = extras.apply(data, [reading()])
    assert applied[0][3] == Decimal("0.00")


def test_store_remembers_the_last_reading_and_who_is_due(tmp_path):
    path = tmp_path / "extras.json"
    store = extras.load_store(path)
    extras.set_entry(store, CREDITOR, "Abr_YQ-2026-2", reading("100", "200"), every_quarter=True)
    extras.save_store(store, path)
    store = extras.load_store(path)
    key = extras.member_key(29, "Anna Beispiel")
    assert extras.previous_reading(store, CREDITOR, key, PERIOD) == Decimal("200")
    assert extras.missing_readings(store, CREDITOR, PERIOD) == [(key, "Anna Beispiel")]
    extras.set_entry(store, CREDITOR, PERIOD, reading("200", "260"), every_quarter=True)
    assert extras.missing_readings(store, CREDITOR, PERIOD) == []
    assert [e.kwh for e in extras.entries_for(store, CREDITOR, PERIOD)] == [Decimal("60.00")]
    # this quarter's own reading is not its own starting point
    assert extras.previous_reading(store, CREDITOR, key, PERIOD) == Decimal("200")
    extras.remove_entry(store, CREDITOR, PERIOD, key)
    assert extras.entries_for(store, CREDITOR, PERIOD) == []


def test_findings_make_each_extra_a_warning_on_its_document():
    _, applied, problems = extras.apply(invoice_data(), [reading()])
    found = extras.findings(applied, problems, [("k", "Bert Sonne")])
    assert [f.severity for f in found] == [v.WARNING, v.WARNING]
    assert "RE202600070" in found[0].documents
    assert "Bert Sonne" in found[1].names
