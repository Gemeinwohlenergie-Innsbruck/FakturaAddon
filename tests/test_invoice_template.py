"""The generated invoice template and the fields the app fills must agree."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from docxtpl import DocxTemplate

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

FILLED_BY_THE_APP = {
    "EmpfängerName", "EmpfängerAdresse1", "EmpfängerAdresse2", "invoiceitemstbl_contents",
    "Rechnung_Gutschrift", "Rechnungsnummer", "DatumHeute", "Jahr", "Quartal", "Zeitraum",
    "Mitgliedsnummer", "Einleitung", "TotalSumNetto", "TotalSumUst", "TotalSumBrutto",
    "TotalLabel", "Überweisungstext", "Grafik", "TextfürVerbrauch",
    "community_name", "community_street", "community_streetnr", "community_citycode",
    "community_city", "community_phone", "community_mail", "community_website",
    "community_IBAN", "community_companynumber",
}


def test_template_asks_only_for_fields_the_app_fills():
    template = DocxTemplate(os.path.join(ROOT, "templates", "template_invoice_clean.docx"))
    wanted = template.get_undeclared_template_variables()
    assert wanted <= FILLED_BY_THE_APP, wanted - FILLED_BY_THE_APP
    assert "Grafik" in wanted            # the chart is inline, so it flows to page two if needed
