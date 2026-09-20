import datetime
import subprocess
import numpy as np
import json
from functools import partial
import pandas as pd
from pathlib import Path
import os
from subwindows import  Subwindow
from PyQt5.QtCore import *
from PyQt5 import QtWidgets, QtGui, QtCore
import sys
from PyQt5.QtWidgets import QLabel, QFileDialog, QMessageBox, QGridLayout, QTableWidget, QTableWidgetItem, QListWidget, QWidget, QListWidgetItem, QCheckBox, QListWidgetItem, QPushButton, QVBoxLayout, QDialog
from importing import invoices,emails, masterdata,energydata,load_filepath, check_whether_data_exists, newmember, LoginDialog, SettingsDialog
from exporting import produce_sepa_export_dfs, produce_invoices_and_save
from selection import select_invoice_positions
from PyQt5.QtWidgets import QHBoxLayout
import datetime as dt
import imaplib
from emailing import MailSelection, LoginPrompt, selectmail, MailAdressSelection, Sendapproval, send_mail_to_one_person
import email
from email.header import decode_header




class TableView(QtWidgets.QTableWidget):
    def __init__(self, data=pd.DataFrame([]), editable = False, clickable = False, *args):
        QtWidgets.QTableWidget.__init__(self, *args)
        self.data = data.to_dict(orient="list")
        rowcount = data.shape[0]
        self.functions_on_row_clicked = [0]*rowcount
        self.set_new_data(data, editable = editable)
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
        if clickable:
            self.itemClicked.connect(self.on_item_clicked)
    def set_new_data(self,data, editable = False, maxrows = 50):
        datacopy = data.copy().iloc[0:maxrows]
        self.data = datacopy.to_dict(orient="list")
        self.setData(datacopy.shape[0],datacopy.shape[1], editable= editable)
    def setData(self,rowcount = 0, colcount = 0, editable = False):
        self.setColumnCount(colcount)
        self.setRowCount(rowcount)
        row_names = []
        for n, key in enumerate(self.data.keys()):
            if isinstance(key,tuple):
                row_names.append(" ".join(key))
            else:
                row_names.append(key)
            for m, item in enumerate(self.data[key]):
                newitem = QtWidgets.QTableWidgetItem(str(item))
                if not editable:
                    newitem.setFlags(newitem.flags() & ~Qt.ItemIsEditable)  # Remove the editable flag
                self.setItem(m, n, newitem)

        self.setHorizontalHeaderLabels(row_names)
        self.resizeColumnsToContents()
        self.resizeRowsToContents()
    def on_item_clicked(self, item):
        row_clicked = item.row()
        # try:
        self.functions_on_row_clicked[row_clicked]()
        # except Exception as Error:
        #     print("Could not run the function for this row.")
        #     print(Error)



# class ImportDialog(QtWidgets.QDialog):
#     def __init__(self,mainwind):
#         super().__init__(mainwind)
#
#         self.setWindowTitle("Import")
#
#         layout = QtWidgets.QVBoxLayout()
#         importvariables = ["Rechnungsdaten aus EEG Faktura","Daten über Mandate","Vorlage Rechnungen","Vorlage Infinity Export"]
#         buttons = [0]*len(importvariables)
#         okbutton = QtWidgets.QPushButton("OK")
#         okbutton.pressed.connect(self.accept)
#         layouts = [0]*len(importvariables)
#         for i,importvariable in enumerate(importvariables):
#             layouts[i] = QtWidgets.QHBoxLayout()
#             layouts[i].addWidget(QtWidgets.QLabel(importvariable))
#             buttons[i] = QtWidgets.QPushButton("Laden")
#             layouts[i].addWidget(buttons[i])
#             layout.addLayout(layouts[i])
#         layout.addWidget(okbutton)
#         self.setLayout(layout)
#         def sel_filepath_and_import():
#             dialog = QFileDialog()
#             foo_dir = dialog.getExistingDirectory(self, 'Select an awesome directory')
#         buttons[0].pressed.connect()

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        print("Initializing Window")
        self.setWindowTitle("Faktura Infinity Addon")
        self.resize(1300, 800)
        self.move(20, 20)
        self.second_window = None
        self.exportwindow = None

        ENV_PATH = Path(__file__).parent / ".env"

        _ENV_KEYS = {
            "user": "EEG_USER",
            "password": "EEG_PASSWORD",
            "tenant": "EEG_TENANT",
            "community_id": "EEG_COMMUNITY_ID",
            "my_mail": "MAIL_ADDRESS",
            "imap_server": "MAIL_IMAP_SERVER",
            "my_mail_pw": "MAIL_PASSWORD",
            "home_directory": "HOME_DIRECTORY",
            "EEG_name": "EEG_NAME",
            "template_export_invoice" : "TEMPLATE_EXPORT_INVOICE",
            "template_email" : "TEMPLATE_EMAIL"
        }

        def load_env() -> dict:
            values = {}
            if not ENV_PATH.exists():
                return values
            for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                for field, env_key in _ENV_KEYS.items():
                    if key.strip() == env_key:
                        values[field] = val.strip()
            return values

        self.config = load_env()
        # Never print the config itself - it holds MAIL_PASSWORD and EEG_PASSWORD.
        print(f"Loaded {len(self.config)} settings from {ENV_PATH}")
        if not self.config:
            print("No .env configuration found - opening the settings dialog")
            dlg = SettingsDialog()
            if dlg.exec_() != QDialog.Accepted:
                # Carrying on with an empty config crashes on the next line.
                raise SystemExit(0)
            # SettingsDialog writes to .env; without this re-read self.config
            # stays empty and every lookup below fails.
            self.config = load_env()

        self.home_directory = self.config.get("home_directory", "")
        paths_datanames = ["Rechnungsdaten","EEG Faktura Stammdaten","EEG Faktura Quartalsenergiedaten","EEG Faktura Quartalsenergiedaten QOV","Rechnungen Vorlage", "Emails Vorlage"]
        self.loaded_filepaths = pd.DataFrame({"Daten":paths_datanames,
                                  "Speicherort":["Auswählen"]*len(paths_datanames),
                                              })
        # promptwindows

        self.loginprompt = None
        self.mailselectionprompt = None
        #nc credits
        self.nc_auth_user = ''
        self.nc_auth_pass = ''
        #email data



        self.mandatesdata_loaded = False
        self.invoicesdata_loaded = False
        self.thisinvoices_year = ""
        self.thisinvoice_quart = ""
        self.safepath_this_invoices = ""
        self.init_data()
        self.init_Ui()


    def init_Ui(self):
        self.centralwidget = QtWidgets.QWidget(self)
        self.centralwidget = QtWidgets.QWidget(self)
        self.overallverticallayout = QtWidgets.QVBoxLayout(self.centralwidget)
        menubar = QtWidgets.QMenuBar()
        self.menubardata_Make_invoices= self.init_menubardata_make_invoices()
        if self.menubardata_Make_invoices:
            self.actionFile = menubar.addMenu("Rechnungen erstellen und verschicken")
            for menuline in self.menubardata_Make_invoices:
                action = QtWidgets.QAction(menuline[0], self)
                action.triggered.connect(menuline[2])
                if menuline[1]:
                    action.setShortcut(menuline[1])
                self.actionFile.addAction(action)
        self.menubardata_Infinity= self.init_menubardata_Infinity()
        if self.menubardata_Infinity:
            self.actionFile = menubar.addMenu("Infinity export")
            for menuline in self.menubardata_Infinity:
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

        # self.menubardata_New_member= self.init_menubardata_new_member()
        # if self.menubardata_New_member:
        #     self.actionFile = menubar.addMenu("Neues Mitglied onbording")
        #     for menuline in self.menubardata_New_member:
        #         action = QtWidgets.QAction(menuline[0], self)
        #         action.triggered.connect(menuline[2])
        #         if menuline[1]:
        #             action.setShortcut(menuline[1])
        #         self.actionFile.addAction(action)





        self.overallverticallayout.addWidget(menubar)

        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.verticalLayout0 = QtWidgets.QVBoxLayout() 
        self.verticalLayout1 = QtWidgets.QVBoxLayout()
        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.verticalLayout0 = QtWidgets.QVBoxLayout()  # layout on the left with the masslist, and other stuff
        self.verticalLayout1 = QtWidgets.QVBoxLayout()  # laout on the right with the graph
        self.table_0_0 = TableView()
        self.table_0_1 = TableView()
        self.table_1_0 = TableView()
        self.table_1_1 = TableView(self.loaded_filepaths,clickable=True)
        self.init_loading_functionality(self.table_1_1)

        self.horizontalLayout.addLayout(self.verticalLayout1)
        self.horizontalLayout.addLayout(self.verticalLayout0)
        self.verticalLayout0.addWidget(QLabel("Rechnungsdaten KonsumentInnen"))
        self.verticalLayout0.addWidget(self.table_0_0)
        self.verticalLayout0.addWidget(QLabel("Energiedaten"))
        self.verticalLayout0.addWidget(self.table_0_1)
        self.verticalLayout0.setStretch(1, 7)
        self.verticalLayout0.setStretch(3, 7)

        self.verticalLayout1.addWidget(QLabel("Rechnungsdaten ProduzentInnen"))
        self.verticalLayout1.addWidget(self.table_1_0)
        self.verticalLayout1.addWidget(QLabel("Dateien geladen:"))
        self.verticalLayout1.addWidget(self.table_1_1)
        self.verticalLayout1.setStretch(1, 7)
        self.verticalLayout1.setStretch(3, 4)

        self.overallverticallayout.addLayout(self.horizontalLayout)



        self.overallverticallayout.addLayout(self.horizontalLayout)
        self.setCentralWidget(self.centralwidget)

    def init_data(self):
        #self.mandates = mandates
        self.invoices = invoices
        self.emails = emails
        self.masterdata = masterdata
        self.energydata = energydata
        self.new_member = newmember


    def init_loading_functionality(self,table_widget_in_which_loading_is_done):

        def updatetable_1_1():
            table_widget_in_which_loading_is_done.set_new_data(self.loaded_filepaths)

        def import_invoice_data():
            print("import invoice data")
            filepath = load_filepath(self,"Importiere Rechnungen von EEG Faktura",homedir= self.home_directory)
            if filepath is not None:
                self.loaded_filepaths.loc[self.loaded_filepaths["Daten"][self.loaded_filepaths["Daten"] == "Rechnungsdaten"].index, "Speicherort"] = filepath


                invoicedata= self.invoices.load_data(filepath=filepath)
                if invoicedata is not None:
                    invoicequart = invoicedata["detailed"]["Abrechnung"].iloc[0]
                    invoices_year, invoices_quart = invoicequart.split("-")[-2], invoicequart.split("-")[-1]
                    self.thisinvoices_year = invoices_year
                    self.thisinvoice_quart = invoices_quart
                    debit = invoicedata["list"][(invoicedata["list"]["Dokumenttyp"] == "Rechnung")]
                    transfer = invoicedata["list"][(invoicedata["list"]["Dokumenttyp"] == "Gutschrift")|(invoicedata["list"]["Dokumenttyp"] == "Information")]

                    self.reload_table_view("0_0",debit)
                    self.reload_table_view("1_0",transfer)

                    updatetable_1_1()
                    self.invoicesdata_loaded = True
                else:
                    print()

        def load_faktura_new_member_export_template():
            def load_faktura_template(filepath, nc_loading=False, nc_instance=""):
                if filepath is not None:
                    new_memberdata = self.new_member.load_template(filepath=filepath, nc=nc_loading, nc_instance=nc_instance)
                    if new_memberdata is not None:
                        self.loaded_filepaths.loc[self.loaded_filepaths["Daten"][
                            self.loaded_filepaths["Daten"] == "Vorlage EEG Faktura Stammdaten Export"].index, "Speicherort"] = filepath
                        self.new_membersdata_loaded = True
                        # self.table_1_1.set_new_data(self.loaded_filepaths.iloc[0:3])
                        updatetable_1_1()
                else:
                    return None
            filepath=""
            if not filepath:
                print("Load faktura_new_member_export_template")
                dlg = QMessageBox(self)
                questiontext = f"Ich kann die die Vorlage zu Faktura Export von folgendem Pfad herunteladen:"
                questiontext += f"\n\n{self.nc_faktura_export_template_fp}"
                questiontext += "\n\nSoll ich es von diesem Pfad herunterladen, oder willst du lokal eine Datei von deinem Computer auswählen?"
                dlg.setText(questiontext)
                dlg.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
                prompt = dlg.exec()


                if prompt == QMessageBox.Yes:
                    pass

                else:
                    filepath = load_filepath(self,"Lade Vorlage zu Faktura Export",homedir= self.home_directory)
                    load_faktura_template(filepath = filepath)
            else:
                load_faktura_template(filepath = filepath)

        def load_template_invoice_from_fp(filepath):
            if filepath:
                invoices_template = self.invoices.load_template(filepath=filepath)
                if invoices_template is not None:
                    self.loaded_filepaths.loc[self.loaded_filepaths["Daten"][
                        self.loaded_filepaths["Daten"] == "Rechnungen Vorlage"].index, "Speicherort"] = filepath
                    updatetable_1_1()
            else:
                return None

        def select_template_invoice():
            print("Select template invoice export")
            filepath = load_filepath(self,"Wähle das Template für Rechnungen aus", filter="Word Document (*.docx)",homedir= self.home_directory)
            if filepath is not None:
                load_template_invoice_from_fp(filepath)

        def loadp_masterdata_from_fp(filepath):
            if filepath is not None:
                masterdata = self.masterdata.load_data(filepath=filepath)
                masterdata_meta = self.masterdata.load_metadata(filepath=filepath)
                mailadresses = self.emails.load_data(filepath=filepath)
                if masterdata is not None:
                    self.loaded_filepaths.loc[self.loaded_filepaths["Daten"][
                        self.loaded_filepaths[
                            "Daten"] == "EEG Faktura Stammdaten"].index, "Speicherort"] = filepath
                    updatetable_1_1()
            else:
                return None

        def import_masterdata_data():
            print("Import the data on every person out of EEG faktura")
            filepath = load_filepath(self,"Wähle die Masterdaten von Faktura aus.",homedir= self.home_directory)
            if filepath is not None:
                loadp_masterdata_from_fp(filepath)

        def load_energydata_fp(filepath, load_qov = False):
            if filepath is not None:
                energydata = None
                energydataqov = None
                if load_qov:
                    energydataqov = self.energydata.load_metadata(filepath=filepath)
                else:
                    energydata = self.energydata.load_data(filepath=filepath)

                if (energydata is not None) or (energydataqov is not None):
                    if load_qov:
                        self.reload_table_view("0_1", energydataqov)
                        self.loaded_filepaths.loc[self.loaded_filepaths["Daten"][
                            self.loaded_filepaths["Daten"] == "EEG Faktura Quartalsenergiedaten QOV"].index, "Speicherort"] = filepath
                    else:
                        self.reload_table_view("0_1", energydata)
                        self.loaded_filepaths.loc[self.loaded_filepaths["Daten"][
                            self.loaded_filepaths["Daten"] == "EEG Faktura Quartalsenergiedaten"].index, "Speicherort"] = filepath

                    updatetable_1_1()
            else:
                return None

        def import_energy_data(load_qov = False):
            print("Import the energydata out of EEG faktura")
            filepath = load_filepath(self,"Wähle die Energiedaten für diese Quartal aus",homedir= self.home_directory)
            if filepath is not None:
                load_energydata_fp(filepath, load_qov = load_qov)

        def load_emaildata_fp(filepath):
            if filepath:
                email_temp = self.emails.load_template(filepath=filepath)
                if email_temp is not None:
                    self.loaded_filepaths.loc[self.loaded_filepaths["Daten"][
                        self.loaded_filepaths["Daten"] == "Emails Vorlage"].index, "Speicherort"] = filepath
                    updatetable_1_1()
            else:
                return None

        def import_email_template():
            print("Import the email template ")
            filepath = load_filepath(self,"Wähle die Emailvorlage aus.",filter ="Docx (*.docx)",homedir= self.home_directory)
            if filepath is not None:
                load_emaildata_fp(filepath)


        allfunctions = [import_invoice_data, import_masterdata_data,import_energy_data,partial(import_energy_data,load_qov = True), select_template_invoice,import_email_template]

        for index,function in enumerate(allfunctions):
            table_widget_in_which_loading_is_done.functions_on_row_clicked[index] = function

        # Auto-load the templates named in .env. Both loaders return early on an
        # empty path, so an install with no templates configured still starts.
        load_template_invoice_from_fp(self.config.get("template_export_invoice", ""))
        load_emaildata_fp(self.config.get("template_email", ""))


        # loadp_masterdata_from_fp(self.loaded_filepaths.loc[self.loaded_filepaths["Daten"] == "EEG Faktura Stammdaten","Speicherort"].iloc[0])
        # print("loaded masterdata")

    
    def init_menubardata_Infinity(self):

        def export_csv():
            print("Export cvs")
            check,datamissing = check_whether_data_exists(invoices = self.invoices, invoicedatarequired=True)
            print(f"Check was {check}, datamissing {datamissing}")

            if check:
                if self.exportwindow is None:
                    #data check

                    self.exportwindow = Subwindow("Exportiere .csv für SEPA")
                    self.exportwindow.resize(500, 100)
                    self.exportwindow.move(30, 30)
                    self.exportwindow.tablegrid = QGridLayout()
                    self.exportwindow.tablegrid.setColumnStretch(0,1)
                    self.exportwindow.tablegrid.setColumnStretch(1,10)
                    self.exportwindow.tablegrid.setColumnStretch(2,5)
                    self.exportwindow.totalsum = QGridLayout()
                    self.exportwindow.totalsum.setColumnStretch(0,1)
                    self.exportwindow.totalsum.setColumnStretch(1,10)
                    self.exportwindow.totalsum.setColumnStretch(2,5)



                    header_layout = QHBoxLayout()

                    # Add header labels to the header layout
                    header_label1 = QLabel("")
                    header_label2 = QLabel("Name")
                    header_label3 = QLabel("Betrag [€]")
                    header_layout.addWidget(header_label1)
                    header_layout.addWidget(header_label2)
                    header_layout.addWidget(header_label3)
                    header_layout.setStretch(0,1)
                    header_layout.setStretch(1,10)
                    header_layout.setStretch(2,5)


                    self.exportwindow.list_data = []

                    names = []
                    amounts = []
                    for idx, person in self.invoices.data["list"].iterrows():
                        name = person["Empfänger Vorame"]
                        if not pd.isna(person["Empfänger Nachname"]):
                            name += f" {person['Empfänger Nachname']}"
                        names.append(name)
                        if person["Dokumenttyp"] == "Rechnung":
                            amounts.append(-person["Rechnungsbetrag Brutto"])
                        else: amounts.append(person["Rechnungsbetrag Brutto"])

                    # mandatesexist = []
                    # for name in names:
                    #     if (mandates.data["Zahlungspflichtiger Name"] == name).any():
                    #         mandatesexist.append("x")
                    #     else: mandatesexist.append("")

                    for index,(name,amount) in enumerate(zip(names,amounts)):
                        index += 1
                        checkbox = QCheckBox()
                        checkbox.setChecked(True)
                        col1 = QLabel(str(name))
                        col2 = QLabel(str(amount))

                        self.exportwindow.tablegrid.addWidget(checkbox,index,0)
                        self.exportwindow.tablegrid.addWidget(col1,index,1)
                        self.exportwindow.tablegrid.addWidget(col2,index,2)

                        self.exportwindow.list_data.append(checkbox)
                    totalsum = np.array(amounts).sum()
                    self.exportwindow.totalsum.addWidget(QLabel("Gesamt"),0,1)
                    self.exportwindow.totalsum.addWidget(QLabel(f"€ {totalsum:.2f}"),0,2)

                    # print(self.exportwindow.tablegrid.rowCount())
                    # for i in range(0,self.exportwindow.tablegrid.rowCount()):
                    #     self.exportwindow.tablegrid.setRowStretch(i, 0)



                    def get_selected_names():
                        # One checkbox per row of data["list"], built in row order
                        # above, so this mask indexes that frame directly.
                        selected_mask = [cb.isChecked() for cb in self.exportwindow.list_data]
                        invoices_selected_names, selected_names = select_invoice_positions(
                            self.invoices.data["list"], self.invoices.data["detailed"], selected_mask)
                        if selected_names.empty:
                            QMessageBox.warning(self, "Keine Auswahl",
                                                "Es ist niemand ausgewählt - es wird nichts exportiert.")
                            return
                        print(f"{len(selected_names)} von {len(selected_mask)} Empfänger:innen ausgewählt")

                        exportingdebit,exportingtransfer,doublesprocess = produce_sepa_export_dfs(invoices_selected_names,self.config.get("EEG_name",""))

                        date_str = datetime.date.today().strftime("%d_%m_%Y")

                        def save_csv(df, filepath, what):
                            """Write one export file. Returns True only if it landed.

                            The caller must stop on False: a half-written pair,
                            where the transfers file exists and the direct debits
                            do not, looks exactly like a clean run.
                            """
                            if not filepath.lower().endswith(".csv"):
                                filepath = f"{filepath}.csv"
                            print(f"Export {what} to: {filepath}")
                            try:
                                df.to_csv(filepath, index=False, sep=";")
                                return True
                            except Exception as e:
                                print(f"Saving {what} failed: {e}")
                                QMessageBox.critical(self, "Speichern fehlgeschlagen",
                                                     f"{what} konnten nicht gespeichert werden:\n{filepath}\n\n{e}")
                                return False

                        filepath1 = load_filepath(self, "Wähle Speicherort für Export für SEPA Lastschrift aus",
                                                  filter="csv (*.csv)", fileex=False,
                                                  defaultfilename=f"Lastschriften_Infinity_export_{date_str}",
                                                  homedir=self.home_directory)

                        if exportingdebit is not None:
                            if filepath1 is None:
                                return
                            if not save_csv(exportingdebit, filepath1, "Lastschriften"):
                                return

                        if exportingtransfer is not None:
                            homedir2 = os.path.dirname(filepath1) if filepath1 else self.home_directory
                            filepath2 = load_filepath(self,"Wähle Speicherort für Export für Überweisungen aus",
                                                      filter="csv (*.csv)", fileex=False,
                                                      defaultfilename=f"Überweisungen_Infinity_export_{date_str}",
                                                      homedir=homedir2)
                            if filepath2 is not None:
                                if not save_csv(exportingtransfer, filepath2, "Überweisungen"):
                                    return

                        self.exportwindow.close()
                        self.exportwindow = None   # otherwise the menu entry needs two clicks next time
                        return selected_names


                    self.exportwindow.ok_button = QPushButton("OK")
                    self.exportwindow.ok_button.pressed.connect(get_selected_names)
                    self.exportwindow.overallverticallayout.addLayout(header_layout)
                    self.exportwindow.overallverticallayout.addLayout(self.exportwindow.tablegrid)
                    self.exportwindow.overallverticallayout.addLayout(self.exportwindow.totalsum)

                    # self.exportwindow.overallverticallayout.addWidget(self.exportwindow.list_widget)
                    self.exportwindow.overallverticallayout.addWidget(self.exportwindow.ok_button)



                    self.exportwindow.show()
                else:
                    self.exportwindow.close()  # Close window.
                    self.exportwindow = None  # Discard reference.

            else:
                errorbox = QMessageBox()
                text = "Für diesen Schritt müssen noch folgende Daten eingelesen werden:"
                for missing in datamissing:
                    text += f"\n- {missing}"
                errorbox.setText(text)
                errorbox.exec_()
        def reload_table_view(tablenr,data):
            """

            :param tablenr: in columns on the grid "0_0","0_1","1_0"
            :param data: as a Pandas Dataframe
            :return:
            """
            tabledict = {"0_0":self.table_0_0,
                         "0_1": self.table_0_1,
                         "1_0": self.table_1_0,
                         }
            tabledict[tablenr].set_new_data(data)

        self.reload_table_view = reload_table_view

        menubardata = [
                            ["Exportiere .csv Datei für Raiffeisen Infinty", "", export_csv]]
        # ["Importiere Rechnungdaten von EEG Faktura", "", import_invoice_data],
        # ["Lade Daten von SEPA Mandate", "", import_mandates],
        return menubardata


    def init_menubardata_new_member(self):
        def load_Mail():
            print("Load Mail")

            # def selectmail(imap):
            #     print("Select mail out of list")
            #     self.mailselectionprompt = MailSelection("Select the Mail",imap=imap,functiononnewmemberparse=self.new_member.load_data)
            #     self.mailselectionprompt.show()

            def try_logging_in_f(user, pw):
                print(f"try logging in to IMAP server as {user}")
                imap = imaplib.IMAP4_SSL(self.imap_server)
                # # authenticate
                imap.login(user, pw)
                selectmail(self,imap)

            self.loginprompt = LoginPrompt(try_logging_in_f,title = "Email Login")
            self.loginprompt.show()
            try_logging_in_f( self.config.get("my_mail", ""), self.config.get("my_mail_pw", ""))

        def show_new_member():
            print(self.new_member.data)

        """
        def export_for_faktura():
            print("Faktura Export")
            check, datamissing =  check_whether_data_exists(newmember=self.new_member,newmemberdatarequired=True, newmembertemprequired=True)
            print(f"Check was {check}, datamissing {datamissing}")
            if not check:
                errorbox = QMessageBox()
                text = "Für diesen Schritt müssen noch folgende Daten eingelesen werden:"
                for missing in datamissing:
                    text += f"\n- {missing}"
                errorbox.setText(text)
                errorbox.exec_()
            else:
                ws = newmember.template["EEG Stammdaten"]
                matchingdict = {

                    "Postleitzahl":"D10",
                    "Stadt/Ort":"E10",
                    "Straße":"F10",
                    "Hausnummer":"G10",
                    "Vorname":"U10",
                    "Nachname":"V10",
                    "IBAN":"Z10",
                    "Name auf Bankkarte":"AA10",
                    "E-Mail":"AC10",
                    "Telefonnummer":"AD10",




                }
                valuesmissing = []
                for match in matchingdict:

                    try:
                        ws[matchingdict[match]] = self.new_member.data[match]
                    except:
                        print(f"{match} is missing")
                        valuesmissing.append(match = template_invoice_clean.docx)
                if valuesmissing:
                    errorbox = QMessageBox()
                    text = "Diese Werte fehlen:"
                    for missing in datamissing:
                        text += f"\n- {missing}"
                errorbox.setText(text)
                errorbox.exec_()
                if self.new_meif __name__ == "__main__":
    app = QApplication(sys.argv)
    dlg = SettingsDialog()
    if dlg.exec_() == QDialog.Accepted:
        print("Settings saved:", dlg.get_settings())
    else:
        print("Cancelled.")
    sys.exit(0)mber.data["Anmeldungstyp"] == "Produzent:in":
                    ws["L10"] = self.new_member.data['Einspeisezählpunkt-nummer']
                    ws["M10"] = "PRODUCTION"    #????
                    netzbetreibernummer = self.new_member.data['Einspeisezählpunkt-nummer'][0:8]
                    ws["A10"] = netzbetreibernummer
                elif self.new_member.data["Anmeldungstyp"] == "Konsument:in":
                    ws["L10"] = self.new_member.data['Zählpunktnummer']
                    netzbetreibernummer = self.new_member.data['Zählpunktnummer'][0:8]
                    ws["A10"] = netzbetreibernummer
                    ws["M10"] = "CONSUMPTION"
                if self.new_member.data["Ich bin"] == "Privatperson":
                    ws["X10"] = "privat"
                else:
                    ws["X10"] = self.new_member.data["bussines"]
                    ws["AF10"] = "USt. Nummer"

                ws["Y10"] = dt.datetime.today().strftime("%d.%m.%Y")
                ws["AI10"] =  dt.datetime.today().strftime("%d.%m.%Y")
                ws["B10"] = self.GEI_gemeinschafts_ID

                filepath = load_filepath(self,"Exportiere Daten von einem neunen Mitglied für EEG Faktura als .xlsx",fileex=False,homedir= self.home_directory)
                if filepath is not None:
                    if ".xlsx" not in filepath:
                        filepath = f"{filepath}.xlsx"
                        newmember.template.save(filepath)
        """

        # menubardata = [["Wähle eine Mail aus", "", load_Mail],["Zeige die Daten vom neuen Mitglied", "", show_new_member],["Exportiere Daten vom neuen Mitglied für EEG Faktura", "", export_for_faktura]]
        menubardata = [["Wähle eine Mail aus", "", load_Mail],["Zeige die Daten vom neuen Mitglied", "", show_new_member]]

        # ["Lade Vorlage zu Faktura Export", "", load_faktura_new_member_export_template]
        return menubardata

    def init_menubardata_make_invoices(self):
        def login_eeg_faktura():
            dlg = LoginDialog(parent=self)  # pass your main window as parent
            if dlg.exec_() == QDialog.Accepted:
                creds = dlg.get_credentials()
                print(creds)
                # creds["user"], creds["login"], creds["tenant"], creds["password"]
        def change_Settings():
            dlg = SettingsDialog()
            if dlg.exec_() == QDialog.Accepted:
                creds = dlg.get_credentials()
                print(creds)

        def check_energydata():
            print("I check the energydata")
            check,datamissing = check_whether_data_exists(energydata= self.energydata,energymetadatarequired= True)
            print(f"Check was {check}, datamissing {datamissing}")

            if check:
                qov_values = energydata.metadata.copy()
                qov_cols = energydata.metadata.columns.get_level_values(0) == "QoV"
                qov_values.columns = range(qov_values.shape[1])
                qov_values = qov_values.loc[:,qov_cols]
                qov_L3_values = (energydata.metadata.loc[:,qov_cols] == "L3").values
                times_qov_L3 = qov_L3_values.any(axis = 1)
                change = np.diff(times_qov_L3.astype(int))
                starts = np.where(change == 1)[0] + 1
                ends = np.where(change == -1)[0]
                if times_qov_L3[0]:
                    starts = np.insert(starts, 0, 0)
                if times_qov_L3[-1]:
                    ends = np.append(ends, len(times_qov_L3) - 1)

                qovL3_startendgroups = [(start,end) for start,end in zip(starts,ends)]
                report_list = []
                for start, end in qovL3_startendgroups:
                    columns_this_L3, = np.where(qov_L3_values[start])
                    names = np.unique(energydata.metadata.columns[qov_values.columns[columns_this_L3]-1].get_level_values('Name'))
                    shownames =', '.join(names)
                    if names.shape[0] > 3:
                        shownames = "All"
                    Metering_points = np.unique(energydata.metadata.columns[qov_values.columns[columns_this_L3]-1].get_level_values('MeteringpointID'))
                    days = (energydata.metadata.index[start].date(),energydata.metadata.index[end].date())
                    timerange = f"{energydata.metadata.index[start]} - {energydata.metadata.index[end]}"
                    print(days,timerange,names,Metering_points)
                    line = [energydata.metadata.index[start].date(),energydata.metadata.index[end].date(),shownames,timerange,', '.join(names),', '.join(Metering_points)]
                    report_list.append(line)
                report_df = pd.DataFrame(report_list,columns = ["Start Datum", "End Datum", "Namen Übersicht", "Zeitraum Details","Namen Details", "ZP Details"])
                if report_df.shape[0] == 0:
                    message = QMessageBox()
                    text = "Überprüfung durchgeführt. \nAlle QoV Energiedaten sind mindestens L2"
                    message.setText(text)
                    message.exec_()
                else:
                    self.safepath_this_energyreport = load_filepath(self,
                                                                    "Wo soll den Überprüfungsreport hinspeichern?.",
                                                                    fileex=False,
                                                                    defaultfilename=f"Energydata_QoV_Report_{energydata.metadata.index[0].strftime("%Y_%m_%d")}-{energydata.metadata.index[-1].strftime("%Y_%m_%d")}.xlsx",
                                                                    homedir=self.home_directory)
                    if not self.safepath_this_energyreport.lower().endswith(".xslx"):
                        self.safepath_this_energyreport += ".xlsx"
                    print(f"Save qov Report to: {self.safepath_this_energyreport}")
                    report_df.to_excel(self.safepath_this_energyreport)
                    try:
                        os.startfile(self.safepath_this_energyreport)
                    except:
                        subprocess.Popen(["libreoffice", self.safepath_this_energyreport])



            else:
                errorbox = QMessageBox()
                text = "Für diesen Schritt müssen noch folgende Daten eingelesen werden:"
                for missing in datamissing:
                    text += f"\n- {missing}"
                errorbox.setText(text)
                errorbox.exec_()


        def create_invoices_and_save():
            print("I try to create the invoices and the save it.")
            check,datamissing = check_whether_data_exists(invoices = self.invoices, energydata= self.energydata,masterdata=self.masterdata,invoicedatarequired=True, invoicestemprequired=True, masterdatarequired=True)
            print(f"Check was {check}, datamissing {datamissing}")
            # if "Energiedaten" in datamissing:
            #     errorbox = QMessageBox()
            #     text = "Die Energiedaten fehlen, du kannst aber trotzdem fortfahren"
            #     errorbox.setText(text)
            #     errorbox.exec_()
            if check:
                # first create a dict with all the info for the invoice, then render the template, then do it for all persons.
                self.safepath_this_invoices = load_filepath(self, "Wo soll ich die Rechnungen hinspeichern?.", pathisdir=True,homedir= self.home_directory)
                if self.safepath_this_invoices is not None:
                    print(f"Save to {self.safepath_this_invoices}")
                    # for loading screeen i need multithreading
                    class Worker(QObject):
                        progress = pyqtSignal(str)
                        finished = pyqtSignal()

                        def __init__(self, task_func):
                            super().__init__()
                            self.task_func = task_func

                        def run(self):
                            self.task_func(self.progress.emit,self.finished.emit)

                    class StatusDialog(QDialog):
                        def __init__(self):
                            super().__init__()
                            self.setWindowTitle("Arbeitet...")
                            self.label = QLabel("Preparing...")
                            layout = QVBoxLayout()
                            layout.addWidget(self.label)
                            self.setLayout(layout)

                        def update_text(self, message):
                            self.label.setText(message)

                    def task_for_worker(callback,finished):
                        produce_invoices_and_save(self.energydata.data, invoices.data["detailed"], self.masterdata, self.invoices.template,
                                                  self.safepath_this_invoices,callback,finished)

                    dialog = StatusDialog()
                    dialog.show()

                    thread = QThread()
                    worker = Worker(task_for_worker)
                    worker.moveToThread(thread)

                    worker.progress.connect(dialog.update_text)
                    worker.finished.connect(thread.quit)
                    worker.finished.connect(dialog.accept)
                    thread.started.connect(worker.run)

                    thread.start()
                    dialog.exec_()
                else:
                    print("no fp selected")


            else:
                errorbox = QMessageBox()
                text = "Für diesen Schritt müssen noch folgende Daten eingelesen werden:"
                for missing in datamissing:
                    text += f"\n- {missing}"
                errorbox.setText(text)
                errorbox.exec_()

        def send_invoices_mail():
            print("Send all invoices to the mailing list")
            print("Load Mail")
            # print(self.invoices.data)
            check,datamissing = check_whether_data_exists(invoices = self.invoices, masterdata=self.masterdata,emails= self.emails,invoicedatarequired=True, masterdatarequired= True,emailstemprequired=True)
            if check:
                personswithinvoicesmasterdata = self.masterdata.data.loc[(self.masterdata.data["Name 1"]).isin(self.invoices.data["detailed"]["Empfänger Vorame"]) & (self.masterdata.data["Name 2"]).isin(self.invoices.data["detailed"]["Empfänger Nachname"]),:]
                # print(personswithinvoicesmasterdata)
                personswithinvoicesmasterdata = personswithinvoicesmasterdata[["Name 1","Name 2","E-Mail"]].drop_duplicates()

                def try_logging_in_f(user, pw, host):
                    print(f"try logging in to IMAP server as {user}")
                    try:
                        imap = imaplib.IMAP4_SSL(host)
                        # # authenticate
                        imap.login(user, pw)
                        return True
                    except:
                        return False

                # either do the login prompt and then execute the function or just execute the funciton
                # self.loginprompt = LoginPrompt(try_logging_in_f, title="Email Login")
                logged_in = try_logging_in_f(self.config.get("my_mail", ""), self.config.get("my_mail_pw", ""), self.config.get("imap_server", ""))
                if logged_in:
                    mailadressselection = MailAdressSelection(personswithinvoicesmasterdata["E-Mail"], title="Wähle die Personen aus, denen du eine Mail schreiben willst")
                    if mailadressselection.exec_():  # This blocks until dialog is closed
                        selected_persons  = None
                        selected_persons = mailadressselection.result
                        print("Returned from dialog:", selected_persons)
                    else:
                        print("Dialog canceled")
                    if selected_persons is not None:
                        personswithinvoicesselected = personswithinvoicesmasterdata.loc[selected_persons,:]
                        sendapproval = Sendapproval(personswithinvoicesselected["E-Mail"], title="Wähle die Personen aus, denen du eine Mail schreiben willst")
                        if sendapproval.exec_():  # This blocks until dialog is closed
                            send_y_n = sendapproval.result
                            print("Returned from dialog:", send_y_n)
                        else:
                            print("Dialog canceled")
                        if send_y_n:
                            print(f"Send Mails to {personswithinvoicesselected["E-Mail"]}")
                            if not self.safepath_this_invoices:
                                self.safepath_this_invoices = load_filepath(self, "In welchem Ordner sind die ganzen Rechnungen gespeichert?", pathisdir=True,homedir= self.home_directory)



                            for ind, person_data in personswithinvoicesselected.iterrows():
                                print(f"Send Mail to: {person_data['E-Mail']}")

                                receivername = f"{person_data["Name 1"]}_{person_data["Name 2"]}"
                                invoicequart = invoices.data["detailed"]["Abrechnung"].iloc[0]
                                email_this = person_data["E-Mail"]
                                invoices_year, invoices_quart = invoicequart.split("-")[-2], invoicequart.split("-")[-1]
                                self.thisinvoices_year = invoices_year
                                self.thisinvoice_quart = invoices_quart
                                nameinvoicefile = f"Rechnung_{self.thisinvoices_year}_q{self.thisinvoice_quart}_{receivername}.pdf"

                                fpinvoicefile = os.path.join(self.safepath_this_invoices , nameinvoicefile)
                                send_mail_to_one_person(self.config.get("my_mail", ""),self.config.get("my_mail_pw", ""), self.config.get("imap_server", ""),self.config.get("EEG_name", ""),email_this,person_data["Name 1"],
                                                        self.thisinvoice_quart, self.thisinvoices_year, self.emails.template, fpinvoicefile, masterdata)


                        else: print("Dont send")
                    else:
                        print("Abort since nobody was selected")#

                else:
                    # Never echo the password here - this dialog is exactly what
                    # a user screenshots when asking for help.
                    mail_adresse = self.config.get("my_mail", "(nicht gesetzt)")
                    mail_server = self.config.get("imap_server", "(nicht gesetzt)")
                    errorbox = QMessageBox()
                    errorbox.setWindowTitle("Anmeldung fehlgeschlagen")
                    text = ("Anmeldung beim Mailserver nicht möglich."
                            f"\n\nMail Adresse: {mail_adresse}"
                            f"\nServer: {mail_server}"
                            "\n\nDas Passwort wurde abgelehnt. Bitte in den Einstellungen prüfen.")
                    for missing in datamissing:
                        text += f"\n- {missing}"
                    errorbox.setText(text)
                    errorbox.exec_()
            else:
                errorbox = QMessageBox()
                text = "Für diesen Schritt müssen noch folgende Daten eingelesen werden:"
                for missing in datamissing:
                    text += f"\n- {missing}"
                errorbox.setText(text)
                errorbox.exec_()

                # for
                #     # MailAdressSelection(self.emails, "An welche Mailadressen soll ich die Rechnungen schicken")
        # when we have api capabilities we can use this
        # ["Login in EEG Faktura", "", login_eeg_faktura],
        menubardata = [["Überprüfe die Energiedatenqualität","",check_energydata],["Erstelle alle Rechnungen", "", create_invoices_and_save],["Verschicke die Rechnungen per Mail", "", send_invoices_mail],["Settings", "", change_Settings]]
        return menubardata


def main():
    app = QtWidgets.QApplication(sys.argv)
    main = MainWindow()
    main.show()
    sys._excepthook = sys.excepthook

    def exception_hook(exctype, value, traceback):
        print("silent error")
        print(exctype, value, traceback)
        sys._excepthook(exctype, value, traceback)
        sys.exit(1)

    sys.excepthook = exception_hook
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()