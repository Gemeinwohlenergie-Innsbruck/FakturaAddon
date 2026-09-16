from bs4 import BeautifulSoup
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout,QListWidget, QPushButton, QLabel, QScrollArea, QTextEdit, QFormLayout, QLineEdit, QGridLayout, QCheckBox, QDialog
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
            if self.start + self.nr_messagesperpage >= 0:
                self.start = self.start + self.nr_messagesperpage
                self.finish = self.finish + self.nr_messagesperpage
            else: return
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
    server.starttls()
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



class Sendapproval(QDialog):
    """
    This "window" is a QWidget. If it has no parent, it
    will appear as a free-floating window as we want.
    """
    def __init__(self,emails, title = ""):
        super().__init__()
        self.setWindowTitle(title)

        print("Check")
        self.resize(800, 400)
        self.move(200,200)
        layout = QVBoxLayout()
        sublayout = QHBoxLayout()
        layout.addWidget(QLabel(f"Soll ich den folgenden Personen ein Mail mit deren Rechnungen schreiben? \n{emails}"))
        self.yesbut = QPushButton("Ja")
        self.nobut = QPushButton("Nein")
        sublayout.addWidget(self.yesbut)
        sublayout.addWidget(self.nobut)
        layout.addLayout(sublayout)

        self.yesbut.pressed.connect(lambda: self.confirm_selection(True))
        self.nobut.pressed.connect(lambda: self.confirm_selection(False))

        self.setLayout(layout)

    def confirm_selection(self,event):

        self.result = event
        self.accept()

def send_mail_to_one_person(sender_email,password,host,sender_name, receiver_email,receiver_forename,invquart,invyear, template,fp_to_invoice, masterdata,port = 587):
    email = EmailMessage()

    email['Subject'] = f"Rechnung {sender_name} {invyear} Quartal {invquart}"
    email['From'] = sender_email
    email['To'] = receiver_email
    print(f"Sending Mail from {sender_email} with to {receiver_email} with subject {email['Subject']} with attachment {fp_to_invoice}...")


    output_from_parsed_template = template.render(name=receiver_forename,
                                                  quart = invquart,
                                                  year = invyear,
                                                  community_name = masterdata.metadata['Bezeichnung'],
                                                  community_companynumber = masterdata.metadata['Geschäftsnummer'],
                                                  community_citycode = masterdata.metadata['PLZ'],
                                                  community_city = masterdata.metadata['Wohnort'],
                                                  community_street = masterdata.metadata['Straße'],
                                                  community_streetnr = masterdata.metadata['StraßenNr.'],
                                                  community_mail = masterdata.metadata['E-Mail'],
                                                  community_website = masterdata.metadata['Web Seite'],
                                                  community_IBAN = masterdata.metadata['IBAN'])


    plain_content = f"Hallo {receiver_forename}. \nAnbei findest du deine Rechnung für das {invquart}, {invyear} \n Mit lieben Grüßen, \n{sender_name} \n\n|"
    email.set_content(plain_content)  # Optional plain text

    # Add HTML content
    email.add_alternative(output_from_parsed_template, subtype='html')




# .attach(MIMEText(output_from_parsed_template, "html"))
    with open(fp_to_invoice, 'rb') as content_file:
        content = content_file.read()
        email.add_attachment(content, maintype='application', subtype='pdf', filename=os.path.basename(fp_to_invoice))

    context = ssl.create_default_context()
    # with smtplib.SMTP_SSL(host, 465, context=context) as server:
    #     server.login(sender_email, password)
    #     server.sendmail(
    #         sender_email, receiver_email,email
    #     )

    with smtplib.SMTP(host,port,) as s:
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

    # SAVE TO SENT FOLDER
    with imaplib.IMAP4_SSL(host, 993) as imap:
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
