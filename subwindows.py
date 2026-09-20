import PyQt5.QtWidgets as QtWidgets
import PyQt5.QtGui as QtGui
from bs4 import BeautifulSoup

import imaplib
import email
from email.header import decode_header
from PyQt5.QtWidgets import QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QLineEdit, QPushButton, QListWidget, QTextEdit, QFormLayout, QScrollArea
import sys


class Subwindow(QMainWindow):
    def __init__(self, Windowname,  Menubardata = [],*args,**kwargs):
        # menubar has to be [[Text,Shortcut,function]]
        super(Subwindow, self).__init__(*args, **kwargs)
        print("Initializing Subwindow")
        self.windowname = Windowname
        self.menubardata = Menubardata
        self.setWindowTitle(self.windowname)

        self.init_Ui_overview()

    def init_Ui_overview(self):
        self.centralwidget = QtWidgets.QWidget(self)
        # main layout setup
        self.overallverticallayout = QtWidgets.QVBoxLayout(self.centralwidget)
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.verticalLayout0 = QtWidgets.QVBoxLayout()  # layout on the left with the masslist, and other stuff
        self.verticalLayout1 = QtWidgets.QVBoxLayout()  # laout on the right with the graph
        if self.menubardata:
            menubar = QtWidgets.QMenuBar()
            self.actionFile = menubar.addMenu("Datei")
            # the po.importanythingact triggers init_UI_file_loaded() and init_plots()
            for menuline in self.menubardata:
                action = QtWidgets.QAction(menuline[0], self)
                action.triggered.connect(menuline[2])
                if menuline[1]:
                    action.setShortcut(menuline[1])
                self.actionFile.addAction(action)

            self.actionFile.addSeparator()
            quit = QtWidgets.QAction("Schließen", self)
            quit.setShortcut("Alt+F4")
            quit.triggered.connect(lambda: sys.exit(0))
            self.actionFile.addAction(quit)

            self.overallverticallayout.addWidget(menubar)
        self.overallverticallayout.addLayout(self.horizontalLayout)
        self.setCentralWidget(self.centralwidget)


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
