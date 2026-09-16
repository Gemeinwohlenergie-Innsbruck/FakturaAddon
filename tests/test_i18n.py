"""Guards against a half-translated UI.

The risk with German-as-the-key is that a new string gets added and simply
falls through to German when the UI is English - silently, and only where
nobody happened to look. These tests exercise the real widgets and then assert
that every key tr() was actually asked for has an English entry.
"""
import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import i18n


@pytest.fixture(autouse=True)
def german_again():
    yield
    i18n.set_language("de")


def test_german_is_the_identity():
    i18n.set_language("de")
    assert i18n.tr("Daten prüfen") == "Daten prüfen"
    assert i18n.tr("{n} Fehler", n=3) == "3 Fehler"


def test_english_translates_and_formats():
    i18n.set_language("en")
    assert i18n.tr("Daten prüfen") == "Check data"
    assert i18n.tr("{n} Fehler", n=3) == "3 errors"


def test_unknown_language_falls_back_to_german():
    assert i18n.set_language("fr") == "de"
    assert i18n.tr("Daten prüfen") == "Daten prüfen"


def test_unknown_key_falls_back_to_the_german_source():
    i18n.set_language("en")
    assert i18n.tr("Ein völlig neuer Satz") == "Ein völlig neuer Satz"


def test_every_placeholder_survives_translation():
    """An English string that drops a {placeholder} raises at format time."""
    import string
    formatter = string.Formatter()
    for source, translated in i18n.EN.items():
        want = {f for _, f, _, _ in formatter.parse(source) if f}
        got = {f for _, f, _, _ in formatter.parse(translated) if f}
        assert want == got, f"placeholder mismatch for {source!r}: {want} vs {got}"


_KEEP_ALIVE = []   # Qt deletes the C++ object as soon as Python drops the last ref


def _build_whole_ui():
    """Construct every user-facing widget so tr() sees every key they use."""
    import tempfile, pathlib
    import config
    tmp = pathlib.Path(tempfile.mkdtemp())
    env = tmp / ".env"
    env.write_text("MAIL_ADDRESS=a@b.at\nMAIL_IMAP_SERVER=mail.x.at\n"
                   f"HOME_DIRECTORY={tmp}\nEEG_NAME=GEI\n", encoding="utf-8")
    config.ENV_PATH = env

    from PyQt5 import QtWidgets
    # Held too: when the QApplication is collected Qt tears down every widget
    # with it, and findChildren then raises "C++ object has been deleted".
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    _KEEP_ALIVE.append(app)
    import main, validation
    from importing import SettingsDialog
    from emailing import SendPreviewDialog

    window = main.MainWindow()
    details = pd.DataFrame({
        "Empfänger Name": ["Anna Müller", "Eva Gruber"],
        "Empfänger Vorame": ["Anna", "Eva"],
        "Empfänger Nachname": ["Müller", "Gruber"],
        "Empfänger Konto IBAN": ["AT611904300234573201", ""],
        "Dokumenttyp": ["Rechnung", "Gutschrift"],
        "Empfänger Mandatsreferenz": ["", "M-2"],
        "Pos. Bruttobetrag": [52.0, 0.0],
        "Rechnungsbetrag Brutto": [52.0, 30.0],
        "Abrechnung": ["EEG-2025-2", "EEG-2025-2"],
    })
    window.invoices.data = {"list": details, "detailed": details}
    window.masterdata.data = pd.DataFrame({"Name 1": ["Anna"], "Name 2": ["Müller"],
                                           "E-Mail": [""]})
    window.masterdata.metadata = {"Bezeichnung": "GEI"}
    window.invoicesdata_loaded = True
    window.thisinvoices_year, window.thisinvoice_quart = "2025", "2"
    window.on_data_changed()
    window.mark_step_done("validate")

    # dialogs
    findings = validation.validate(invoices=window.invoices, masterdata=window.masterdata,
                                   members_with_invoices=main.members_with_invoices)
    main.ValidationDialog(findings)
    main.ValidationDialog([])
    SettingsDialog()
    SendPreviewDialog([("Anna Müller", "a@b.at", "/tmp/Rechnung.pdf")],
                      [("Eva Gruber", "e@b.at", "Rechnung_Eva.pdf")],
                      lambda addr: ("Betreff", "<p>hi</p>", "Rechnung.pdf"))
    _KEEP_ALIVE.extend([
        window,
        main.ValidationDialog(findings),
        SettingsDialog(),
        SendPreviewDialog([("Anna Müller", "a@b.at", "/tmp/Rechnung.pdf")], [],
                          lambda addr: ("Betreff", "<p>hi</p>", "Rechnung.pdf")),
    ])
    return window


def test_no_string_in_the_ui_is_left_untranslated():
    """The real guard: build the whole UI, then demand English for every key."""
    i18n.set_language("en")
    i18n.reset_usage()      # only count what this test's UI actually asks for
    _build_whole_ui()
    missing = i18n.missing_translations()
    assert not missing, (
        f"{len(missing)} string(s) reached the UI with no English translation:\n  "
        + "\n  ".join(sorted(repr(m) for m in missing)))


def _tr_keys_in_source():
    """Every literal tr("…") key in the project, found statically.

    The runtime walk above cannot reach modal dialogs - they call exec_() and
    would block - so this covers the call sites it can never execute.
    """
    import ast
    root = pathlib.Path(__file__).resolve().parent.parent
    keys = {}
    for path in sorted(root.glob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            name = func.id if isinstance(func, ast.Name) else getattr(func, "attr", None)
            if name != "tr" or not node.args:
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                keys.setdefault(first.value, path.name)
    return keys


import pathlib


def test_every_tr_call_site_has_an_english_string():
    keys = _tr_keys_in_source()
    assert len(keys) > 100, f"expected the whole UI, only found {len(keys)} tr() calls"
    missing = {k: where for k, where in keys.items() if k not in i18n.EN}
    assert not missing, (
        f"{len(missing)} tr() call site(s) have no English string:\n  "
        + "\n  ".join(f"{where}: {key!r}" for key, where in sorted(missing.items())))


# Words that are pure UI chrome - if any of these survives an English build,
# some string reached a widget without going through tr(). (This is what caught
# the workflow "wartet auf:" lists, whose labels were built untranslated.)
GERMAN_CHROME = ["wartet auf", "nicht geladen", "Durchsuchen", "Stammdaten",
                 "Rechnungsvorlage", "Emailvorlage", "Energiedaten", "erledigt", "bereit"]


def test_no_german_chrome_survives_an_english_build():
    from PyQt5 import QtWidgets
    i18n.set_language("en")
    window = _build_whole_ui()
    offenders = []
    for widget in window.findChildren(QtWidgets.QWidget):
        text = getattr(widget, "text", lambda: "")()
        if not isinstance(text, str):
            continue
        for word in GERMAN_CHROME:
            if word in text:
                offenders.append(f"{type(widget).__name__}: {text!r} (contains {word!r})")
    assert not offenders, "untranslated UI text:\n  " + "\n  ".join(offenders)
