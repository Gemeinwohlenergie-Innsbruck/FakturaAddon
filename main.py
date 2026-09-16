import datetime
import subprocess
import traceback
import threading
import numpy as np
import json
from functools import partial
import pandas as pd
from pathlib import Path
import os
from subwindows import  Subwindow
from PyQt5.QtCore import *
from PyQt5 import QtWidgets, QtGui, QtCore
from PyQt5.QtGui import QBrush, QColor
import sys
from PyQt5.QtWidgets import QLabel, QFileDialog, QMessageBox, QGridLayout, QTableWidget, QTableWidgetItem, QListWidget, QWidget, QListWidgetItem, QCheckBox, QListWidgetItem, QPushButton, QVBoxLayout, QDialog
from importing import invoices,emails, masterdata,energydata,load_filepath, check_whether_data_exists, newmember, LoginDialog, SettingsDialog
from exporting import produce_sepa_export_dfs, produce_invoices_and_save
from selection import select_invoice_positions, members_with_invoices
from config import ENV_PATH, load_env
import validation
import theme
from exporting import resolve_name_in_energydata
from PyQt5.QtWidgets import QHBoxLayout
import datetime as dt
import imaplib
from emailing import (MailSelection, LoginPrompt, selectmail, MailAdressSelection,
                      send_mail_to_one_person, build_invoice_email, SendPreviewDialog)
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
    def set_new_data(self,data, editable = False, maxrows = 200):
        # Slice first, then copy - copying the whole frame to keep 200 rows is
        # wasted work on a big energy export.
        datacopy = data.iloc[0:maxrows].copy()
        self.data = datacopy.to_dict(orient="list")
        self.setData(datacopy.shape[0],datacopy.shape[1], editable= editable)
        hidden = data.shape[0] - datacopy.shape[0]
        if hidden > 0:
            # Truncating in silence reads as "those members are missing from
            # the import". Say it out loud in a final row.
            self.insertRow(self.rowCount())
            note = QtWidgets.QTableWidgetItem(
                f"… {hidden} weitere Zeilen nicht angezeigt ({data.shape[0]} gesamt)")
            note.setFlags(note.flags() & ~Qt.ItemIsEditable & ~Qt.ItemIsSelectable)
            self.setItem(self.rowCount() - 1, 0, note)
            if self.columnCount() > 1:
                self.setSpan(self.rowCount() - 1, 0, 1, self.columnCount())
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

class FileLoadPanel(QtWidgets.QWidget):
    """The 'Dateien geladen' list, as a form with real buttons.

    This used to be a QTableWidget whose rows happened to respond to clicks -
    no button, no cursor change, no tooltip, so there was nothing to tell the
    user that clicking a row was how you loaded a file.
    """

    def __init__(self, rows, parent=None):
        super().__init__(parent)
        self._paths = {}
        self._status = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 0)
        self._buttons = {}
        for row, (key, label) in enumerate(rows):
            name = QLabel(label)
            status = QLabel("nicht geladen")
            status.setStyleSheet("color: palette(mid);")
            status.setWordWrap(False)
            status.setTextInteractionFlags(Qt.TextSelectableByMouse)
            button = QPushButton("Durchsuchen…")
            button.setToolTip(f"{label} auswählen und laden")
            grid.addWidget(name, row, 0)
            grid.addWidget(status, row, 1)
            grid.addWidget(button, row, 2)
            self._status[key] = status
            self._buttons[key] = button
        grid.setRowStretch(len(rows), 1)

    def set_handler(self, key, handler):
        self._buttons[key].clicked.connect(handler)

    def set_path(self, key, path):
        """Show a loaded file by name, with the full path on hover."""
        self._paths[key] = path
        label = self._status[key]
        if path:
            label.setText(f"✓ {os.path.basename(path)}")
            label.setToolTip(path)
            label.setStyleSheet(f"color: {theme.OK};")
        else:
            label.setText("nicht geladen")
            label.setToolTip("")
            label.setStyleSheet(f"color: {theme.MUTED};")

    def path(self, key):
        return self._paths.get(key, "")


def open_in_default_app(path):
    """Open a file with whatever the OS uses for it. Returns True on success.

    os.startfile exists only on Windows - on macOS it raises AttributeError,
    which the old code caught and followed with a hardcoded `libreoffice`
    call, a binary that is on PATH on neither macOS nor Windows. So the QoV
    report saved correctly and then silently failed to open anywhere except
    a Linux box with LibreOffice installed.
    """
    try:
        if sys.platform == "win32":
            os.startfile(path)                          # noqa: S606 - Windows only
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])
        return True
    except Exception as e:
        print(f"Could not open {path} automatically: {e}")
        return False


class ValidationDialog(QDialog):
    """Findings from the pre-flight checks, worst first."""

    SEVERITY_LABEL = {validation.ERROR: "Fehler",
                      validation.WARNING: "Warnung",
                      validation.INFO: "Hinweis"}
    SEVERITY_COLOUR = {validation.ERROR: theme.ERROR,
                       validation.WARNING: theme.WARNING,
                       validation.INFO: theme.BLUE}

    def __init__(self, findings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Datenprüfung")
        self.resize(760, 520)
        self.findings = findings

        layout = QVBoxLayout(self)
        errors = sum(1 for f in findings if f.severity == validation.ERROR)
        warnings = sum(1 for f in findings if f.severity == validation.WARNING)

        summary = QLabel()
        if not findings:
            summary.setText("Keine Probleme gefunden.")
        else:
            parts = []
            if errors:
                parts.append(f"{errors} Fehler")
            if warnings:
                parts.append(f"{warnings} Warnung(en)")
            rest = len(findings) - errors - warnings
            if rest:
                parts.append(f"{rest} Hinweis(e)")
            summary.setText(" · ".join(parts))
        summary.setStyleSheet("font-weight: 600; padding: 4px;")
        layout.addWidget(summary)

        tree = QtWidgets.QTreeWidget()
        tree.setHeaderLabels(["", "Bereich", "Befund"])
        tree.setColumnWidth(0, 80)
        tree.setColumnWidth(1, 160)
        for finding in findings:
            item = QtWidgets.QTreeWidgetItem(
                [self.SEVERITY_LABEL.get(finding.severity, finding.severity),
                 finding.category, finding.message])
            item.setForeground(0, QBrush(QColor(self.SEVERITY_COLOUR.get(finding.severity, "#333"))))
            for row in finding.rows:
                item.addChild(QtWidgets.QTreeWidgetItem(["", "", str(row)]))
            # Expand short lists; a hundred names stays collapsed.
            item.setExpanded(0 < len(finding.rows) <= 8)
            tree.addTopLevelItem(item)
        layout.addWidget(tree, 1)

        buttons = QHBoxLayout()
        copy_button = QPushButton("Bericht kopieren")
        copy_button.clicked.connect(self.copy_report)
        buttons.addWidget(copy_button)
        buttons.addStretch(1)
        close_button = QPushButton("Schließen")
        close_button.setDefault(True)
        close_button.clicked.connect(self.accept)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)

    def report_text(self):
        lines = []
        for finding in self.findings:
            lines.append(f"[{self.SEVERITY_LABEL.get(finding.severity, finding.severity)}] "
                         f"{finding.category}: {finding.message}")
            lines.extend(f"    - {row}" for row in finding.rows)
        return "\n".join(lines) or "Keine Probleme gefunden."

    def copy_report(self):
        QtWidgets.QApplication.clipboard().setText(self.report_text())


class WorkflowPanel(QtWidgets.QWidget):
    """The quarterly sequence, as an actual sequence.

    The menus gave two unrelated groups of always-enabled actions, so the order
    of the work lived only in people's heads: you clicked "Verschicke die
    Rechnungen" and found out afterwards, via a dialog, what was missing. Each
    step here is enabled only once its inputs exist, and says what it is
    waiting for while it is not.
    """

    def __init__(self, steps, parent=None):
        super().__init__(parent)
        self._buttons = {}
        self._markers = {}
        self._reasons = {}
        grid = QGridLayout(self)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setColumnStretch(0, 0)
        grid.setColumnStretch(1, 0)
        grid.setColumnStretch(2, 1)
        for row, (key, title, optional) in enumerate(steps):
            marker = QLabel("○")
            marker.setFixedWidth(16)
            button = QPushButton(f"{row + 1}. {title}" + ("  (optional)" if optional else ""))
            button.setObjectName("stepButton")
            button.setMinimumWidth(240)
            reason = QLabel("")
            reason.setWordWrap(True)
            reason.setStyleSheet("color: palette(mid);")
            grid.addWidget(marker, row, 0)
            grid.addWidget(button, row, 1)
            grid.addWidget(reason, row, 2)
            self._markers[key] = marker
            self._buttons[key] = button
            self._reasons[key] = reason
        grid.setRowStretch(len(steps), 1)

    def set_handler(self, key, handler):
        self._buttons[key].clicked.connect(handler)

    def set_state(self, key, missing, done):
        """missing: labels of inputs not yet loaded. done: step has been run."""
        ready = not missing
        self._buttons[key].setEnabled(ready)
        marker = self._markers[key]
        button = self._buttons[key]
        button.setProperty("done", "true" if done and not missing else "false")
        button.style().unpolish(button)
        button.style().polish(button)
        if missing:
            reason = "wartet auf: " + ", ".join(missing)
            marker.setText("○")
            marker.setStyleSheet(f"color: {theme.MUTED};")
            self._buttons[key].setToolTip(reason)
        elif done:
            reason = "erledigt"
            marker.setText("✓")
            marker.setStyleSheet(f"color: {theme.OK}; font-weight: 600;")
            self._buttons[key].setToolTip("")
        else:
            reason = "bereit"
            marker.setText("▶")
            marker.setStyleSheet(f"color: {theme.ORANGE_DARK}; font-weight: 600;")
            self._buttons[key].setToolTip("")
        self._reasons[key].setText(reason)


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, *args, **kwargs):
        super(MainWindow, self).__init__(*args, **kwargs)
        print("Initializing Window")
        self.setWindowTitle("Faktura Infinity Addon")
        # Default size only; restore_geometry() overrides it with the size and
        # position the window was last closed at. No move() - a hardcoded
        # position can land the window off-screen on a smaller display.
        self.resize(1300, 800)
        self.second_window = None
        self.exportwindow = None

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


    def _build_menu(self, menubar, title, entries):
        menu = menubar.addMenu(title)
        for entry in entries:
            label, shortcut, handler = entry[0], entry[1], entry[2]
            key = entry[3] if len(entry) > 3 else None
            action = QtWidgets.QAction(label, self)
            action.triggered.connect(self._wrap_step(handler))
            if shortcut:
                action.setShortcut(shortcut)
            menu.addAction(action)
            if key:
                # Kept so refresh_workflow can enable and disable them in step
                # with the workflow panel.
                self.menu_actions[key] = action
        return menu

    def _wrap_step(self, handler):
        """Run a step, then re-evaluate what is possible next."""
        def run(*_):
            handler()
            self.refresh_workflow()
        return run

    def init_Ui(self):
        self.menu_actions = {}
        self.completed_steps = set()
        self.centralwidget = QtWidgets.QWidget(self)
        self.overallverticallayout = QtWidgets.QVBoxLayout(self.centralwidget)

        # self.menuBar(), not a QMenuBar dropped into a layout: a menu bar
        # parked in a layout is not the window's menu bar, sizes oddly, and
        # never reaches the macOS menu bar.
        menubar = self.menuBar()
        self.menubardata_Make_invoices = self.init_menubardata_make_invoices()
        if self.menubardata_Make_invoices:
            self._build_menu(menubar, "Rechnungen erstellen und verschicken",
                             self.menubardata_Make_invoices)
        self.menubardata_Infinity = self.init_menubardata_Infinity()
        if self.menubardata_Infinity:
            infinity_menu = self._build_menu(menubar, "Infinity Export", self.menubardata_Infinity)
            infinity_menu.addSeparator()
            close_action = QtWidgets.QAction("Schließen", self)
            close_action.setShortcut(QtGui.QKeySequence.Quit)
            # close(), not sys.exit(0): lets closeEvent save the geometry and
            # gives Qt a chance to shut down cleanly.
            close_action.triggered.connect(self.close)
            infinity_menu.addAction(close_action)

        self.overallverticallayout.addWidget(self.build_header())

        self.horizontalLayout = QtWidgets.QHBoxLayout()
        self.verticalLayout0 = QtWidgets.QVBoxLayout()  # left: consumer data
        self.verticalLayout1 = QtWidgets.QVBoxLayout()  # right: producer data and files
        self.table_0_0 = TableView()
        self.table_0_1 = TableView()
        self.table_1_0 = TableView()
        self.filepanel = FileLoadPanel(self.FILE_ROWS)

        # Built before init_loading_functionality, because its auto-load of the
        # .env templates immediately calls back into on_data_changed().
        self.workflow = WorkflowPanel(self.WORKFLOW_STEPS)
        step_handlers = {entry[3]: entry[2]
                         for entry in (self.menubardata_Make_invoices or []) + (self.menubardata_Infinity or [])
                         if len(entry) > 3}
        for key, handler in step_handlers.items():
            self.workflow.set_handler(key, self._wrap_step(handler))

        self.init_loading_functionality(self.filepanel)

        self.horizontalLayout.addLayout(self.verticalLayout1)
        self.horizontalLayout.addLayout(self.verticalLayout0)
        self.verticalLayout0.addWidget(self.section_label("Rechnungsdaten KonsumentInnen"))
        self.verticalLayout0.addWidget(self.table_0_0)
        self.verticalLayout0.addWidget(self.section_label("Energiedaten"))
        self.verticalLayout0.addWidget(self.table_0_1)
        self.verticalLayout0.setStretch(1, 7)
        self.verticalLayout0.setStretch(3, 7)

        self.verticalLayout1.addWidget(self.section_label("Rechnungsdaten ProduzentInnen"))
        self.verticalLayout1.addWidget(self.table_1_0)
        self.verticalLayout1.addWidget(self.section_label("Dateien laden"))
        self.verticalLayout1.addWidget(self.filepanel)
        self.verticalLayout1.addWidget(self.section_label("Ablauf"))
        self.verticalLayout1.addWidget(self.workflow)
        self.verticalLayout1.setStretch(1, 7)
        self.verticalLayout1.setStretch(3, 4)
        self.verticalLayout1.setStretch(5, 3)

        self.overallverticallayout.addLayout(self.horizontalLayout)
        self.setCentralWidget(self.centralwidget)
        self.update_status_header()
        self.refresh_workflow()
        self.restore_geometry()

    def section_label(self, text):
        label = QLabel(text)
        label.setObjectName("sectionLabel")
        return label

    def build_header(self):
        """Letterhead band: the logo, then what is currently loaded.

        Same mark and same orange as the invoices the app produces, so the
        window and its output look like they come from the same place.
        """
        band = QWidget()
        band.setObjectName("headerWidget")
        row = QHBoxLayout(band)
        row.setContentsMargins(12, 8, 12, 8)
        row.setSpacing(14)

        logo = QLabel()
        pixmap = QtGui.QPixmap(theme.logo_path())
        if not pixmap.isNull():
            # Stored at 2x for HiDPI; display at 40px tall.
            logo.setPixmap(pixmap.scaledToHeight(40, Qt.SmoothTransformation))
        else:
            # Missing asset must not cost us the header.
            logo.setText("Gemeinwohl Energie Innsbruck")
            logo.setStyleSheet(f"color: {theme.INK}; font-weight: 600;")
        row.addWidget(logo)

        self.status_header = QLabel()
        self.status_header.setObjectName("statusHeaderIdle")
        self.status_header.setTextInteractionFlags(Qt.TextSelectableByMouse)
        row.addWidget(self.status_header, 1)
        return band

    def restore_geometry(self):
        """Reopen where the user left the window.

        The hardcoded resize(1300, 800) / move(20, 20) could place the window
        partly off a 1366x768 laptop screen.
        """
        geometry = QSettings().value("window/geometry")
        if geometry is not None:
            self.restoreGeometry(geometry)

    def closeEvent(self, event):
        QSettings().setValue("window/geometry", self.saveGeometry())
        super().closeEvent(event)

    # (key, title, optional) - the quarterly sequence, in order.
    WORKFLOW_STEPS = [
        ("validate",        "Daten prüfen",              False),
        ("check_energy",    "Energiequalität prüfen",    True),
        ("create_invoices", "Rechnungen erstellen",      False),
        ("send_mail",       "Rechnungen verschicken",    False),
        ("sepa_export",     "SEPA-Export für Infinity",  False),
    ]

    def step_requirements(self):
        """What each step is waiting for, evaluated fresh on every refresh."""
        has_invoices = self.invoices.data is not None
        has_master = self.masterdata.data is not None
        has_energy = self.energydata.data is not None
        has_qov = self.energydata.metadata is not None
        has_invoice_template = self.invoices.template is not None
        has_mail_template = self.emails.template is not None
        return {
            "validate": [] if has_invoices else ["Rechnungsdaten"],
            "check_energy": [] if has_qov else ["Quartalsenergiedaten QoV"],
            # Energiedaten belongs here: produce_invoices_and_save dereferences
            # it unconditionally, so starting without it used to blow up inside
            # the worker rather than being refused up front.
            "create_invoices": [label for label, ok in [
                ("Rechnungsdaten", has_invoices),
                ("Stammdaten", has_master),
                ("Energiedaten", has_energy),
                ("Rechnungsvorlage", has_invoice_template)] if not ok],
            "send_mail": [label for label, ok in [
                ("Rechnungsdaten", has_invoices),
                ("Stammdaten", has_master),
                ("Emailvorlage", has_mail_template)] if not ok],
            "sepa_export": [] if has_invoices else ["Rechnungsdaten"],
        }

    def mark_step_done(self, key):
        self.completed_steps.add(key)
        self.refresh_workflow()

    def refresh_workflow(self):
        """Keep the step list and the menu entries agreeing about what is possible."""
        requirements = self.step_requirements()
        for key, _, _ in self.WORKFLOW_STEPS:
            missing = requirements.get(key, [])
            self.workflow.set_state(key, missing, key in self.completed_steps)
            action = self.menu_actions.get(key)
            if action is not None:
                action.setEnabled(not missing)
                action.setToolTip("wartet auf: " + ", ".join(missing) if missing else "")

    def init_data(self):
        #self.mandates = mandates
        self.invoices = invoices
        self.emails = emails
        self.masterdata = masterdata
        self.energydata = energydata
        self.new_member = newmember

    def report_invoice_problems(self, problems):
        """Show what a batch skipped, instead of losing it to a console nobody sees."""
        if not problems:
            QMessageBox.information(self, "Fertig", "Alle Rechnungen wurden erstellt.")
            return
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Warning)
        box.setWindowTitle("Mit Anmerkungen abgeschlossen")
        box.setText(f"{len(problems)} Punkt(e) brauchen deine Aufmerksamkeit.")
        box.setDetailedText("\n\n".join(problems))
        box.exec_()

    def report_send_result(self, sent, failed, missing):
        """Summarise a mail run: what went out, what did not, and why."""
        box = QMessageBox(self)
        box.setWindowTitle("Mailversand abgeschlossen")
        box.setIcon(QMessageBox.Warning if (failed or missing) else QMessageBox.Information)
        lines = [f"Verschickt: {len(sent)}"]
        if missing:
            lines.append(f"Ohne PDF übersprungen: {len(missing)}")
        if failed:
            lines.append(f"Fehlgeschlagen: {len(failed)}")
        box.setText("\n".join(lines))
        details = []
        if sent:
            details.append("Verschickt an:\n" + "\n".join(sent))
        if missing:
            details.append("Keine Rechnung gefunden:\n" + "\n".join(missing))
        if failed:
            details.append("Fehler:\n" + "\n".join(failed))
        if details:
            box.setDetailedText("\n\n".join(details))
        box.exec_()


    # (key, label) for each loadable file, in display order.
    FILE_ROWS = [
        ("invoices",         "Rechnungsdaten"),
        ("masterdata",       "EEG Faktura Stammdaten"),
        ("energy",           "Quartalsenergiedaten"),
        ("energy_qov",       "Quartalsenergiedaten QoV"),
        ("invoice_template", "Rechnungen Vorlage"),
        ("email_template",   "Emails Vorlage"),
    ]

    def init_loading_functionality(self, panel):

        def import_invoice_data():
            print("import invoice data")
            filepath = load_filepath(self, "Importiere Rechnungen von EEG Faktura", homedir=self.home_directory)
            if filepath is None:
                return
            invoicedata = self.invoices.load_data(filepath=filepath)
            if invoicedata is None:
                return
            invoicequart = invoicedata["detailed"]["Abrechnung"].iloc[0]
            self.thisinvoices_year = invoicequart.split("-")[-2]
            self.thisinvoice_quart = invoicequart.split("-")[-1]
            debit = invoicedata["list"][(invoicedata["list"]["Dokumenttyp"] == "Rechnung")]
            transfer = invoicedata["list"][(invoicedata["list"]["Dokumenttyp"] == "Gutschrift")|(invoicedata["list"]["Dokumenttyp"] == "Information")]

            self.reload_table_view("0_0", debit)
            self.reload_table_view("1_0", transfer)
            panel.set_path("invoices", filepath)
            self.invoicesdata_loaded = True
            self.on_data_changed()

        def load_template_invoice_from_fp(filepath):
            if not filepath:
                return
            if self.invoices.load_template(filepath=filepath) is not None:
                panel.set_path("invoice_template", filepath)
                self.on_data_changed()

        def select_template_invoice():
            filepath = load_filepath(self, "Wähle die Vorlage für die Rechnungen aus",
                                     filter="Word Dokument (*.docx)", homedir=self.home_directory)
            if filepath is not None:
                load_template_invoice_from_fp(filepath)

        def loadp_masterdata_from_fp(filepath):
            if not filepath:
                return
            loaded = self.masterdata.load_data(filepath=filepath)
            self.masterdata.load_metadata(filepath=filepath)
            self.emails.load_data(filepath=filepath)
            if loaded is not None:
                panel.set_path("masterdata", filepath)
                self.on_data_changed()

        def import_masterdata_data():
            filepath = load_filepath(self, "Wähle die Stammdaten von EEG Faktura aus", homedir=self.home_directory)
            if filepath is not None:
                loadp_masterdata_from_fp(filepath)

        def load_energydata_fp(filepath, load_qov=False):
            if not filepath:
                return
            if load_qov:
                loaded = self.energydata.load_metadata(filepath=filepath)
                key = "energy_qov"
            else:
                loaded = self.energydata.load_data(filepath=filepath)
                key = "energy"
            if loaded is not None:
                self.reload_table_view("0_1", loaded)
                panel.set_path(key, filepath)
                self.on_data_changed()

        def import_energy_data(load_qov=False):
            title = ("Wähle die QoV-Energiedaten für dieses Quartal aus" if load_qov
                     else "Wähle die Energiedaten für dieses Quartal aus")
            filepath = load_filepath(self, title, homedir=self.home_directory)
            if filepath is not None:
                load_energydata_fp(filepath, load_qov=load_qov)

        def load_emaildata_fp(filepath):
            if not filepath:
                return
            if self.emails.load_template(filepath=filepath) is not None:
                panel.set_path("email_template", filepath)
                self.on_data_changed()

        def import_email_template():
            # Was filtered on *.docx, but the email template is HTML.
            filepath = load_filepath(self, "Wähle die Emailvorlage aus",
                                     filter="HTML Datei (*.html *.htm)", homedir=self.home_directory)
            if filepath is not None:
                load_emaildata_fp(filepath)

        handlers = {
            "invoices":         import_invoice_data,
            "masterdata":       import_masterdata_data,
            "energy":           import_energy_data,
            "energy_qov":       partial(import_energy_data, load_qov=True),
            "invoice_template": select_template_invoice,
            "email_template":   import_email_template,
        }
        for key, handler in handlers.items():
            panel.set_handler(key, handler)

        # Auto-load the templates named in .env. Both loaders return early on an
        # empty path, so an install with no templates configured still starts.
        load_template_invoice_from_fp(self.config.get("template_export_invoice", ""))
        load_emaildata_fp(self.config.get("template_email", ""))

    def on_data_changed(self):
        """A file was loaded: re-evaluate the header and which steps are possible."""
        self.update_status_header()
        self.refresh_workflow()

    def update_status_header(self):
        """One line saying which quarter is loaded and how much of it.

        Running a quarter twice, or generating invoices against last quarter's
        energy data, was previously invisible until the PDFs came out wrong.
        """
        if not self.invoicesdata_loaded or self.invoices.data is None:
            self.status_header.setText("Keine Rechnungsdaten geladen - "
                                       "zuerst rechts eine Datei laden.")
            self.status_header.setObjectName("statusHeaderIdle")
            self.status_header.style().polish(self.status_header)
            return
        invoice_list = self.invoices.data["list"]
        n_debit = int((invoice_list["Dokumenttyp"] == "Rechnung").sum())
        n_credit = len(invoice_list) - n_debit
        energy = "Energiedaten geladen" if self.energydata.data is not None else "keine Energiedaten"
        self.status_header.setText(
            f"Abrechnung {self.thisinvoices_year} Q{self.thisinvoice_quart}  ·  "
            f"{n_debit} Rechnungen, {n_credit} Gutschriften  ·  {energy}")
        self.status_header.setObjectName("statusHeader")
        self.status_header.style().polish(self.status_header)
        self.setWindowTitle(f"Faktura Infinity Addon - {self.thisinvoices_year} "
                            f"Q{self.thisinvoice_quart}")

    def init_menubardata_Infinity(self):

        def export_csv():
            print("Export cvs")
            check,datamissing = check_whether_data_exists(invoices = self.invoices, invoicedatarequired=True)
            print(f"Check was {check}, datamissing {datamissing}")

            if check:
                if self.exportwindow is None:
                    #data check

                    self.exportwindow = Subwindow("Exportiere .csv für SEPA")
                    # Tall enough to show a useful number of rows; the scroll
                    # area below handles the rest. No move() - a fixed position
                    # can put the window off-screen.
                    self.exportwindow.resize(620, 640)
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

                    amount_labels = []
                    for index,(name,amount) in enumerate(zip(names,amounts)):
                        index += 1
                        checkbox = QCheckBox()
                        checkbox.setChecked(True)
                        col1 = QLabel(str(name))
                        col2 = QLabel(f"{amount:.2f}")
                        col2.setAlignment(Qt.AlignRight | Qt.AlignVCenter)

                        self.exportwindow.tablegrid.addWidget(checkbox,index,0)
                        self.exportwindow.tablegrid.addWidget(col1,index,1)
                        self.exportwindow.tablegrid.addWidget(col2,index,2)

                        self.exportwindow.list_data.append(checkbox)
                        amount_labels.append(amount)

                    # One signed "Gesamt" hid whether money was going out or
                    # coming in. Debits and credits are separate operations at
                    # the bank, so show them separately.
                    label_debit = QLabel()
                    label_credit = QLabel()
                    label_net = QLabel()
                    for row, (caption, widget) in enumerate([
                            ("Lastschriften (Einzug)", label_debit),
                            ("Überweisungen (Gutschrift)", label_credit),
                            ("Netto", label_net)]):
                        caption_label = QLabel(caption)
                        if caption == "Netto":
                            caption_label.setStyleSheet("font-weight: 600;")
                            widget.setStyleSheet("font-weight: 600;")
                        widget.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
                        self.exportwindow.totalsum.addWidget(caption_label, row, 1)
                        self.exportwindow.totalsum.addWidget(widget, row, 2)

                    def refresh_totals():
                        """Keep the totals honest as boxes are ticked and unticked."""
                        selected = [a for a, cb in zip(amount_labels, self.exportwindow.list_data)
                                    if cb.isChecked()]
                        debit_sum = -sum(a for a in selected if a < 0)   # stored negative
                        credit_sum = sum(a for a in selected if a > 0)
                        label_debit.setText(f"€ {debit_sum:.2f}")
                        label_credit.setText(f"€ {credit_sum:.2f}")
                        label_net.setText(f"€ {credit_sum - debit_sum:.2f}")

                    for checkbox in self.exportwindow.list_data:
                        checkbox.stateChanged.connect(lambda _: refresh_totals())
                    refresh_totals()

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
                                # utf-8-sig: plain UTF-8 has no BOM, so German
                                # banking imports read Müller/Straße as mojibake
                                # in the account name and payment reference.
                                df.to_csv(filepath, index=False, sep=";", encoding="utf-8-sig")
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
                        self.mark_step_done("sepa_export")
                        return selected_names


                    def set_all_checked(checked):
                        for checkbox in self.exportwindow.list_data:
                            checkbox.blockSignals(True)
                            checkbox.setChecked(checked)
                            checkbox.blockSignals(False)
                        refresh_totals()

                    select_all = QPushButton("Alle auswählen")
                    select_none = QPushButton("Keine")
                    select_all.clicked.connect(lambda: set_all_checked(True))
                    select_none.clicked.connect(lambda: set_all_checked(False))
                    selection_row = QHBoxLayout()
                    selection_row.addWidget(select_all)
                    selection_row.addWidget(select_none)
                    selection_row.addStretch(1)
                    selection_row.addWidget(QLabel(f"{len(names)} Positionen"))

                    self.exportwindow.ok_button = QPushButton("Exportieren")
                    self.exportwindow.ok_button.setObjectName("primaryButton")
                    self.exportwindow.ok_button.setDefault(True)
                    self.exportwindow.ok_button.pressed.connect(get_selected_names)

                    # The checkbox grid goes in a scroll area. Added straight to
                    # the layout, 120 members asked for a 3272px-tall window, so
                    # the totals and the OK button sat below the bottom of the
                    # screen with no way to reach them.
                    rows_container = QWidget()
                    rows_container.setLayout(self.exportwindow.tablegrid)
                    scroll = QtWidgets.QScrollArea()
                    scroll.setWidget(rows_container)
                    scroll.setWidgetResizable(True)
                    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

                    layout = self.exportwindow.overallverticallayout
                    layout.addLayout(header_layout)
                    layout.addWidget(scroll, 1)          # the only part that grows
                    layout.addLayout(selection_row)
                    layout.addLayout(self.exportwindow.totalsum)
                    layout.addWidget(self.exportwindow.ok_button)

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

        menubardata = [["Exportiere .csv Datei für Raiffeisen Infinity", "", export_csv, "sepa_export"]]
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

        def collect_findings():
            return validation.validate(
                invoices=self.invoices, masterdata=self.masterdata, energydata=self.energydata,
                resolve_name=resolve_name_in_energydata,
                members_with_invoices=members_with_invoices)

        def run_validation():
            findings = collect_findings()
            ValidationDialog(findings, parent=self).exec_()
            if not [f for f in findings if f.severity == validation.ERROR]:
                self.mark_step_done("validate")

        def confirm_despite_errors(title):
            """Re-run the checks before an irreversible step and stop on errors.

            Cheap - it is a handful of pandas passes - and it catches the two
            mistakes that are otherwise invisible until the bank or a member
            tells you: energy data from the wrong quarter, and debits with no
            usable IBAN or mandate.
            """
            errors = [f for f in collect_findings() if f.severity == validation.ERROR]
            if not errors:
                return True
            box = QMessageBox(self)
            box.setIcon(QMessageBox.Warning)
            box.setWindowTitle(title)
            box.setText(f"Die Datenprüfung meldet {len(errors)} Fehler.")
            box.setInformativeText("Trotzdem fortfahren?")
            box.setDetailedText("\n".join(f"{f.category}: {f.message}" for f in errors))
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            return box.exec_() == QMessageBox.Yes

        def check_energydata():
            print("I check the energydata")
            check,datamissing = check_whether_data_exists(energydata= self.energydata,energymetadatarequired= True)
            print(f"Check was {check}, datamissing {datamissing}")

            if check:
                qov_values = self.energydata.metadata.copy()
                qov_cols = self.energydata.metadata.columns.get_level_values(0) == "QoV"
                qov_values.columns = range(qov_values.shape[1])
                qov_values = qov_values.loc[:,qov_cols]
                qov_L3_values = (self.energydata.metadata.loc[:,qov_cols] == "L3").values
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
                    names = np.unique(self.energydata.metadata.columns[qov_values.columns[columns_this_L3]-1].get_level_values('Name'))
                    shownames =', '.join(names)
                    if names.shape[0] > 3:
                        shownames = "All"
                    Metering_points = np.unique(self.energydata.metadata.columns[qov_values.columns[columns_this_L3]-1].get_level_values('MeteringpointID'))
                    days = (self.energydata.metadata.index[start].date(),self.energydata.metadata.index[end].date())
                    timerange = f"{self.energydata.metadata.index[start]} - {self.energydata.metadata.index[end]}"
                    print(days,timerange,names,Metering_points)
                    line = [self.energydata.metadata.index[start].date(),self.energydata.metadata.index[end].date(),shownames,timerange,', '.join(names),', '.join(Metering_points)]
                    report_list.append(line)
                report_df = pd.DataFrame(report_list,columns = ["Start Datum", "End Datum", "Namen Übersicht", "Zeitraum Details","Namen Details", "ZP Details"])
                if report_df.shape[0] == 0:
                    message = QMessageBox()
                    text = "Überprüfung durchgeführt. \nAlle QoV Energiedaten sind mindestens L2"
                    message.setText(text)
                    message.exec_()
                else:
                    first_day = self.energydata.metadata.index[0].strftime("%Y_%m_%d")
                    last_day = self.energydata.metadata.index[-1].strftime("%Y_%m_%d")
                    savepath = load_filepath(self,
                                             "Wo soll ich den Überprüfungsreport hinspeichern?",
                                             fileex=False,
                                             defaultfilename=f"Energydata_QoV_Report_{first_day}-{last_day}.xlsx",
                                             homedir=self.home_directory)
                    if savepath is None:
                        # Cancelling used to call .lower() on None right here.
                        print("No path selected for the QoV report")
                        return
                    # Was ".xslx" - transposed letters, so a correctly named
                    # file became Report.xlsx.xlsx.
                    if not savepath.lower().endswith(".xlsx"):
                        savepath += ".xlsx"
                    self.safepath_this_energyreport = savepath
                    print(f"Save qov Report to: {savepath}")
                    try:
                        report_df.to_excel(savepath)
                    except Exception as e:
                        QMessageBox.critical(self, "Speichern fehlgeschlagen",
                                             f"Der Report konnte nicht gespeichert werden:\n{savepath}\n\n{e}")
                        return
                    if not open_in_default_app(savepath):
                        QMessageBox.information(
                            self, "Report gespeichert",
                            f"Der Überprüfungsreport wurde gespeichert:\n{savepath}\n\n"
                            f"Er konnte nicht automatisch geöffnet werden.")



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
                if not confirm_despite_errors("Rechnungen erstellen"):
                    return
                # first create a dict with all the info for the invoice, then render the template, then do it for all persons.
                self.safepath_this_invoices = load_filepath(self, "Wo sollen die Rechnungen gespeichert werden?", pathisdir=True,homedir= self.home_directory)
                if self.safepath_this_invoices is not None:
                    print(f"Save to {self.safepath_this_invoices}")
                    # for loading screeen i need multithreading
                    cancel_requested = threading.Event()

                    class Worker(QObject):
                        progress = pyqtSignal(str, int, int)
                        finished = pyqtSignal(list)   # problems encountered

                        def __init__(self, task_func):
                            super().__init__()
                            self.task_func = task_func
                            # Written before the signal is emitted and read after
                            # wait(), so the report does not depend on a queued
                            # slot having been delivered.
                            self.problems = []

                        def run(self):
                            try:
                                self.problems = self.task_func(self.progress.emit) or []
                            except Exception as e:
                                traceback.print_exc()
                                self.problems = [f"Abbruch durch einen Fehler: {e}"]
                            finally:
                                # Always emit. Any path that skipped this left the
                                # dialog open and the thread running forever.
                                self.finished.emit(self.problems)

                    class StatusDialog(QDialog):
                        def __init__(self):
                            super().__init__()
                            self.setWindowTitle("Rechnungen werden erstellt")
                            self.setMinimumWidth(420)
                            self.label = QLabel("Rechnungen werden vorbereitet...")
                            self.bar = QtWidgets.QProgressBar()
                            self.bar.setRange(0, 0)     # indeterminate until the first update
                            self.cancel_button = QPushButton("Abbrechen")
                            self.cancel_button.clicked.connect(self.request_cancel)
                            layout = QVBoxLayout()
                            layout.addWidget(self.label)
                            layout.addWidget(self.bar)
                            layout.addWidget(self.cancel_button)
                            self.setLayout(layout)

                        def request_cancel(self):
                            cancel_requested.set()
                            self.cancel_button.setEnabled(False)
                            self.label.setText("Abbruch nach der laufenden Rechnung...")

                        def update_progress(self, message, done, total):
                            self.label.setText(message)
                            if total:
                                self.bar.setRange(0, total)
                                self.bar.setValue(done)

                        def keyPressEvent(self, event):
                            # Esc would close the dialog and drop the last
                            # reference to a still-running thread. Treat it as
                            # a cancel request instead.
                            if event.key() == Qt.Key_Escape:
                                self.request_cancel()
                                return
                            super().keyPressEvent(event)

                        def closeEvent(self, event):
                            # The title-bar close button bypasses keyPressEvent.
                            # Ignoring it outright would look like a frozen app
                            # now that there is a Cancel button, so treat it the
                            # same way: ask to stop, and let `finished` close us.
                            self.request_cancel()
                            event.ignore()

                    def task_for_worker(callback):
                        return produce_invoices_and_save(
                            self.energydata.data, self.invoices.data["detailed"], self.masterdata,
                            self.invoices.template, self.safepath_this_invoices, callback,
                            should_cancel=cancel_requested.is_set)

                    dialog = StatusDialog()

                    thread = QThread()
                    worker = Worker(task_for_worker)
                    worker.moveToThread(thread)

                    worker.progress.connect(dialog.update_progress)
                    worker.finished.connect(thread.quit)
                    worker.finished.connect(lambda _: dialog.accept())
                    thread.started.connect(worker.run)

                    thread.start()
                    dialog.exec_()
                    thread.wait()

                    # worker.problems, not a list filled by a queued slot: the
                    # slot is only delivered while an event loop is running, so
                    # a dialog that closed early would have reported a clean run
                    # even when members were skipped.
                    self.report_invoice_problems(worker.problems)
                    self.mark_step_done("create_invoices")
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
                # Match on the (Vorname, Nachname) pair. Testing the two columns
                # independently also matched people who share a first name with
                # one recipient and a surname with another, i.e. members with no
                # invoice at all were queued to receive one.
                personswithinvoicesmasterdata = members_with_invoices(
                    self.masterdata.data, self.invoices.data["detailed"])
                if personswithinvoicesmasterdata.empty:
                    QMessageBox.information(self, "Keine Empfänger:innen",
                                            "Zu den geladenen Rechnungen wurde niemand in den "
                                            "Stammdaten gefunden.")
                    return

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
                if not confirm_despite_errors("Rechnungen verschicken"):
                    return
                logged_in = try_logging_in_f(self.config.get("my_mail", ""), self.config.get("my_mail_pw", ""), self.config.get("imap_server", ""))
                if logged_in:
                    mailadressselection = MailAdressSelection(personswithinvoicesmasterdata["E-Mail"], title="Wähle die Personen aus, denen du eine Mail schreiben willst")
                    # Early returns: these values used to be assigned only inside
                    # the accepted branch, so cancelling raised UnboundLocalError.
                    if not mailadressselection.exec_():
                        print("Dialog canceled")
                        return
                    selected_persons = mailadressselection.result
                    personswithinvoicesselected = personswithinvoicesmasterdata.loc[selected_persons,:]
                    if personswithinvoicesselected.empty:
                        QMessageBox.information(self, "Keine Auswahl", "Es wurde niemand ausgewählt.")
                        return

                    if not self.safepath_this_invoices:
                        self.safepath_this_invoices = load_filepath(self, "In welchem Ordner sind die ganzen Rechnungen gespeichert?", pathisdir=True,homedir= self.home_directory)
                    if not self.safepath_this_invoices:
                        print("No invoice folder selected - aborting")
                        return

                    invoicequart = self.invoices.data["detailed"]["Abrechnung"].iloc[0]
                    self.thisinvoices_year = invoicequart.split("-")[-2]
                    self.thisinvoice_quart = invoicequart.split("-")[-1]

                    # Resolve every attachment before sending anything: a missing
                    # PDF used to surface as FileNotFoundError partway through,
                    # after some members had already been mailed.
                    jobs, missing = [], []
                    preview_rows, missing_rows = [], []
                    for _, person_data in personswithinvoicesselected.iterrows():
                        display = f"{person_data['Name 1']} {person_data['Name 2']}"
                        receivername = f"{person_data['Name 1']}_{person_data['Name 2']}"
                        nameinvoicefile = f"Rechnung_{self.thisinvoices_year}_q{self.thisinvoice_quart}_{receivername}.pdf"
                        fpinvoicefile = os.path.join(self.safepath_this_invoices, nameinvoicefile)
                        if os.path.exists(fpinvoicefile):
                            jobs.append((person_data, fpinvoicefile))
                            preview_rows.append((display, person_data["E-Mail"], fpinvoicefile))
                        else:
                            missing.append(f"{person_data['E-Mail']}: {nameinvoicefile} nicht gefunden")
                            missing_rows.append((display, person_data["E-Mail"], nameinvoicefile))

                    jobs_by_address = {person_data["E-Mail"]: (person_data, path)
                                       for person_data, path in jobs}

                    def build_preview(address):
                        """Compose the real message and pull its subject, HTML and attachment.

                        Built by build_invoice_email, the same function the send
                        uses, so the preview cannot drift from what goes out.
                        """
                        person_data, path = jobs_by_address[address]
                        message = build_invoice_email(
                            self.config.get("my_mail", ""), self.config.get("EEG_name", ""),
                            address, person_data["Name 1"],
                            self.thisinvoice_quart, self.thisinvoices_year,
                            self.emails.template, path, self.masterdata)
                        html = ""
                        for part in message.walk():
                            if part.get_content_type() == "text/html":
                                html = part.get_content()
                        return message["Subject"], html, os.path.basename(path)

                    preview = SendPreviewDialog(preview_rows, missing_rows, build_preview, parent=self)
                    if not preview.exec_() or not preview.result:
                        print("Send cancelled in the preview dialog")
                        return

                    sent, failed = [], []
                    for person_data, fpinvoicefile in jobs:
                        print(f"Send Mail to: {person_data['E-Mail']}")
                        try:
                            send_mail_to_one_person(self.config.get("my_mail", ""),self.config.get("my_mail_pw", ""), self.config.get("imap_server", ""),self.config.get("EEG_name", ""),person_data["E-Mail"],person_data["Name 1"],
                                                    self.thisinvoice_quart, self.thisinvoices_year, self.emails.template, fpinvoicefile, self.masterdata)
                            sent.append(person_data["E-Mail"])
                        except Exception as e:
                            # One bad address must not abort a run that has
                            # already delivered to everybody before it.
                            traceback.print_exc()
                            failed.append(f"{person_data['E-Mail']}: {e}")

                    self.report_send_result(sent, failed, missing)
                    self.mark_step_done("send_mail")

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
        menubardata = [["Daten prüfen", "", run_validation, "validate"],
                       ["Überprüfe die Qualität der Energiedaten", "", check_energydata, "check_energy"],
                       ["Erstelle alle Rechnungen", "", create_invoices_and_save, "create_invoices"],
                       ["Verschicke die Rechnungen per Mail", "", send_invoices_mail, "send_mail"],
                       ["Einstellungen", "", change_Settings]]
        return menubardata


def install_exception_dialog():
    """Show unhandled errors instead of vanishing.

    The packaged build is --windowed, so it has no console: the previous hook
    printed a traceback nobody could see and called sys.exit(1), which looked
    to the user like the app simply disappeared.
    """
    original_hook = sys.excepthook

    def exception_hook(exctype, value, tb):
        if issubclass(exctype, KeyboardInterrupt):
            original_hook(exctype, value, tb)
            return
        details = "".join(traceback.format_exception(exctype, value, tb))
        print(details)
        try:
            box = QMessageBox()
            box.setIcon(QMessageBox.Critical)
            box.setWindowTitle("Unerwarteter Fehler")
            box.setText("Es ist ein unerwarteter Fehler aufgetreten.\n\n"
                        f"{exctype.__name__}: {value}")
            box.setInformativeText("Über 'Details anzeigen' bekommst du den vollen Fehlerbericht - "
                                   "bitte diesen beim Melden mitschicken.")
            box.setDetailedText(details)
            copy_button = box.addButton("Fehlerbericht kopieren", QMessageBox.ActionRole)
            box.addButton("Weiter", QMessageBox.AcceptRole)
            box.exec_()
            if box.clickedButton() is copy_button:
                QtWidgets.QApplication.clipboard().setText(details)
        except Exception:
            original_hook(exctype, value, tb)
        # Deliberately no sys.exit: one failed action should not discard the
        # data the user has already loaded.

    sys.excepthook = exception_hook


def main():
    app = QtWidgets.QApplication(sys.argv)
    app.setApplicationName("FakturaAddon")
    app.setOrganizationName("Energiegemeinschaft")
    app.setWindowIcon(QtGui.QIcon(theme.logo_path()))
    app.setStyleSheet(theme.STYLESHEET)
    install_exception_dialog()
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())


if __name__ == '__main__':
    main()