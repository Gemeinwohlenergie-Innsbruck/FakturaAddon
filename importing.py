import numpy as np
from functools import partial
from docxtpl import DocxTemplate
import pandas as pd
from PyQt5.QtWidgets import QFileDialog, QMessageBox, QWidget, QVBoxLayout, QPushButton, QLabel,  QMessageBox, QDialog
from PyQt5.QtCore import pyqtSignal, QThread, Qt
from io import BytesIO
from jinja2 import Environment, FileSystemLoader, PackageLoader, select_autoescape
from openpyxl import load_workbook



class Data():
    def __init__(self,F_for_data_loading,F_for_template_loading, F_for_metadata_loading = lambda x: x):
        self.f_load_data = F_for_data_loading
        self.f_load_template = F_for_template_loading
        self.f_load_metadata = F_for_metadata_loading

        self.data = None
        self.metadata = None
        self.template = None
    def load_data(self,**kwargs):
        self.data = self.f_load_data(**kwargs)
        return self.data
    def load_metadata(self,**kwargs):
        self.metadata = self.f_load_metadata(**kwargs)
        return self.metadata
    def load_template(self,**kwargs):
        self.template = self.f_load_template(**kwargs)
        return self.template

# def load_mandates(filepath='',nc =False, nc_instance = ''):
#     print(f"Load {filepath}")
#     if not nc:
#         try:
#             mandates = pd.read_excel(filepath)
#         except:
#             errorbox = QMessageBox()
#             errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)")
#             errorbox.exec_()
#             return
#     else:
#         print("Nextcloud loading")
#         mandates = nc_instance.files.download(filepath)
#         mandates = pd.read_excel(BytesIO(mandates), engine='openpyxl')
#         print(mandates)
#     try:
#         mandates = mandates[~mandates['Mandatsausstellungsdatum (Datum auf dem Vertrag)'].isna()]
#         mandates['Mandatsausstellungsdatum'] = pd.to_datetime(mandates['Mandatsausstellungsdatum (Datum auf dem Vertrag)'],dayfirst=True)
#         mandates = mandates.drop('Mandatsausstellungsdatum (Datum auf dem Vertrag)', axis=1)
#         mandates = mandates.rename(columns={'Vorname (gleich wie in eegfaktura)': 'Vorname', 'Nachname (gleich wie in eegfaktura)': 'Nachname','Mitgliedsnummer aus eegfaktura ist auch die Mandatsreferenz':'Mitgliedsnummer'})
#     except:
#         errorbox = QMessageBox()
#         errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)")
#         errorbox.exec_()
#         return
#     return mandates
# def load_mandate_template(filepath = '', filepath2= ''):
#     print(f"Load {filepath},{filepath2}")
#     templates = {}
#     templates["debit"] = pd.read_csv(filepath,delimiter=";")
#     templates["transfer"]  = pd.read_csv(filepath2,delimiter=";")
#     return templates


def load_invoices(filepath='',nc = False):
    print(filepath)
    if not nc:
        try:
            data = pd.read_excel(filepath,sheet_name="Liste")
            datadetailed = pd.read_excel(filepath,sheet_name="Details")
        except:
            data = None
            datadetailed = None
            errorbox = QMessageBox()
            errorbox.setWindowTitle("Datei nicht lesbar")
            errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)")
            errorbox.exec_()
    else:
        print("Nextcloud loading")
    if data is not None:
        invoicedata = {}
        invoicedata["list"] = data
        invoicedata["detailed"] = datadetailed

        return invoicedata
    else:
        return None

def load_invoice_template(filepath, nc = False):
    print(f"Load invoice template from {filepath}")
    if not filepath:
        return None
    try:
        return DocxTemplate(filepath)
    except Exception as e:
        print(f"Could not load invoice template: {e}")
        errorbox = QMessageBox()
        errorbox.setWindowTitle("Rechnungsvorlage")
        errorbox.setText(f"Die Rechnungsvorlage konnte nicht geladen werden:\n{filepath}\n\n{e}")
        errorbox.exec_()
        return None

def load_mail_adresses(filepath = '', nc = ''):
    print(f"Load Emaildata from {filepath}")
    if not nc:
        try:
            data = pd.read_excel(filepath,sheet_name="Mitglieder")["E-Mail"]
        except Exception as e:
            print(e)
            data = None
            errorbox = QMessageBox()
            errorbox.setWindowTitle("Datei nicht lesbar")
            errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)")
            errorbox.exec_()
    else:
        print("Nextcloud loading (not implemented)")
    return data

def load_mail_template(filepath = ''):
    print(f"Load mail template from {filepath}")
    if not filepath:
        return None
    try:
        # abspath so a bare filename resolves against the working directory
        # instead of handing FileSystemLoader an empty search path.
        searchpath = os.path.dirname(os.path.abspath(filepath))
        env = Environment(loader=FileSystemLoader(searchpath), autoescape=select_autoescape())
        return env.get_template(os.path.basename(filepath))
    except Exception as e:
        print(f"Could not load mail template: {e}")
        errorbox = QMessageBox()
        errorbox.setWindowTitle("Emailvorlage")
        errorbox.setText(f"Die Emailvorlage konnte nicht geladen werden:\n{filepath}\n\n{e}")
        errorbox.exec_()
        return None



def load_energy_qovdata(filepath = "", nc = False):
    print(f"Load {filepath}")
    if not nc:
        try:
            # to acess the data you have to user multiindex.like energydata.data.loc[:,pd.IndexSlice["AT005120000000000000000030160301P",:,:,:]] or data.xs("Mario Buchinger",level="Name",axis=1)
            # First entry is zählpunktnummer, dann Name, dann prod/cons dann Art der Daten
            qovdata = pd.read_excel(filepath, sheet_name="QoV Log", skiprows=[7, 8, 9], header=[1, 2, 3, 6],
                                    index_col=[0])
            newnameindex = {x: x.replace(" ", "") for x in qovdata.columns.get_level_values(level="Name")}
            qovdata.index = pd.to_datetime(qovdata.index, format="%d.%m.%Y %H:%M:%S")
            qovdata = qovdata.sort_index()

        except Exception as e:
            print(e)
            errorbox = QMessageBox()
            errorbox.setWindowTitle("Datei nicht lesbar")
            errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)")
            errorbox.exec_()
            return
    else:
        print("Nextcloud loading")

    return qovdata

def load_energy_data(filepath = "", nc = False, qov = False):
    print(f"Load {filepath}, qov: {qov}")
    if not nc:
        class LoadingDialog(QDialog):
            def __init__(self, message="Laden"):
                super().__init__()
                self.setWindowFlags(self.windowFlags() | Qt.WindowStaysOnTopHint)  # keep on top
                self.setWindowTitle("Laden")
                self.setModal(True)  # modal dialog
                self.resize(250, 80)

                layout = QVBoxLayout()
                self.label = QLabel(message)
                self.label.setAlignment(Qt.AlignCenter)
                layout.addWidget(self.label)
                self.setLayout(layout)

            def keyPressEvent(self, event):
                # Esc would close the dialog, return from this function, and
                # drop the last reference to a still-running QThread - Qt then
                # aborts with "QThread: Destroyed while thread is still running".
                if event.key() != Qt.Key_Escape:
                    super().keyPressEvent(event)

            def closeEvent(self, event):
                # The title-bar close button bypasses keyPressEvent entirely.
                event.ignore()


        class Worker(QThread):
            finished = pyqtSignal(list)  # signal to return data
            progress = pyqtSignal(str)  # optional signal for messages

            def __init__(self, filepath, qov):
                super().__init__()
                self.filepath = filepath
                self.qov = qov
                # Written before the signal is emitted and read after wait(),
                # so the result does not depend on a queued slot having run.
                self.result = None
                self.error = None

            def run(self):
                self.progress.emit("Excel-Datei wird geladen...")
                try:
                    if self.qov:
                        data = pd.read_excel(self.filepath, sheet_name="QoV Log", skiprows=[7, 8, 9], header=[1, 2, 3, 6],
                                                index_col=[0])
                    else:
                        data = pd.read_excel(self.filepath,sheet_name="Energiedaten",skiprows=[7,8,9], header=[1,2,3,6],index_col=[0])
                    data.index = pd.to_datetime(data.index, format="%d.%m.%Y %H:%M:%S")
                    data = data.sort_index()

                    self.result = data
                    self.finished.emit([True, data])
                except Exception as e:
                    self.error = f"There was an error loading: {e}"
                    self.finished.emit([False, self.error])

        dlg = LoadingDialog("Laden, bitte warten...")
        worker = Worker(filepath, qov)
        worker.finished.connect(lambda _: dlg.accept())

        worker.start()
        dlg.exec()
        # Block until the thread has actually finished before `worker` goes out
        # of scope, otherwise Qt tears down a running QThread.
        worker.wait()

        if worker.error:
            # Read off the worker rather than out of a queued slot: if the
            # dialog ever stops running its event loop before the worker
            # emits, the slot is never delivered and the loaded DataFrame is
            # silently dropped.
            print(worker.error)
            errorbox = QMessageBox()
            errorbox.setWindowTitle("Datei nicht lesbar")
            errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)"
                             f"\n\n{worker.error}")
            errorbox.exec_()
    else:
        print("Nextcloud loading")
        return None

    return worker.result

def load_faktura_member_export_template(filepath = "",nc =False, nc_instance = ''):
    print(f"Load {filepath}")
    if not nc:
        try:
            template = load_workbook(filename = filepath)
            print(template)
        except:
            errorbox = QMessageBox()
            errorbox.setWindowTitle("Datei nicht lesbar")
            errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)")
            errorbox.exec_()
            return
    else:
        print("Nextcloud loading")
        template = nc_instance.files.download(filepath)
        template = load_workbook(BytesIO(template))
        print(template)
    return template

def load_new_member_data(data = ''):
    return data

def load_filepath(parent, title, filter="Excel (*.xlsx)", fileex=True, pathisdir = False,homedir = "", defaultfilename = ""):
    print("Lokal")
    if not pathisdir:
        if fileex:
            filepath, filter = QFileDialog.getOpenFileName(parent, title, homedir, filter)
        else:
            if defaultfilename:
                homedir = os.path.join(homedir,defaultfilename)
            filepath, filter = QFileDialog.getSaveFileName(parent, title, homedir, filter)
    else:
        filepath = QFileDialog.getExistingDirectory(parent, title, homedir)
    if filepath:
        return filepath
    else:
        return None

def load_masterdata(filepath, nc = False):
    print(f"Load Masterdata from {filepath}")
    if not nc:
        try:
            data = pd.read_excel(filepath,sheet_name="Mitglieder")
        except Exception as e:
            print(e)
            data = None
            errorbox = QMessageBox()
            errorbox.setWindowTitle("Datei nicht lesbar")
            errorbox.setText("Ausgewählte Datei ist nicht lesbar (ist sie im richtigen Format?)")
            errorbox.exec_()
    else:
        print("Nextcloud loading (not implemented)")
    return data

def load_masterdata_meta(filepath):
    print(f"Load Metadata from {filepath}")
    df = pd.read_excel(filepath, header=None, dtype=str)

    result = {}
    for col in df.columns:
        col_values = df[col].tolist()  # remove empty cells
        col_values.append(np.nan)
        # print(col_values)
        for i in range(len(col_values) - 2):
            this = col_values[i]
            next = col_values[i + 1]
            nextnext = col_values[i + 2]
            if not pd.isna(col_values[i + 1]) and pd.isna(col_values[i + 2]):
                result[this] = next
                # print(this, next)
            else:
                pass
                # print("no viable")

            i += 1
    return result


def check_whether_data_exists(mandates = None,masterdata = None,invoices = None,energydata = None, emails = None,
                              mandatesrequired = False, invoicedatarequired = False, masterdatarequired = False,
                              masterdataexporttemprequired = False, emailstemprequired = False,invoicestemprequired = False,energymetadatarequired = False,
                              energydataoptional = False, newmember = None, newmemberdatarequired = False, newmembertemprequired = False):
    data_missing = []
    check = True
    if mandatesrequired:
        if mandates.data is None:
            check = False
            data_missing.append("Mandate")
    if invoicedatarequired:
        if invoices.data is None:
            check = False
            data_missing.append("Rechnungsdaten")
    if emailstemprequired:
        if emails.template is None:
            check = False
            data_missing.append("Email Template")
    if masterdatarequired:
        if masterdata.data is None:
            check = False
            data_missing.append("EEG Faktura Stammdaten")
    if masterdataexporttemprequired:
        if masterdata.template is None:
            check = False
            data_missing.append("Vorlage EEG Faktura Stammdaten Expor")
    if invoicestemprequired:
        if invoices.template is None:
            check = False
            data_missing.append("Rechnungen Vorlage")
    if energydataoptional:
        if energydata.data is None:
            data_missing.append("Energiedaten")
    if energymetadatarequired:
        if energydata.metadata is None:
            check = False
            data_missing.append("Energiedaten QoV")
    if newmemberdatarequired:
        if newmember.data is None:
            check = False
            data_missing.append("Daten zum Neuen Mitglied")
    if newmembertemprequired:
        if newmember.template is None:
            check = False
            data_missing.append("Template zum export der Neuen Mitglied")
    return check, data_missing



masterdata = Data(load_masterdata,"",F_for_metadata_loading= load_masterdata_meta)
invoices = Data(load_invoices,load_invoice_template)
emails = Data(load_mail_adresses,load_mail_template)
energydata = Data(load_energy_data,"", F_for_metadata_loading=partial(load_energy_data,qov = True))
newmember = Data(load_new_member_data,load_faktura_member_export_template)


import sys
import os
import requests
from pathlib import Path
from PyQt5.QtWidgets import (
    QApplication, QDialog, QFormLayout, QLineEdit,
    QPushButton, QDialogButtonBox, QLabel, QVBoxLayout, QHBoxLayout, QFileDialog
)

# Single source of truth. Three copies of these used to live in this file,
# and only the last one was reachable.
from config import ENV_PATH, ENV_KEYS, load_env, save_env

BASE_URL = "https://eegfaktura.at/energystore/query"


def fetch_community_metadata(community_id: str, tenant: str, user: str, password: str) -> dict:
    """POST to the community metadata endpoint and return the parsed JSON body.

    Raises:
        requests.HTTPError        – non-2xx response (bad credentials / wrong community ID)
        requests.RequestException – network-level errors (timeout, DNS, …)
    """
    import base64
    url = f"{BASE_URL}/{community_id}/metadata"
    credentials = base64.b64encode(f"{user}:{password}".encode()).decode()
    headers = {
        "Content-Type":  "application/json",
        "Authorization": f"Basic {credentials}",
        "X-Tenant":      tenant,
    }
    body = {}
    print("--- REQUEST ---")
    print(f"POST {url}")
    print(f"Headers: Content-Type={headers['Content-Type']}, X-Tenant={headers['X-Tenant']}, Authorization=Basic <redacted>")
    print(f"Body:    {body}")
    print("---------------")
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()


class LoginDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Anmelden")
        self.setFixedWidth(700)

        layout = QVBoxLayout(self)

        form = QFormLayout()
        self.edit_user         = QLineEdit()
        self.edit_password     = QLineEdit()
        self.edit_tenant       = QLineEdit()
        self.edit_community_id = QLineEdit()
        self.edit_password.setEchoMode(QLineEdit.Password)

        form.addRow("Benutzername:", self.edit_user)
        form.addRow("Passwort:", self.edit_password)
        form.addRow("Mandant:", self.edit_tenant)
        form.addRow("Gemeinschafts-ID:", self.edit_community_id)
        layout.addLayout(form)

        for field in (self.edit_user, self.edit_password,
                      self.edit_tenant, self.edit_community_id):
            field.returnPressed.connect(self._on_accept)

        self.error_label = QLabel()
        self.error_label.setVisible(False)
        layout.addWidget(self.error_label)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        # Pre-fill fields from .env if values exist
        saved = load_env()
        self.edit_user.setText(saved.get("user", ""))
        self.edit_password.setText(saved.get("password", ""))
        self.edit_tenant.setText(saved.get("tenant", ""))
        self.edit_community_id.setText(saved.get("community_id", ""))

    def _on_accept(self):
        if not all([
            self.edit_user.text().strip(),
            self.edit_password.text(),
            self.edit_tenant.text().strip(),
            self.edit_community_id.text().strip(),
        ]):
            self.error_label.setText("Alle Felder sind erforderlich.")
            self.error_label.setVisible(True)
            return
        self.error_label.setVisible(False)

        creds = self.get_credentials()
        try:

            self._metadata = fetch_community_metadata(
                community_id=creds["community_id"],
                tenant=creds["tenant"],
                user=creds["user"],
                password=creds["password"],
            )

        except requests.HTTPError as exc:
            self.error_label.setText(
                f"HTTP {exc.response.status_code} — bitte Zugangsdaten und Gemeinschafts-ID prüfen"
            )
            self.error_label.setVisible(True)
            return
        except requests.RequestException as exc:
            self.error_label.setText(f"Netzwerkfehler: {exc}")
            self.error_label.setVisible(True)
            return

        save_env(creds)
        self.accept()

    def get_credentials(self) -> dict:
        return {
            "user":         self.edit_user.text().strip(),
            "password":     self.edit_password.text(),
            "tenant":       self.edit_tenant.text().strip(),
            "community_id": self.edit_community_id.text().strip(),
        }

    def get_metadata(self) -> dict:
        """Returns the metadata response from the server (only valid after accept())."""
        return getattr(self, "_metadata", {})

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Einstellungen")
        self.setFixedWidth(700)

        layout = QVBoxLayout(self)

        form = QFormLayout()

        self.edit_my_mail     = QLineEdit()
        self.edit_imap_server = QLineEdit()
        self.edit_my_mail_pw  = QLineEdit()
        self.edit_my_mail_pw.setEchoMode(QLineEdit.Password)
        self.edit_eeg_name    = QLineEdit()

        # Home directory with browse button
        dir_row = QHBoxLayout()
        self.edit_home_directory = QLineEdit()
        browse_btn = QPushButton("Durchsuchen…")
        browse_btn.clicked.connect(self._browse_directory)
        dir_row.addWidget(self.edit_home_directory)
        dir_row.addWidget(browse_btn)

        # Template fields with browse buttons
        self.edit_template_invoice = QLineEdit("template_invoice_clean.docx")
        invoice_row = QHBoxLayout()
        invoice_browse = QPushButton("Durchsuchen…")
        invoice_browse.clicked.connect(lambda: self._browse_file(self.edit_template_invoice, "Word Documents (*.docx)"))
        invoice_row.addWidget(self.edit_template_invoice)
        invoice_row.addWidget(invoice_browse)

        self.edit_template_email = QLineEdit("email_template.html")
        email_row = QHBoxLayout()
        email_browse = QPushButton("Durchsuchen…")
        email_browse.clicked.connect(lambda: self._browse_file(self.edit_template_email, "HTML Files (*.html)"))
        email_row.addWidget(self.edit_template_email)
        email_row.addWidget(email_browse)

        form.addRow("Mailadresse:", self.edit_my_mail)
        form.addRow("IMAP-Server:", self.edit_imap_server)
        form.addRow("Mail-Passwort:", self.edit_my_mail_pw)
        form.addRow("Basisordner:", dir_row)
        form.addRow("Name der EEG:", self.edit_eeg_name)
        form.addRow("Rechnungsvorlage:", invoice_row)
        form.addRow("Emailvorlage:", email_row)
        layout.addLayout(form)

        note = QLabel("Alle Felder sind optional.")
        layout.addWidget(note)

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        for field in (self.edit_my_mail, self.edit_imap_server,
                      self.edit_my_mail_pw, self.edit_home_directory,
                      self.edit_eeg_name, self.edit_template_invoice,
                      self.edit_template_email):
            field.returnPressed.connect(self._on_save)

        # Pre-fill from .env
        saved = load_env()
        self.edit_my_mail.setText(saved.get("my_mail", ""))
        self.edit_imap_server.setText(saved.get("imap_server", ""))
        self.edit_my_mail_pw.setText(saved.get("my_mail_pw", ""))
        self.edit_home_directory.setText(saved.get("home_directory", ""))
        self.edit_eeg_name.setText(saved.get("EEG_name", ""))
        if saved.get("template_export_invoice"):
            self.edit_template_invoice.setText(saved["template_export_invoice"])
        if saved.get("template_email"):
            self.edit_template_email.setText(saved["template_email"])

    def _browse_directory(self):
        path = QFileDialog.getExistingDirectory(self, "Basisordner auswählen",
                                                self.edit_home_directory.text() or str(Path.home()))
        if path:
            self.edit_home_directory.setText(path)

    def _browse_file(self, edit: QLineEdit, file_filter: str):
        path, _ = QFileDialog.getOpenFileName(self, "Datei auswählen",
                                              self.edit_home_directory.text() or str(Path.home()),
                                              file_filter)
        if path:
            edit.setText(path)

    def _on_save(self):
        settings = self.get_settings()
        save_env(settings)
        self.accept()

    def get_settings(self) -> dict:
        return {
            "my_mail":                  self.edit_my_mail.text().strip(),
            "imap_server":              self.edit_imap_server.text().strip(),
            "my_mail_pw":               self.edit_my_mail_pw.text(),
            "home_directory":           self.edit_home_directory.text().strip(),
            "EEG_name":                 self.edit_eeg_name.text().strip(),
            "template_export_invoice":  self.edit_template_invoice.text().strip(),
            "template_email":           self.edit_template_email.text().strip(),
        }




