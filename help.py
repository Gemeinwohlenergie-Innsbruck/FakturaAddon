"""Hilfe: the quarterly steps, and where each file comes from.

Kept as two whole pages (German, English) rather than a hundred tr() keys:
it is prose, and it reads better translated as prose. EEG Faktura's labels
(Vorschau Akt., EXCEL, the download icon) are quoted as that app shows them.
"""

from PyQt5.QtWidgets import QDialog, QDialogButtonBox, QTextBrowser, QVBoxLayout

import i18n

HELP_DE = """
<h2>Ablauf pro Quartal</h2>
<p>Den ganzen Ablauf je Gemeinschaft einmal durchführen (z.&nbsp;B. GWE Innsbruck, dann GEA H32).
Alle Dateien am selben Tag herunterladen &ndash; die Energiedaten werden noch Wochen nach
Quartalsende vom Netzbetreiber korrigiert.</p>

<h3>1. Daten aus EEG Faktura holen</h3>
<table cellpadding="4">
<tr><td><b>Rechnungsdaten</b></td><td>EEG Faktura &rarr; Mitglieder &rarr; <i>Abrechnungsmodus</i>, Quartal wählen.
 Für einen Test <i>Vorschau Akt.</i> und dann <i>EXCEL</i>. Für den echten Lauf <i>Abrechnung durchführen</i>
 (vergibt die Rechnungsnummern, nicht umkehrbar) und dann <i>EXCEL</i>.
 <br><b>Nicht</b> auf <i>SENDEN</i> und nicht auf <i>SEPA</i> klicken &ndash; das erledigt dieses Programm.</td></tr>
<tr><td><b>Stammdaten</b></td><td>EEG Faktura &rarr; Mitglieder &rarr; Download-Symbol oben &rarr; <i>Stammdaten</i> &rarr; <i>Export</i>.</td></tr>
<tr><td><b>Energiedaten + QoV</b></td><td>Am einfachsten hier im Programm: <i>Von EEG Faktura…</i> (nach den Stammdaten).
 Alternativ EEG Faktura &rarr; Download-Symbol &rarr; <i>Energiedaten</i>, Zeitraum = Quartal &rarr; <i>Export</i>
 (neuere Exporte enthalten keine QoV-Daten mehr; dann fehlt die Qualitätsprüfung).</td></tr>
</table>

<h3>2. Dateien laden (rechts, „Dateien laden“)</h3>
<ol>
<li><b>Rechnungsdaten</b> &rarr; <i>Durchsuchen…</i> &ndash; oben stehen dann Quartal und Anzahl der Dokumente.</li>
<li><b>EEG Faktura Stammdaten</b> &rarr; <i>Durchsuchen…</i> &ndash; legt fest, welche Gemeinschaft bearbeitet wird.</li>
<li><b>Quartalsenergiedaten</b> &rarr; <i>Von EEG Faktura…</i>, Quartal prüfen, mit dem EEG-Faktura-Konto anmelden.
 Füllt Energiedaten und QoV in einem Schritt.</li>
<li>Die Vorlagen für Rechnung und Mail werden automatisch geladen.</li>
</ol>
<p>Die Tabellen links lassen sich filtern (Feld über der Tabelle), per Klick auf die Spaltenüberschrift sortieren
und in der Breite ziehen.</p>

<h3>3. Prüfen (Ablauf, oben nach unten)</h3>
<ol>
<li><b>Daten prüfen</b> &ndash; schnelle Liste der Befunde (optional).</li>
<li><b>Energiequalität prüfen</b> &ndash; Excel-Bericht über fehlerhafte Viertelstunden (optional).</li>
<li><b>Abrechnung prüfen und freigeben</b> &ndash; Pflicht; ohne Freigabe sind die folgenden Schritte gesperrt.
 <ul>
 <li><i>Abweichung</i>: abgerechnete kWh gegen Energiedaten &ndash; sollte 0 sein. Sonst in EEG Faktura
  <i>Vorschau Akt.</i> bzw. Abrechnung neu erstellen.</li>
 <li><i>Datenqualität</i>: L3 = fehlerhaft, L0 = kein Messwert, L2 = Ersatzwert (zulässig).</li>
 <li>Jede Zeile abhaken (<i>Unauffällige abhaken</i> hilft), dann <i>Freigeben</i>.
  Freigabe trotz Fehlern braucht eine Begründung. Prüfprotokoll speichern.</li>
 <li>Wird danach eine Datei neu geladen, ist eine neue Prüfung nötig.</li>
 </ul></li>
</ol>

<h3>4. Erstellen und verschicken</h3>
<ol>
<li><b>Rechnungen erstellen</b> &ndash; Ordner wählen; eine PDF pro Mitgliedschaft. Braucht Word oder LibreOffice
 (LibreOffice dabei geschlossen lassen). Die erste PDF kurz ansehen.</li>
<li><b>Rechnungen verschicken</b> &ndash; Empfänger:innen auswählen, dann zeigt die Vorschau jede Mail.
 Erst <i>… Mails verschicken</i> sendet wirklich.</li>
<li><b>SEPA-Export für Infinity</b> &ndash; Auswahl prüfen; die Frage nach einzelnen Positionen mit <b>Nein</b>
 beantworten (verrechnet Gebühr und Gutschrift pro Person und Konto). Die zwei CSV-Dateien
 (Lastschriften, Überweisungen) in Raiffeisen Infinity hochladen.
 Mitglieder mit Einzugsart NONE werden nicht eingezogen &ndash; sie überweisen selbst.</li>
</ol>

<h3>Testmodus</h3>
<p>Einstellungen &rarr; <i>Testmodus &ndash; alle Mails an</i>: alle Rechnungsmails gehen an diese eine Adresse,
im Betreff steht das eigentliche Mitglied. Solange er an ist, steht oben TESTMODUS.
Vor dem echten Lauf das Feld leeren.</p>

<h3>Wenn etwas nicht klappt</h3>
<ul>
<li><b>Nur .docx statt PDF</b>: Word oder LibreOffice installieren; LibreOffice einmal von Hand öffnen und
 schließen. Die Meldung nennt den genauen Grund.</li>
<li><b>Mail: Anmeldung oder Zertifikat</b>: Einstellungen &rarr; <i>Verbindung testen</i>.</li>
<li><b>„Schon exportiert“ beim SEPA-Export</b>: diese Dokumente waren schon in einem Export.
 Nach einem Testlauf ohne Bankupload kann
 <code>~/Library/Application Support/FakturaAddon/ledger.jsonl</code> gelöscht werden.</li>
<li><b>Zählpunkte ohne Mitglied</b> beim Laden der Energiedaten: Stammdaten sind älter als ein neues
 Mitglied &ndash; neu herunterladen.</li>
</ul>
"""

HELP_EN = """
<h2>Each quarter</h2>
<p>Run the whole sequence once per community (e.g. GWE Innsbruck, then GEA H32).
Download every file on the same day &ndash; grid operators keep correcting energy data for weeks
after a quarter ends.</p>

<h3>1. Get the data from EEG Faktura</h3>
<table cellpadding="4">
<tr><td><b>Invoice data</b></td><td>EEG Faktura &rarr; members &rarr; <i>Abrechnungsmodus</i>, choose the quarter.
 For a test: <i>Vorschau Akt.</i>, then <i>EXCEL</i>. For the real run: <i>Abrechnung durchführen</i>
 (assigns invoice numbers, cannot be undone), then <i>EXCEL</i>.
 <br>Do <b>not</b> click <i>SENDEN</i> or <i>SEPA</i> &ndash; this app does both.</td></tr>
<tr><td><b>Member data</b></td><td>EEG Faktura &rarr; members &rarr; download icon at the top &rarr; <i>Stammdaten</i> &rarr; <i>Export</i>.</td></tr>
<tr><td><b>Energy data + QoV</b></td><td>Easiest in this app: <i>From EEG Faktura…</i> (after loading the member data).
 Or EEG Faktura &rarr; download icon &rarr; <i>Energiedaten</i>, period = the quarter &rarr; <i>Export</i>
 (newer exports no longer contain QoV data, so the quality check is then missing).</td></tr>
</table>

<h3>2. Load the files ("Load files", right-hand side)</h3>
<ol>
<li><b>Invoice data</b> &rarr; <i>Browse…</i> &ndash; the header then shows the quarter and the document counts.</li>
<li><b>EEG Faktura member data</b> &rarr; <i>Browse…</i> &ndash; this decides which community you are working on.</li>
<li><b>Quarterly energy data</b> &rarr; <i>From EEG Faktura…</i>, check the quarter, log in with your EEG Faktura
 account. Fills energy data and QoV in one step.</li>
<li>The invoice and mail templates load automatically.</li>
</ol>
<p>The tables on the left can be filtered (box above each table), sorted by clicking a column header,
and resized by dragging.</p>

<h3>3. Check (workflow, top to bottom)</h3>
<ol>
<li><b>Check data</b> &ndash; a quick list of findings (optional).</li>
<li><b>Check energy quality</b> &ndash; an Excel report of faulty quarter-hours (optional).</li>
<li><b>Review and approve billing</b> &ndash; required; the later steps stay locked until it is done.
 <ul>
 <li><i>Difference</i>: billed kWh against the energy data &ndash; should be 0. Otherwise refresh the preview
  or re-run the billing in EEG Faktura.</li>
 <li><i>Data quality</i>: L3 = faulty, L0 = no reading, L2 = substitute value (acceptable).</li>
 <li>Tick every row (<i>Tick unremarkable ones</i> helps), then <i>Approve</i>.
  Approving despite errors needs a reason. Save the review record.</li>
 <li>Reloading any file afterwards needs a new review.</li>
 </ul></li>
</ol>

<h3>4. Create and send</h3>
<ol>
<li><b>Create invoices</b> &ndash; choose a folder; one PDF per membership. Needs Word or LibreOffice
 (keep LibreOffice closed meanwhile). Look at the first PDF.</li>
<li><b>Send invoices</b> &ndash; choose recipients; the preview then shows every mail.
 Nothing is sent until <i>Send … mails</i>.</li>
<li><b>SEPA export for Infinity</b> &ndash; check the selection; answer <b>No</b> to the question about separate
 positions (nets fee against credit per person and account). Upload the two CSV files
 (direct debits, transfers) to Raiffeisen Infinity.
 Members with Einzugsart NONE are not debited &ndash; they pay by transfer.</li>
</ol>

<h3>Test mode</h3>
<p>Settings &rarr; <i>Test mode &ndash; all mail to</i>: every invoice mail goes to that one address, with the
intended member in the subject. While it is on, the header says TEST MODE.
Clear the field before the real run.</p>

<h3>If something goes wrong</h3>
<ul>
<li><b>Only .docx, no PDF</b>: install Word or LibreOffice; open LibreOffice once by hand and close it.
 The message gives the exact reason.</li>
<li><b>Mail: login or certificate</b>: Settings &rarr; <i>Test connection</i>.</li>
<li><b>"Already exported" in the SEPA export</b>: those documents were in an earlier export.
 After a test run that never went to the bank, delete
 <code>~/Library/Application Support/FakturaAddon/ledger.jsonl</code>.</li>
<li><b>Metering points without a member</b> when loading energy data: the member data is older than a new
 member &ndash; download it again.</li>
</ul>
"""


class HelpDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        english = i18n.current_language() == "en"
        self.setWindowTitle("Help" if english else "Hilfe")
        self.resize(780, 720)
        layout = QVBoxLayout(self)
        page = QTextBrowser()
        page.setOpenExternalLinks(True)
        page.setHtml(HELP_EN if english else HELP_DE)
        layout.addWidget(page, 1)
        buttons = QDialogButtonBox(QDialogButtonBox.Close)
        buttons.rejected.connect(self.reject)
        buttons.accepted.connect(self.accept)
        layout.addWidget(buttons)
