"""Operator UI in German or English.

German is the source language: the German text *is* the lookup key, so
`tr("Daten prüfen")` returns that string unchanged when the UI is German and
needs no catalogue entry. Only English needs a table. That keeps the German
path impossible to break and keeps the call sites readable.

Scope is deliberately the operator's UI only. Invoices, invoice chart labels
and the text of the mails stay German whatever the operator picks - they go to
Austrian members, and their language has nothing to do with who is running the
app. Translating them along with the menus would be a bug, not a feature.

Placeholders use str.format, so counts are passed as keyword arguments:

    tr("{n} Mitglied(er) ohne IBAN.", n=3)
"""

LANGUAGES = {"de": "Deutsch", "en": "English"}
DEFAULT_LANGUAGE = "de"

_language = DEFAULT_LANGUAGE
_used_keys = set()      # every key tr() has been asked for, for the coverage test


def set_language(code):
    global _language
    _language = code if code in LANGUAGES else DEFAULT_LANGUAGE
    return _language


def current_language():
    return _language


def tr(text, **kwargs):
    """Translate `text` into the current UI language and fill placeholders."""
    _used_keys.add(text)
    if _language != "de":
        text = EN.get(text, text)
    return text.format(**kwargs) if kwargs else text


def used_keys():
    return set(_used_keys)


def reset_usage():
    """Forget which keys have been asked for (used to scope the coverage test)."""
    _used_keys.clear()


def missing_translations():
    """Keys tr() has been asked for that have no English entry."""
    return {k for k in _used_keys if k not in EN}


EN = {
    # --- window, menus -----------------------------------------------------
    "Faktura Infinity Addon": "Faktura Infinity Addon",
    "Einstellungen": "Settings",
    "Einstellungen…": "Settings…",
    "Rechnungen erstellen und verschicken": "Create and send invoices",
    "Infinity Export": "Infinity export",
    "Schließen": "Quit",

    # --- menu entries ------------------------------------------------------
    "Daten prüfen": "Check data",
    "Überprüfe die Qualität der Energiedaten": "Check energy data quality",
    "Erstelle alle Rechnungen": "Create all invoices",
    "Verschicke die Rechnungen per Mail": "Send the invoices by mail",
    "Exportiere .csv Datei für Raiffeisen Infinity": "Export .csv file for Raiffeisen Infinity",

    # --- header, sections --------------------------------------------------
    "Keine Rechnungsdaten geladen - zuerst rechts eine Datei laden.":
        "No invoice data loaded - load a file on the right first.",
    "Abrechnung {year} Q{quarter}  ·  {debit} Rechnungen, {credit} Gutschriften  ·  {energy}":
        "Billing {year} Q{quarter}  ·  {debit} invoices, {credit} credit notes  ·  {energy}",
    "Energiedaten geladen": "energy data loaded",
    "keine Energiedaten": "no energy data",
    "Rechnungsdaten KonsumentInnen": "Invoice data - consumers",
    "Rechnungsdaten ProduzentInnen": "Invoice data - producers",
    "Energiedaten": "Energy data",
    "Dateien laden": "Load files",
    "Ablauf": "Workflow",

    # --- file panel --------------------------------------------------------
    "Durchsuchen…": "Browse…",
    "nicht geladen": "not loaded",
    "{label} auswählen und laden": "Select and load {label}",
    "Rechnungsdaten": "Invoice data",
    "EEG Faktura Stammdaten": "EEG Faktura member data",
    "Quartalsenergiedaten": "Quarterly energy data",
    "Quartalsenergiedaten QoV": "Quarterly energy data QoV",
    "Rechnungen Vorlage": "Invoice template",
    "Emails Vorlage": "Email template",

    # --- workflow panel ----------------------------------------------------
    "Energiequalität prüfen": "Check energy quality",
    "Rechnungen erstellen": "Create invoices",
    "Rechnungen verschicken": "Send invoices",
    "SEPA-Export für Infinity": "SEPA export for Infinity",
    "(optional)": "(optional)",
    "wartet auf: {missing}": "waiting for: {missing}",
    "erledigt": "done",
    "bereit": "ready",

    # --- file dialogs ------------------------------------------------------
    "Importiere Rechnungen von EEG Faktura": "Import invoices from EEG Faktura",
    "Wähle die Stammdaten von EEG Faktura aus": "Select the EEG Faktura member data",
    "Wähle die Energiedaten für dieses Quartal aus": "Select this quarter's energy data",
    "Wähle die QoV-Energiedaten für dieses Quartal aus": "Select this quarter's QoV energy data",
    "Wähle die Vorlage für die Rechnungen aus": "Select the invoice template",
    "Wähle die Emailvorlage aus": "Select the email template",
    "Word Dokument (*.docx)": "Word document (*.docx)",
    "HTML Datei (*.html *.htm)": "HTML file (*.html *.htm)",
    "Wo sollen die Rechnungen gespeichert werden?": "Where should the invoices be saved?",
    "In welchem Ordner sind die ganzen Rechnungen gespeichert?":
        "Which folder are the invoices saved in?",
    "Wo soll ich den Überprüfungsreport hinspeichern?": "Where should the check report be saved?",
    "Wähle Speicherort für Export für SEPA Lastschrift aus":
        "Choose where to save the SEPA direct debit export",
    "Wähle Speicherort für Export für Überweisungen aus":
        "Choose where to save the credit transfer export",

    # --- SEPA export window ------------------------------------------------
    "Exportiere .csv für SEPA": "Export .csv for SEPA",
    "Name": "Name",
    "Betrag [€]": "Amount [€]",
    "Alle auswählen": "Select all",
    "Keine": "None",
    "{n} Positionen": "{n} items",
    "Lastschriften (Einzug)": "Direct debits (collected)",
    "Überweisungen (Gutschrift)": "Transfers (credited)",
    "Netto": "Net",
    "Exportieren": "Export",
    "Keine Auswahl": "Nothing selected",
    "Es ist niemand ausgewählt - es wird nichts exportiert.":
        "Nobody is selected - nothing will be exported.",
    "Speichern fehlgeschlagen": "Save failed",
    "{what} konnten nicht gespeichert werden:\n{path}\n\n{error}":
        "{what} could not be saved:\n{path}\n\n{error}",
    "Lastschriften": "Direct debits",
    "Überweisungen": "Transfers",

    # --- invoice run -------------------------------------------------------
    "Rechnungen werden erstellt": "Creating invoices",
    "Rechnungen werden vorbereitet...": "Preparing invoices...",
    "Abbrechen": "Cancel",
    "Abbruch nach der laufenden Rechnung...": "Stopping after the current invoice...",
    "Fertig": "Done",
    "Alle Rechnungen wurden erstellt.": "All invoices were created.",
    "Mit Anmerkungen abgeschlossen": "Finished with remarks",
    "{n} Punkt(e) brauchen deine Aufmerksamkeit.": "{n} item(s) need your attention.",

    # --- mail run ----------------------------------------------------------
    "Keine Empfänger:innen": "No recipients",
    "Zu den geladenen Rechnungen wurde niemand in den Stammdaten gefunden.":
        "Nobody in the member data matches the loaded invoices.",
    "Es wurde niemand ausgewählt.": "Nobody was selected.",
    "Anmeldung fehlgeschlagen": "Login failed",
    "Anmeldung beim Mailserver nicht möglich.": "Could not log in to the mail server.",
    "Das Passwort wurde abgelehnt. Bitte in den Einstellungen prüfen.":
        "The password was rejected. Please check it in the settings.",
    "Mailversand abgeschlossen": "Mail run finished",
    "Verschickt: {n}": "Sent: {n}",
    "Ohne PDF übersprungen: {n}": "Skipped, no PDF: {n}",
    "Fehlgeschlagen: {n}": "Failed: {n}",
    "Verschickt an:": "Sent to:",
    "Keine Rechnung gefunden:": "No invoice found:",
    "Fehler:": "Errors:",

    # --- send preview ------------------------------------------------------
    "Rechnungen verschicken ": "Send invoices ",
    "1 Mail": "1 mail",
    "{n} Mails": "{n} mails",
    "{mails} werden verschickt": "{mails} will be sent",
    "{mails} werden verschickt · {skipped} übersprungen (keine PDF-Rechnung gefunden)":
        "{mails} will be sent · {skipped} skipped (no PDF invoice found)",
    "{mails} verschicken": "Send {mails}",
    "Empfänger:in": "Recipient",
    "Mailadresse": "Mail address",
    "Rechnung": "Invoice",
    "✓ Rechnung gefunden": "✓ invoice found",
    "✗ keine Rechnung": "✗ no invoice",
    "{file} nicht gefunden": "{file} not found",
    "Vorschau": "Preview",
    "Vorschau nicht möglich": "Preview not possible",
    "Betreff: {subject}": "Subject: {subject}",
    "Anhang: {file}": "Attachment: {file}",
    "Für diese Person wurde keine PDF-Rechnung gefunden - es wird nichts verschickt.":
        "No PDF invoice was found for this person - nothing will be sent.",

    # --- validation --------------------------------------------------------
    "Datenprüfung": "Data check",
    "Fehler": "Error",
    "Warnung": "Warning",
    "Hinweis": "Note",
    "Bereich": "Area",
    "Befund": "Finding",
    "Bericht kopieren": "Copy report",
    "Keine Probleme gefunden.": "No problems found.",
    "{n} Fehler": "{n} errors",
    "{n} Warnung(en)": "{n} warning(s)",
    "{n} Hinweis(e)": "{n} note(s)",
    "Die Datenprüfung meldet {n} Fehler.": "The data check reports {n} errors.",
    "Trotzdem fortfahren?": "Continue anyway?",
    "Abrechnungszeitraum": "Billing period",
    "Beträge": "Amounts",
    "Doppelte Namen": "Duplicate names",
    "IBAN": "IBAN",
    "Mailadressen": "Mail addresses",
    "Namen": "Names",
    "SEPA-Mandat": "SEPA mandate",
    "Stammdaten der EEG": "Community master data",
    "Der Abrechnungszeitraum konnte nicht aus den Rechnungsdaten gelesen werden.":
        "The billing period could not be read from the invoice data.",
    "Der Zeitraum der Energiedaten konnte nicht bestimmt werden.":
        "The period covered by the energy data could not be determined.",
    "Die Energiedaten ({from_} - {to}) liegen komplett außerhalb des Abrechnungsquartals "
    "{year} Q{quarter} ({start} - {end}). Vermutlich wurde die falsche Datei geladen.":
        "The energy data ({from_} - {to}) falls entirely outside billing quarter "
        "{year} Q{quarter} ({start} - {end}). The wrong file was probably loaded.",
    "Die Energiedaten decken {year} Q{quarter} nicht ganz ab: vorhanden {from_} - {to}, "
    "erwartet {start} - {end}.":
        "The energy data does not fully cover {year} Q{quarter}: present {from_} - {to}, "
        "expected {start} - {end}.",
    "{n} Name(n) aus den Rechnungsdaten kommen in den Energiedaten nicht vor. "
    "Diese Rechnungen bekommen keine Grafik.":
        "{n} name(s) from the invoice data do not appear in the energy data. "
        "Those invoices will have no chart.",
    "{n} Mitglied(er) ohne IBAN.": "{n} member(s) without an IBAN.",
    "{n} IBAN(s) mit ungültiger Prüfsumme.": "{n} IBAN(s) with an invalid checksum.",
    "{n} Lastschrift(en) ohne {field}. Die Bank weist diese zurück.":
        "{n} direct debit(s) without {field}. The bank will reject these.",
    "Mandatsreferenz": "a mandate reference",
    "Mandatsausstellungsdatum": "a mandate date",
    "{n} Name(n) kommen mit mehr als einer IBAN vor. Der SEPA-Export fasst nach Namen "
    "zusammen, diese Zahlungen gingen auf ein einziges Konto.":
        "{n} name(s) appear with more than one IBAN. The SEPA export groups by name, so "
        "these payments would all go to a single account.",
    "{n} Mitglied(er) mit einer Position von 0,00 €.": "{n} member(s) with a 0.00 € item.",
    "{n} Position(en) mit unlesbarem Betrag.": "{n} item(s) with an unreadable amount.",
    "{n} Mitglied(er) mit Rechnung haben keine Mailadresse.":
        "{n} member(s) with an invoice have no mail address.",
    "{n} Mailadresse(n) sehen nicht wie Adressen aus.":
        "{n} mail address(es) do not look like addresses.",
    "{n} Adresse(n) kommen mehrfach vor - diese Personen bekommen mehrere Mails.":
        "{n} address(es) appear more than once - those people will get several mails.",
    "{n} Feld(er) fehlen in den Stammdaten und bleiben auf der Rechnung leer.":
        "{n} field(s) are missing from the master data and will print blank on the invoice.",

    # --- settings dialog ---------------------------------------------------
    "Mailadresse:": "Mail address:",
    "Mail-Passwort:": "Mail password:",
    "IMAP-Server (Posteingang):": "IMAP server (incoming):",
    "SMTP-Server (Versand):": "SMTP server (outgoing):",
    "Port:": "Port:",
    "Basisordner:": "Home folder:",
    "Name der EEG:": "Community name:",
    "Rechnungsvorlage:": "Invoice template:",
    "Emailvorlage:": "Email template:",
    "Sprache:": "Language:",
    "anzeigen": "show",
    "wird nur lokal in .env gespeichert": "stored locally in .env only",
    "Zugangsdaten werden unverschlüsselt in .env neben dem Programm gespeichert. "
    "Diese Datei niemals weitergeben oder committen.":
        "Credentials are stored unencrypted in .env next to the program. "
        "Never share or commit that file.",
    "Verbindung testen": "Test connection",
    "Teste Verbindung…": "Testing connection…",
    "Basisordner auswählen": "Select home folder",
    "Datei auswählen": "Select file",
    "Die Sprache wird beim nächsten Start übernommen.":
        "The language takes effect the next time the app starts.",
    "Sprache geändert": "Language changed",

    # --- errors, files -----------------------------------------------------
    "Datei nicht lesbar": "File not readable",
    "Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)":
        "The selected file is not readable (is it in the right format?)",
    "Rechnungsvorlage": "Invoice template",
    "Emailvorlage": "Email template",
    "Die Rechnungsvorlage konnte nicht geladen werden:\n{path}\n\n{error}":
        "The invoice template could not be loaded:\n{path}\n\n{error}",
    "Die Emailvorlage konnte nicht geladen werden:\n{path}\n\n{error}":
        "The email template could not be loaded:\n{path}\n\n{error}",
    "Unerwarteter Fehler": "Unexpected error",
    "Es ist ein unerwarteter Fehler aufgetreten.\n\n{type}: {message}":
        "An unexpected error occurred.\n\n{type}: {message}",
    "Über 'Details anzeigen' bekommst du den vollen Fehlerbericht - "
    "bitte diesen beim Melden mitschicken.":
        "'Show Details' gives you the full error report - please include it when reporting.",
    "Fehlerbericht kopieren": "Copy error report",
    "Weiter": "Continue",
    "Report gespeichert": "Report saved",
    "Der Überprüfungsreport wurde gespeichert:\n{path}\n\nEr konnte nicht automatisch "
    "geöffnet werden.":
        "The check report was saved:\n{path}\n\nIt could not be opened automatically.",
    "Rechnungen fehlen": "Invoices missing",
    "Für {missing} von {total} Personen wurde keine PDF-Rechnung gefunden.\n\n"
    "Soll ich die übrigen {rest} trotzdem verschicken?":
        "No PDF invoice was found for {missing} of {total} people.\n\n"
        "Send the remaining {rest} anyway?",
    "Überprüfung durchgeführt. \nAlle QoV Energiedaten sind mindestens L2":
        "Check complete. \nAll QoV energy data is at least L2",
    "{done} von {total} Zeilen": "{done} of {total} rows",
    "… {hidden} weitere Zeilen nicht angezeigt ({total} gesamt)":
        "… {hidden} more rows not shown ({total} total)",
    "({done}/{total}) Rechnung für {name}...": "({done}/{total}) Invoice for {name}...",
    "{n} von {total} Empfänger:innen ausgewählt": "{n} of {total} recipients selected",

    # --- data still missing ------------------------------------------------
    "Für diesen Schritt müssen noch folgende Daten eingelesen werden:":
        "This step still needs the following data to be loaded:",
    "Email Template": "Email template",
    "Energiedaten QoV": "Energy data QoV",
    "Report": "Report",
    "Stammdaten": "Member data",
    "Frage": "Question",
    "Willst du jede Positionen einzeln ausweisen \n(z.b. eine eigene Überweisung für "
    "Mitgliedsbeitrag und Stromkosten)??":
        "Do you want every item listed separately \n(e.g. a separate transfer for "
        "membership fee and electricity)?",
}
