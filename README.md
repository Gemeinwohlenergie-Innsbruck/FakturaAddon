# FakturaAddon

Desktop tool for an Energiegemeinschaft: turns EEG-Faktura exports into quarterly
member invoices, SEPA files for Raiffeisen Infinity, and outgoing mail.

## Install

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
