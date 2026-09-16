# FakturaAddon

Desktop tool for an Energiegemeinschaft: turns EEG-Faktura exports into quarterly
member invoices, SEPA files for Raiffeisen Infinity, and outgoing mail.

## Install on a Mac (no Python needed)

Download `FakturaAddon-macos-arm64.dmg` from the
[releases page](https://github.com/lstark-uibk/FakturaAddon/releases), open it,
and drag **FakturaAddon** to Applications. Nothing else to install.

**The first launch needs a right-click.** The app is not signed with an Apple
Developer ID, so double-clicking it shows *"FakturaAddon cannot be opened
because it is from an unidentified developer"*. Once only:

> **Right-click** (or Ctrl-click) the app in Applications → **Open** →
> **Open** in the dialog.

macOS remembers the choice; from then on it opens normally. Signing and
notarising the build removes this step entirely — it needs an Apple Developer
account, and the release workflow already does it if the signing secrets are
present.

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

`LANGUAGE` is `de` or `en` and changes the operator's UI only — invoices and
the mails members receive stay German. Everything here is editable from
**Einstellungen** (Ctrl+,), which can also test the mail login.

**`.env` holds passwords in plain text and is gitignored. Never commit it.**

## Run

```
python main.py
```

## Tests

```
pip install pytest
python -m pytest tests -q
```
