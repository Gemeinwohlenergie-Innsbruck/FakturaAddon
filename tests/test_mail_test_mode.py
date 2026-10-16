import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from jinja2 import Environment, FileSystemLoader, select_autoescape

from emailing import build_invoice_email

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Master:
    metadata = {"Bezeichnung": "GEI", "Straße": "Weg", "StraßenNr.": "1", "PLZ": "6020",
                "Wohnort": "Innsbruck", "E-Mail": "info@example.at", "Web Seite": "x",
                "TelefonNr.": "0", "IBAN": "AT61"}


def template():
    env = Environment(loader=FileSystemLoader(os.path.join(ROOT, "templates")),
                      autoescape=select_autoescape())
    return env.get_template("email_template_clean.html")


def mail(test_recipient=None):
    return build_invoice_email("info@example.at", "GEI", "anna@example.at", "Anna", "3", "2026",
                               template(), None, Master(), test_recipient=test_recipient)


def test_normal_mail_goes_to_the_member():
    message = mail()
    assert message["To"] == "anna@example.at"
    assert not message["Subject"].startswith("[TEST")


def test_test_mode_sends_to_the_test_address_and_says_for_whom():
    message = mail(test_recipient="sam@example.at")
    assert message["To"] == "sam@example.at"
    assert message["Subject"].startswith("[TEST → anna@example.at] ")
