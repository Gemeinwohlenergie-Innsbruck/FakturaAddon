# FakturaAddon

Desktop tool for an Energiegemeinschaft: turns EEG-Faktura exports into quarterly
member invoices, SEPA files for Raiffeisen Infinity, and outgoing mail.

## Install on a Mac (no Python needed)

Download `FakturaAddon-macos-arm64.dmg` from the
[releases page](https://github.com/lstark-uibk/FakturaAddon/releases), open it,
and drag **FakturaAddon** to Applications. Nothing else to install.

**The first launch needs one extra step.** The app is not signed with an Apple
Developer ID, so macOS refuses to open it until you say otherwise.

On **macOS 15 (Sequoia) and later**, including macOS 26, Control-clicking the
app no longer works — Apple removed that override. Instead:

> Double-click the app and dismiss the warning, then open
> **System Settings → Privacy & Security**, scroll to **Security**, and click
> **Open Anyway** next to the message about FakturaAddon. Authenticate, then
> open the app again.

Or, equivalently, from a terminal:

```
xattr -dr com.apple.quarantine /Applications/FakturaAddon.app
```

That removes the download quarantine flag, after which the app opens normally.
Either way it is a one-off per installed copy — a new `.dmg` is quarantined
again.

On **macOS 14 and earlier**, Control-click → Open → Open still works.

Signing and notarising the build removes this step entirely for everyone. It
needs an Apple Developer account, and the release workflow already does it
when the signing secrets are configured.

The `.dmg` is built for **Apple Silicon** (M1 and later). An Intel Mac needs a
separate build on a `macos-13` runner.

### PDF invoices need Word or LibreOffice

`docx2pdf` drives Microsoft Word, and there is no way to make PDFs without
either it or LibreOffice installed. Without one, invoices are saved as `.docx`
only, the run reports that for each member, and the mail step then finds no
PDFs to attach. Free option:

```
brew install --cask libreoffice
```

### Where settings are kept

`~/Library/Application Support/FakturaAddon/.env`, so they survive upgrades.
It holds the mail password in plain text — the same file the app warns about
in Einstellungen.

## Install from source (developers)

Requires **Python 3.12 or newer** (the code uses PEP 701 f-strings).

```
pip install -r requirements.txt
```

PDF export additionally needs either Microsoft Word (via `docx2pdf`) or
LibreOffice (`soffice`) on PATH.

## Configure

Settings live in a `.env` file next to `main.py`. On first start the settings
dialog opens and writes it for you; you can also create it by hand:

```
MAIL_ADDRESS=...
MAIL_IMAP_SERVER=...
MAIL_PASSWORD=...
HOME_DIRECTORY=...
EEG_NAME=...
TEMPLATE_EXPORT_INVOICE=templates/template_invoice_clean.docx
TEMPLATE_EMAIL=templates/email_template_clean.html
MAIL_SMTP_SERVER=...
MAIL_SMTP_PORT=587
LANGUAGE=de
```

`MAIL_TEST_ADDRESS` (Einstellungen → *Testmodus – alle Mails an*) sends every
invoice mail to that one address instead of the members. The subject names
the member it was meant for, the send preview and the window header say
TESTMODUS, and test runs are neither filed in *Gesendete_Rechnungen* nor
recorded as sent. Leave it empty for real runs.

`LANGUAGE` is `de` or `en` and changes the operator's UI only — invoices and
the mails members receive stay German. Everything here is editable from
**Einstellungen** (Ctrl+,), which can also test the mail login.

**`.env` holds passwords in plain text and is gitignored. Never commit it.**

## Energy data straight from EEG Faktura

Instead of downloading the Energy Report and loading it twice (Energiedaten
and QoV), load the **Stammdaten** first and click **Von EEG Faktura…** on the
Quartalsenergiedaten row. Pick the quarter and log in with your EEG Faktura
account; both rows are filled from one download.

- The community is taken from the loaded Stammdaten (its first sheet and
  `Gemeinschafts-ID`), so for a second community just load that community's
  Stammdaten. Energy data and member names can never come from two
  different communities.
- The API returns no names. Each metering point is matched to its member by
  `Zählpunkt` in the Stammdaten, and named exactly as the Energy Report would
  name it. Metering points with data but no Stammdaten row are listed and
  left out; usually that means the Stammdaten export is older than a new
  member.
- The quarter is cut at midnight at its end. The API returns the whole of
  the end day, which would otherwise bill a day of the next quarter.
- Cells are left empty exactly where the export leaves them empty: no
  reading delivered (quality L0), or outside the member's `aktiviert` –
  `deaktiviert` period. A meter that changed hands gets columns for each
  holder. Rebuilding a real export this way reproduces it cell for cell.
- Quality comes per value (L0 none, L1 measured, L2 substitute, L3 faulty).
  Newer EEG Faktura versions drop the *QoV Log* sheet from the Energy Report
  and mark quality by cell colour instead, which the Excel import cannot
  read; the API import does not depend on it.

Energy data for a quarter keeps changing for weeks after it ends, as grid
operators send corrected allocations. Fetch it when you create the invoices,
not earlier, and after the billing run you are invoicing.

Invoice data (Rechnungsdaten) and Stammdaten still have to be downloaded by
hand. Those API routes need a Keycloak token, and EEG Faktura does not allow
desktop apps to log in for one.

`tools/probe_eegfaktura_api.py` and `tools/compare_api_with_export.py` are
read-only checks of which routes your login reaches and that the API import
matches an Excel export cell by cell (download the export the same day).
Both ask for the password without echoing it and print no member data.

Two quirks of the EEG Faktura server are handled: it answers every failed
login with 403, and it decodes Basic credentials as URL-safe base64, which
breaks some passwords containing `?`, `>`, `~` or non-ASCII characters. The
app retries those correctly. Passwords containing `:` cannot work with the
API at all, and the app says so.

## Checking before anyone is charged

**Abrechnung prüfen und freigeben** is a required step. Until it is done,
and again whenever any file is reloaded, the app will not create invoices,
send mail or export SEPA files. It shows every document next to what was
checked against it, and every document has to be ticked before approval.
Approving despite errors needs a written reason. The approval and the
review record (an Excel file you can save) say who approved which data and
when.

What is checked, beyond missing IBANs, mandates and mail addresses:

- **Every euro re-derives.** Each position is recomputed the way
  EEG Faktura's billing computes it (kWh × price in cent, discount, VAT,
  each rounded half-up to the cent). Each document's total must equal the
  sum of its positions: the screen shows the total, but the SEPA file moves
  the sum.
- **Billed kWh match the energy data, per metering point.** Consumers are
  billed their *Eigendeckung*, producers *Gesamte Erzeugung − Überschuss*.
  A difference usually means the grid operator corrected the data after the
  billing run, so re-run the billing in EEG Faktura.
- **The billed quarter-hours were measured.** L3 (faulty) and L0 (no
  reading) in a billed meter's data are errors; L2 (substitute values) is
  noted.
- **Invoices, member list and energy data belong to one community.** This
  matters with two communities on one computer.
- **Bank details are still current.** An IBAN changed since the billing run
  would be debited or paid on the old account.
- **Nothing is collected twice.** Each SEPA export and mail run is recorded
  in `ledger.jsonl` next to the settings. Exporting a document again needs
  an explicit confirmation.

## Run

```
python main.py
```

## Tests

```
pip install pytest
python -m pytest tests -q
```
