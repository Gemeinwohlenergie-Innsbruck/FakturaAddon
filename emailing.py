from bs4 import BeautifulSoup
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QPushButton,
                             QLabel, QScrollArea, QTextEdit, QTextBrowser, QFormLayout,
                             QLineEdit, QGridLayout, QCheckBox, QDialog, QSplitter,
                             QTableWidget, QTableWidgetItem, QAbstractItemView, QHeaderView)
from PyQt5.QtCore import Qt, QUrl
from PyQt5.QtGui import QBrush, QColor
import email
from email.header import decode_header
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.message import EmailMessage
from smtplib import SMTP
import numpy as np
import smtplib, ssl
import os
import imaplib
from datetime import datetime

from i18n import tr
import theme
from tables import SortableItem


class MailSelection(QWidget):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self,title = "",imap = "",functiononnewmemberparse=""):
        super().__init__()
        self.setWindowTitle(title)

        print("Login Prompt")
        self.resize(800, 400)
        self.move(200,200)
        self.imap = imap
        self.functiononnewmemberparse = functiononnewmemberparse
        layout = QVBoxLayout()
        self.email_list = QListWidget()
        self.nr_messagesperpage = 15
        self.start = 0
        self.finish = self.start+self.nr_messagesperpage
        status, messages = self.imap.select("INBOX")
        self.nr_messages = int(messages[0])  # total number of emails
        self.Mailcheckwindow = None

        email_subjects = self.get_mail_subjects(self.start,self.finish)
        self.reload_list(email_subjects)
        # mailmessage = self.get_mail_messages(2,anmeldungstyp="Produzent:in")


        self.moredown = QPushButton("Mehr")
        self.moredown.pressed.connect(lambda: self.load_more_messages("down") )
        self.moreup = QPushButton("Mehr")
        self.moreup.pressed.connect(lambda: self.load_more_messages("up") )
        self.status = QLabel("")
        self.okbut = QPushButton("OK")
        self.okbut.pressed.connect(lambda: self.confirm_selection(self.email_list.currentItem()))

        layout.addWidget(self.moreup)
        layout.addWidget(self.email_list)
        layout.addWidget(self.moredown)
        layout.addWidget(self.status)
        layout.addWidget(self.okbut)

        self.setLayout(layout)
        self.email_list.itemDoubleClicked.connect(self.confirm_selection)
    def load_more_messages(self,dir = "down"):
        if dir == "down":
            # Was `>= 0`, which is always true, so paging ran off the end of
            # the mailbox into non-positive sequence numbers and an IMAP error.
            if self.finish >= self.nr_messages:
                return
            self.start = self.start + self.nr_messagesperpage
            self.finish = min(self.finish + self.nr_messagesperpage, self.nr_messages)
        if dir == "up":
            if self.start - self.nr_messagesperpage >= 0:
                self.start = self.start - self.nr_messagesperpage
                self.finish = self.finish - self.nr_messagesperpage
            else: return
        email_subjects= self.get_mail_subjects(self.start,self.finish)
        self.reload_list(email_subjects)

    def reload_list(self,email_subjects):
        self.email_list.clear()
        for subject, sender in email_subjects:
            self.email_list.addItem(f"{sender}:\t{subject}")
    def confirm_selection(self,item):
        if item:
            anmeldungstyp = "Konsument:in"
            if ('Neuanmeldung Stromkonsument:in' in item.text()):
                anmeldungstyp = "Konsument:in"
            elif ('Neuanmeldung Stromproduzent:in' in item.text()):
                anmeldungstyp = "Produzent:in"
            else:
                self.status.setText("Email war keine Neuanmeldung")

                return
            print(type(self.email_list.row(item)),item.text())
            row = self.email_list.row(item)
            message = self.get_mail_messages(row,anmeldungstyp)
            self.close()
        else:
            print("No item selected")
            self.status.setText("Kein Email ausgewählt")
    def get_mail_messages(self,nrmailfromtop,anmeldungstyp):
        res, msg = self.imap.fetch(str(self.nr_messages - nrmailfromtop), "(RFC822)")
        for response in msg:
            if isinstance(response, tuple):
                # parse a bytes email into a message object
                msg = email.message_from_bytes(response[1])
                if msg.is_multipart():
                    for part in msg.walk():
                        # extract content type of email
                        content_type = part.get_content_type()
                        try:
                            # get the email body
                            body = part.get_payload(decode=True).decode()
                        except:
                            pass
                        if content_type == "text/plain":
                            # print text/plain emails and skip attachments
                            print(body)
        self.Mailcheckwindow = MailCheckWindow(body,title="Datencheck", functionnewmemberparse = self.functiononnewmemberparse, anmeldungstyp=anmeldungstyp)
        self.Mailcheckwindow.show()
        self.close()
        return body

    def get_mail_subjects(self,start,finish):
        email_subjects = []

        for i in range(self.nr_messages-start, self.nr_messages - finish, -1):
            # fetch the email message by ID
            res, msg = self.imap.fetch(str(i), "(RFC822)")
            # print(res,msg)
            for response in msg:
                if isinstance(response, tuple):
                    # parse a bytes email into a message object
                    msg = email.message_from_bytes(response[1])
                    # decode the email subject
                    subject, encoding = decode_header(msg["Subject"])[0]
                    if isinstance(subject, bytes):
                        # if it's a bytes, decode to str
                        subject = subject.decode(encoding)
                    # decode email sender
                    From, encoding = decode_header(msg.get("From"))[0]
                    if isinstance(From, bytes):
                        From = From.decode(encoding)
                    email_subjects.append([subject, From])

        return email_subjects

class MailCheckWindow(QWidget):
    def __init__(self,mailtext,title = "", functionnewmemberparse="",anmeldungstyp = ""):
        self.anmeldungstyp = anmeldungstyp
        self.functionnewmemberparse = functionnewmemberparse
        super().__init__()
        self.setWindowTitle(title)
        self.resize(1000, 600)
        self.move(30,30)
        self.mailtext = mailtext
        self.parsed_data = {}
        self.parse_text()
        layout = QVBoxLayout()
        hlayout1 = QHBoxLayout()
        hlayout2 = QHBoxLayout()
        self.mailtext_window = QTextEdit(mailtext)
        self.mailtext_window.setReadOnly(True)
        self.scroll = QScrollArea()             # Scroll Area which contains the widgets, set as the centralWidget
        self.widget = QWidget()
        self.parsedatawindow = QFormLayout()
        for key in self.parsed_data:
            self.parsedatawindow.addRow(key,QLineEdit(self.parsed_data[key]))

        self.widget.setLayout(self.parsedatawindow)

        self.scroll.setWidgetResizable(True)
        self.scroll.setWidget(self.widget)

        self.okbut = QPushButton("OK")
        self.okbut.pressed.connect(self.collect_parsed)

        layout.addLayout(hlayout1)
        layout.addLayout(hlayout2)
        hlayout1.addWidget(QLabel(f"Email zur Anmeldung von {self.anmeldungstyp}:"))
        hlayout2.addWidget(self.mailtext_window)
        hlayout1.addWidget(QLabel("Daten aus Email geparsed"))
        hlayout2.addWidget(self.scroll)
        hlayout1.setStretch(0,1)
        hlayout1.setStretch(1,2)
        hlayout2.setStretch(0,1)
        hlayout2.setStretch(1,2)

        layout.addWidget(self.okbut)
        self.setLayout(layout)

    def parse_text(self):
        soup = BeautifulSoup(self.mailtext, "html.parser")

        # Extract text content split by <br> tags
        lines = [line.strip() for line in soup.get_text(separator='\n').split('\n') if line.strip()]

        for line in lines:
            if ' : ' in line:
                key, value = line.split(' : ', 1)  # Split into key and value
                self.parsed_data[key.strip()] = value.strip()

    def collect_parsed(self):
        print("I continue with the parsed email")
        self.parsed_data["Anmeldungstyp"] = self.anmeldungstyp
        self.functionnewmemberparse(data = self.parsed_data)
        print(self.parsed_data)
        self.close()


class LoginPrompt(QWidget):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self,function_try_login,title = ""):
        super().__init__()
        self.setWindowTitle(title)

        print("Login Prompt")
        self.function_try_login = function_try_login
        self.resize(200, 100)
        self.move(300,300)
        layout = QVBoxLayout()
        label = QLabel("Nextcloud Login")
        self.user = QLineEdit()
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        line1 = QHBoxLayout()
        line1.addWidget(QLabel("Benutzername"))
        line1.addWidget(self.user)
        line2 = QHBoxLayout()
        line2.addWidget(QLabel("Passwort"))
        line2.addWidget(self.pw)
        okbutton = QPushButton("OK")
        okbutton.pressed.connect(self.okbuttonpress)
        self.status = QLabel("")

        layout.addWidget(label)
        layout.addLayout(line1)
        layout.addLayout(line2)
        layout.addWidget(okbutton)
        layout.addWidget(self.status)

        self.setLayout(layout)

    def okbuttonpress(self):
        print("ok")
        if self.user.text():
            user = self.user.text()
            print("user text eingegeben")
            print(self.user.text())
            if self.pw.text():
                pw = self.pw.text()
                print("pw text eingegeben")

                try:

                    self.function_try_login(user,pw)
                except Exception as error:
                    print("Try again")
                    self.status.setText(f"Anmeldung hat nicht funktioniert \nRückmeldung: {error} \nCheck die Internet Verbindung oder deine Eingabedaten")
                    return


                self.close()
            else:
                self.status.setText("Passwort fehlt")

        else:
            self.status.setText("Benutzname fehlt")


def selectmail(self, imap):
    print("Select mail out of list")
    self.mailselectionprompt = MailSelection("Select the Mail", imap=imap,
                                             functiononnewmemberparse=self.new_member.load_data)
    self.mailselectionprompt.show()

def make_mail_body_from_template_with_input(template = '', **kwargs):
    if template:
        body = template.render(**kwargs)
        return body
    else:
        print("No template loaded")
        return  None


def send_mail(subject = '', body = '',senderadress = '',password = '', receiveradress = '' , host = '', port = ''):
    message = MIMEMultipart()
    message['Subject'] = subject
    message['From'] = senderadress
    message['To'] = receiveradress

    message.attach(MIMEText(body, "html"))
    msgBody = message.as_string()

    server = SMTP(host, port)
    server.starttls(context=mail_ssl_context())
    server.login(senderadress, password)
    server.sendmail(senderadress, receiveradress, msgBody)

    server.quit()



class MailAdressSelection(QDialog):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self,emails, title = ""):
        super().__init__()
        self.setWindowTitle(title)

        print("Select which mail adresses you want to send")
        self.resize(800, 400)
        self.move(200,200)
        layout = QVBoxLayout()
        self.emailadress_list = QListWidget()
        self.listCheckBox = emails.values.tolist()
        print(self.listCheckBox)
        grid = QGridLayout()

        for i, v in enumerate(self.listCheckBox):
            self.listCheckBox[i] = QCheckBox(v)
            self.listCheckBox[i].setChecked(True)
            grid.addWidget(self.listCheckBox[i], i, 0)

        self.okbut = QPushButton("OK")
        self.okbut.pressed.connect(self.confirm_selection)
        layout.addLayout(grid)
        layout.addWidget(self.okbut)

        self.setLayout(layout)

    def confirm_selection(self):
        selected_names = []
        for i, v in enumerate(self.listCheckBox):
            selected_names.append(v.checkState())
        selected_names = np.array(selected_names)
        selected_names = selected_names == 2
        print(selected_names)



        self.result = selected_names
        self.accept()



def render_invoice_mail_body(template, receiver_forename, invquart, invyear, masterdata):
    """Render the HTML body of an invoice mail.

    metadata is read with .get(): a community sheet missing one optional field
    (Geschäftsnummer, say) used to raise KeyError and take down the whole run.
    """
    meta = masterdata.metadata or {}
    return template.render(name=receiver_forename,
                           quart=invquart,
                           year=invyear,
                           community_name=meta.get('Bezeichnung', ''),
                           community_companynumber=meta.get('Geschäftsnummer', ''),
                           community_citycode=meta.get('PLZ', ''),
                           community_city=meta.get('Wohnort', ''),
                           community_street=meta.get('Straße', ''),
                           community_streetnr=meta.get('StraßenNr.', ''),
                           community_mail=meta.get('E-Mail', ''),
                           community_website=meta.get('Web Seite', ''),
                           community_IBAN=meta.get('IBAN', ''))


LOGO_CID = "gei-logo"


def build_invoice_email(sender_email, sender_name, receiver_email, receiver_forename,
                        invquart, invyear, template, fp_to_invoice, masterdata,
                        test_recipient=None):
    """Compose the message that will go out.

    Shared by the preview dialog and the send, so what the user approves is
    built by the same code that sends it - a preview assembled separately
    would only be a picture of what we hope happens.

    With ``test_recipient`` (the test mode in Einstellungen) the mail goes
    there instead, and the subject says who it was meant for.
    """
    email = EmailMessage()
    subject = f"Rechnung {sender_name} {invyear} Quartal {invquart}"
    if test_recipient:
        subject = f"[TEST → {receiver_email}] {subject}"
    email['Subject'] = subject
    email['From'] = sender_email
    email['To'] = test_recipient or receiver_email

    html_body = render_invoice_mail_body(template, receiver_forename, invquart, invyear, masterdata)
    plain_content = (f"Hallo {receiver_forename},\n\n"
                     f"im Anhang findest du deine Abrechnung für das {invquart}. Quartal {invyear} als PDF.\n"
                     f"Darin stehen alle Positionen und Beträge und dein Energieverlauf.\n\n"
                     f"Fragen zur Abrechnung? Antworte einfach auf diese Mail.\n\n"
                     f"Danke, dass du Teil unserer Energiegemeinschaft bist!\n\n"
                     f"Liebe Grüße\n{sender_name}\n")
    email.set_content(plain_content)
    email.add_alternative(html_body, subtype='html')
    if f"cid:{LOGO_CID}" in html_body:
        # Mail clients cannot load the logo from the app: it travels inside
        # the mail as a related image, which the template references by cid.
        with open(theme.logo_path(), "rb") as logo:
            email.get_payload()[-1].add_related(logo.read(), maintype="image", subtype="png",
                                                cid=f"<{LOGO_CID}>", filename="logo.png")

    if fp_to_invoice:
        with open(fp_to_invoice, 'rb') as content_file:
            email.add_attachment(content_file.read(), maintype='application', subtype='pdf',
                                 filename=os.path.basename(fp_to_invoice))
    return email


# Every mail connection is made on the GUI thread, so an unresponsive server
# with the default (infinite) socket timeout freezes the whole application
# mid-run with no way out but force-quitting.
MAIL_TIMEOUT = 30


def mail_ssl_context():
    """TLS context that can verify certificates in the packaged app too.

    ssl.create_default_context() trusts whatever CA file the bundled
    OpenSSL was built to look for. From a source checkout that exists
    (Homebrew's cert.pem); inside the .app it does not, so every server -
    mail.your-server.de included - failed with CERTIFICATE_VERIFY_FAILED.
    certifi's bundle ships with the app.
    """
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except Exception:
        return ssl.create_default_context()


def send_mail_to_one_person(sender_email,password,host,sender_name, receiver_email,receiver_forename,invquart,invyear, template,fp_to_invoice, masterdata,port = 587,
                            test_recipient=None):
    email = build_invoice_email(sender_email, sender_name, receiver_email, receiver_forename,
                                invquart, invyear, template, fp_to_invoice, masterdata,
                                test_recipient=test_recipient)
    receiver_email = test_recipient or receiver_email
    print(f"Sending mail to {receiver_email} with subject {email['Subject']} "
          f"and attachment {os.path.basename(fp_to_invoice) if fp_to_invoice else '(none)'}...")

    context = mail_ssl_context()

    # Without TLS the password and the invoice PDF cross the network in the
    # clear. 465 is implicit TLS; 587 and friends upgrade via STARTTLS.
    if int(port) == 465:
        smtp_session = smtplib.SMTP_SSL(host, port, context=context, timeout=MAIL_TIMEOUT)
    else:
        smtp_session = smtplib.SMTP(host, port, timeout=MAIL_TIMEOUT)
    with smtp_session as s:
        if int(port) != 465:
            try:
                s.starttls(context=context)
            except smtplib.SMTPNotSupportedError as e:
                # Otherwise this surfaces once per recipient as an opaque
                # library error, and the whole run fails without saying why.
                raise RuntimeError(
                    f"{host}:{port} bietet kein STARTTLS an. Bitte in den Einstellungen "
                    f"den SMTP-Port auf 465 stellen oder den richtigen Server eintragen."
                ) from e
        s.login(sender_email, password)
        s.send_message(email,sender_email,receiver_email)

    def ensure_folder(imap, folder_name: str):
        # Get all folders
        imap.subscribe("INBOX.Gesendete_Rechnungen")

        status, folders = imap.list()

        folders_decoded = [
            f.decode() if isinstance(f, bytes) else f
            for f in folders
        ]

        # Check if folder exists
        if not any(folder_name in f for f in folders_decoded):
            print(f"Folder '{folder_name}' not found. Creating it...")
            imap.create(folder_name)
            imap.subscribe("INBOX.Gesendete_Rechnungen")

        else:
            print(f"Folder '{folder_name}' exists.")

        return folder_name

    if test_recipient:
        # Test mails stay out of Gesendete_Rechnungen, which is the record
        # of what members actually received.
        print("... Done (test mode, not filed)")
        return

    # SAVE TO SENT FOLDER
    with imaplib.IMAP4_SSL(host, 993, timeout=MAIL_TIMEOUT, ssl_context=mail_ssl_context()) as imap:
        imap.login(sender_email, password)
        folder = ensure_folder(imap, "INBOX.Gesendete_Rechnungen")
        # show folders
        print(imap.list())

        result = imap.append(
            folder,
            "\\Seen",
            imaplib.Time2Internaldate(datetime.now().timestamp()),
            email.as_bytes()
        )

        print("Stored in:", folder)
    print("... Done")


class SendPreviewDialog(QDialog):
    """Choose recipients and approve the mail run, on one screen.

    Every member with an invoice is listed with a tick box (all ticked to
    start); selecting a row shows that exact mail - subject, body and
    attachment - built by the same code that sends it. This replaces a
    separate address list followed by this preview, which asked the same
    question twice. The table can be filtered and sorted; nothing is sent
    until the send button, which counts the ticked mails.
    """

    # The invoice mail template is designed at 595px plus padding.
    MAIL_WIDTH = 660
    JOB, MISSING = "job", "missing"

    def __init__(self, jobs, missing, build_preview, parent=None, test_recipient=None):
        """
        jobs:    [(display_name, address, attachment_path), ...] - can be sent
        missing: [(display_name, address, expected_filename), ...] - no PDF found
        build_preview: job index -> (subject, html_body, attachment_name)
        """
        super().__init__(parent)
        self.setWindowTitle(tr("Rechnungen verschicken"))
        self.resize(1200, 700)
        self.jobs = jobs
        self.missing = missing
        self.build_preview = build_preview
        self.test_recipient = test_recipient
        self.result = False
        self.selected_jobs = []

        layout = QVBoxLayout(self)
        if test_recipient:
            banner = QLabel(tr("TESTMODUS - alle Mails gehen an {address}, keine an die "
                               "Mitglieder. Ausschalten in den Einstellungen.",
                               address=test_recipient))
            banner.setWordWrap(True)
            banner.setStyleSheet("background: #ff9f34; color: #0c1112; font-weight: 600; "
                                 "padding: 8px; border-radius: 4px;")
            layout.addWidget(banner)
        self.summary = QLabel()
        self.summary.setStyleSheet("font-weight: 600; padding: 4px;")
        layout.addWidget(self.summary)

        bar = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText(tr("Filtern… (Name, Mailadresse, Datei)"))
        self.search.setClearButtonEnabled(True)
        self.search.textChanged.connect(self.apply_filter)
        bar.addWidget(self.search, 1)
        tick_all = QPushButton(tr("Alle auswählen"))
        tick_all.clicked.connect(lambda: self.set_all(True))
        tick_none = QPushButton(tr("Keine"))
        tick_none.clicked.connect(lambda: self.set_all(False))
        bar.addWidget(tick_all)
        bar.addWidget(tick_none)
        layout.addLayout(bar)

        splitter = QSplitter(Qt.Horizontal)
        self.table = QTableWidget(len(jobs) + len(missing), 4)
        self.table.setHorizontalHeaderLabels(["✓", tr("Empfänger:in"), tr("Mailadresse"), tr("Rechnung")])
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.verticalHeader().setVisible(False)
        for row, (name, address, path) in enumerate(jobs):
            self._set_row(row, (self.JOB, row), name, address, tr("✓ Rechnung gefunden"),
                          sendable=True, tooltip=os.path.basename(path))
        for offset, (name, address, expected) in enumerate(missing):
            self._set_row(len(jobs) + offset, (self.MISSING, offset), name, address,
                          tr("✗ keine Rechnung"), sendable=False,
                          tooltip=tr("{file} nicht gefunden", file=expected))
        self.table.resizeColumnsToContents()
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        # Without this the attachment column is clipped by the splitter.
        header.setStretchLastSection(True)
        self.table.setSortingEnabled(True)
        self.table.sortByColumn(-1, Qt.AscendingOrder)
        self.table.setMinimumWidth(460)
        self.table.itemSelectionChanged.connect(self.show_selected)
        self.table.itemChanged.connect(lambda *_: self.update_counts())
        splitter.addWidget(self.table)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        self.subject_label = QLabel()
        self.subject_label.setWordWrap(True)
        self.subject_label.setStyleSheet("font-weight: 600;")
        self.attachment_label = QLabel()
        self.attachment_label.setStyleSheet("color: palette(mid);")
        self.body_view = QTextBrowser()
        self.body_view.setOpenExternalLinks(False)
        right_layout.addWidget(QLabel(tr("Vorschau")))
        right_layout.addWidget(self.subject_label)
        right_layout.addWidget(self.attachment_label)
        right_layout.addWidget(self.body_view, 1)
        splitter.addWidget(right)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 5)
        splitter.setSizes([520, 680])
        layout.addWidget(splitter, 1)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        cancel = QPushButton(tr("Abbrechen"))
        cancel.clicked.connect(self.reject)
        self.send_button = QPushButton()
        self.send_button.setObjectName("primaryButton")
        self.send_button.setDefault(True)
        self.send_button.clicked.connect(self.confirm)
        buttons.addWidget(cancel)
        buttons.addWidget(self.send_button)
        layout.addLayout(buttons)

        self.update_counts()
        if jobs:
            self.table.selectRow(0)

    @staticmethod
    def plural(n):
        return tr("1 Mail") if n == 1 else tr("{n} Mails", n=n)

    def _set_row(self, row, key, name, address, status, sendable, tooltip=""):
        tick = SortableItem()
        tick.setData(Qt.UserRole, key)
        if sendable:
            tick.setFlags(Qt.ItemIsUserCheckable | Qt.ItemIsEnabled | Qt.ItemIsSelectable)
            tick.setCheckState(Qt.Checked)
        else:
            tick.setFlags(Qt.ItemIsEnabled | Qt.ItemIsSelectable)
        tick.set_key(0 if sendable else 1)
        self.table.setItem(row, 0, tick)
        for column, text in enumerate((str(name), str(address), status), start=1):
            item = SortableItem(text)
            item.set_key(text)
            if not sendable:
                item.setForeground(QBrush(QColor("#a33")))
            if tooltip:
                item.setToolTip(tooltip)
            self.table.setItem(row, column, item)

    def row_key(self, row):
        item = self.table.item(row, 0)
        return item.data(Qt.UserRole) if item is not None else None

    def ticked_jobs(self):
        found = []
        for row in range(self.table.rowCount()):
            kind, index = self.row_key(row)
            if kind == self.JOB and self.table.item(row, 0).checkState() == Qt.Checked:
                found.append(index)
        return sorted(found)

    def update_counts(self):
        n = len(self.ticked_jobs())
        parts = [tr("{mails} ausgewählt", mails=self.plural(n)) + f" ({len(self.jobs)})"]
        if self.missing:
            parts.append(tr("{skipped} ohne PDF-Rechnung", skipped=len(self.missing)))
        self.summary.setText(" · ".join(parts))
        self.send_button.setText(
            tr("{mails} an die Testadresse verschicken", mails=self.plural(n)) if self.test_recipient
            else tr("{mails} verschicken", mails=self.plural(n)))
        self.send_button.setEnabled(n > 0)

    def set_all(self, checked):
        self.table.blockSignals(True)
        for row in range(self.table.rowCount()):
            kind, _ = self.row_key(row)
            if kind == self.JOB and not self.table.isRowHidden(row):
                self.table.item(row, 0).setCheckState(Qt.Checked if checked else Qt.Unchecked)
        self.table.blockSignals(False)
        self.update_counts()

    def apply_filter(self, text):
        needle = text.strip().casefold()
        for row in range(self.table.rowCount()):
            haystack = " ".join(self.table.item(row, c).text() + " " + (self.table.item(row, c).toolTip() or "")
                                for c in range(1, self.table.columnCount())).casefold()
            self.table.setRowHidden(row, bool(needle) and needle not in haystack)

    def show_selected(self):
        row = self.table.currentRow()
        key = self.row_key(row) if row >= 0 else None
        if key is None or key[0] != self.JOB:
            # A skipped recipient has no mail to preview.
            self.subject_label.setText("")
            self.attachment_label.setText(
                tr("Für diese Person wurde keine PDF-Rechnung gefunden - "
                   "es wird nichts verschickt.") if key else "")
            self._show_html("")
            return
        try:
            subject, html, attachment = self.build_preview(key[1])
        except Exception as e:
            self.subject_label.setText(tr("Vorschau nicht möglich"))
            self.attachment_label.setText(str(e))
            self._show_html("")
            return
        self.subject_label.setText(tr("Betreff: {subject}", subject=subject))
        self.attachment_label.setText(tr("Anhang: {file}", file=attachment))
        self._show_html(html)

    @staticmethod
    def _message_body(html):
        """Strip the outer centering wrapper before handing the mail to Qt.

        The template centres a fixed 595px body inside a table whose first cell
        is a 50% spacer. Qt's rich text engine gives that spacer half the pane,
        leaves the body too little room, and renders it one character per line.
        Mail clients are fine with it; Qt is not. The inner table is the actual
        message, so show that.
        """
        if not html:
            return ""
        # The preview has no attachments to resolve cid: against; show the
        # logo from the app's own copy instead.
        html = html.replace(f"cid:{LOGO_CID}", QUrl.fromLocalFile(theme.logo_path()).toString())
        try:
            soup = BeautifulSoup(html, "html.parser")
            body = soup.find(id="MAILSTYLE")
            if body is None:
                for table in soup.find_all("table"):
                    if "px" in (table.get("style") or ""):
                        body = table
                        break
            if body is not None:
                return str(body)
        except Exception as e:
            print(f"Could not isolate the mail body for preview: {e}")
        return html

    def _show_html(self, html):
        self._html = html
        self.body_view.setHtml(self._message_body(html))
        # The template is laid out for a 595px-wide mail client. Qt's rich text
        # engine otherwise squeezes it into the pane and the body comes out one
        # character per line; pin the width and let the pane scroll instead.
        self.body_view.document().setTextWidth(
            max(self.MAIL_WIDTH, self.body_view.viewport().width()))

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if getattr(self, "_html", ""):
            self.body_view.document().setTextWidth(
                max(self.MAIL_WIDTH, self.body_view.viewport().width()))

    def confirm(self):
        self.selected_jobs = self.ticked_jobs()
        self.result = bool(self.selected_jobs)
        self.accept()


def test_mail_login(address, password, imap_host, smtp_host, smtp_port, timeout=10):
    """Try logging in to IMAP and SMTP. Returns (ok, lines).

    Exists so credentials are proved from the settings dialog rather than
    discovered to be wrong partway through a send to the whole membership.
    Never returns the password in its messages.
    """
    lines = []
    ok = True

    if not address or not password:
        return False, ["Mailadresse und Passwort werden benötigt."]

    if imap_host:
        try:
            with imaplib.IMAP4_SSL(imap_host, 993, timeout=timeout, ssl_context=mail_ssl_context()) as imap:
                imap.login(address, password)
            lines.append(f"IMAP ({imap_host}:993): OK")
        except Exception as e:
            ok = False
            lines.append(f"IMAP ({imap_host}:993): {e}")
    else:
        lines.append("IMAP: kein Server angegeben")

    if smtp_host:
        try:
            port = int(smtp_port or 587)
        except (TypeError, ValueError):
            port = 587
        try:
            context = mail_ssl_context()
            if port == 465:
                session = smtplib.SMTP_SSL(smtp_host, port, context=context, timeout=timeout)
            else:
                session = smtplib.SMTP(smtp_host, port, timeout=timeout)
            with session as smtp:
                if port != 465:
                    smtp.starttls(context=context)
                smtp.login(address, password)
            lines.append(f"SMTP ({smtp_host}:{port}): OK")
        except Exception as e:
            ok = False
            lines.append(f"SMTP ({smtp_host}:{port}): {e}")
    else:
        ok = False
        lines.append("SMTP: kein Server angegeben - ohne SMTP kann nicht verschickt werden.")

    return ok, lines
