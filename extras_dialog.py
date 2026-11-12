"""The window for extra positions: meter readings that EEG Faktura never sees.

The logic (amounts, store, applying to the invoice data) is in extras.py;
this is only the form around it.
"""

from decimal import Decimal

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (QAbstractItemView, QCheckBox, QComboBox, QDialog, QDialogButtonBox,
                             QFormLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QMessageBox, QPushButton, QTableWidget, QTableWidgetItem, QVBoxLayout)

import extras
import ledger
import theme
import validation as v
from i18n import tr


def _tariff_text(tariff):
    unit = "ct/kWh" if tariff["unit"] == "Ct" else "€/kWh"
    vat = f"{extras.format_number(tariff['vat_rate'], 0)} % USt" if tariff["vat_applies"] else tr("ohne USt")
    # Two lines, not a word-wrapped one: a wrapped QLabel in a QFormLayout
    # gets the height of one line on macOS and overlaps the next row.
    return f"{tariff['tariff']}\n{extras.format_number(tariff['price'])} {unit} · {vat}"


class ReadingDialog(QDialog):
    """One reading: member, last and current meter reading, reason."""

    def __init__(self, store, creditor, period, tariffs, extra=None, every_quarter=True, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Zusatzposition"))
        self.store, self.creditor, self.period, self.tariffs = store, creditor, period, tariffs
        self.result_extra, self.every_quarter = None, every_quarter
        self.setMinimumWidth(620)

        layout = QVBoxLayout(self)
        form = QFormLayout()
        # The macOS style keeps fields at their size hint, which cut the
        # invoice text off after a few words.
        form.setFieldGrowthPolicy(QFormLayout.AllNonFixedFieldsGrow)
        form.setLabelAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.member = QComboBox()
        for key, tariff in sorted(tariffs.items(), key=lambda item: item[1]["name"].casefold()):
            self.member.addItem(f"{tariff['name']} ({tr('Nr.')} {tariff['member']})", key)
        if extra is not None:
            self.member.setCurrentIndex(max(0, self.member.findData(extra.key)))
            self.member.setEnabled(False)
        form.addRow(tr("Mitglied"), self.member)
        self.tariff_label = QLabel()
        form.addRow(tr("Tarif"), self.tariff_label)
        self.description = QLineEdit()
        form.addRow(tr("Text auf der Rechnung"), self.description)
        self.previous = QLineEdit()
        self.previous.setPlaceholderText(tr("z. B. {example}", example="12.345,6"))
        form.addRow(tr("Zählerstand alt (kWh)"), self.previous)
        self.current = QLineEdit()
        self.current.setPlaceholderText(tr("z. B. {example}", example="12.789,0"))
        form.addRow(tr("Zählerstand neu (kWh)"), self.current)
        self.reason = QLineEdit()
        self.reason.setPlaceholderText(tr("z. B. Ablesung vom 30.09.2026 durch …"))
        form.addRow(tr("Grund / Beleg"), self.reason)
        self.repeat = QCheckBox(tr("Jedes Quartal daran erinnern"))
        self.repeat.setChecked(every_quarter)
        form.addRow("", self.repeat)
        layout.addLayout(form)
        explain = QLabel(tr("Der Zähler zählt fortlaufend. Abgerechnet wird der Verbrauch seit der "
                            "letzten Ablesung: Zählerstand neu − Zählerstand alt. Der alte Stand wird "
                            "ab dem zweiten Quartal automatisch eingetragen."))
        explain.setWordWrap(True)
        layout.addWidget(explain)

        self.preview = QLabel()
        self.preview.setWordWrap(True)
        self.preview.setTextFormat(Qt.RichText)
        self.preview.setStyleSheet("padding: 8px; border-radius: 4px;")
        layout.addWidget(self.preview)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel)
        self.buttons.accepted.connect(self.accept_reading)
        self.buttons.rejected.connect(self.reject)
        layout.addWidget(self.buttons)

        if extra is not None:
            self.description.setText(extra.description)
            self.previous.setText(extras.format_number(extra.previous))
            self.current.setText(extras.format_number(extra.current))
            self.reason.setText(extra.reason)
        self.member.currentIndexChanged.connect(self.member_changed)
        for field in (self.description, self.previous, self.current, self.reason):
            field.textChanged.connect(self.update_preview)
        if extra is None:
            self.member_changed()
        self.update_preview()

    def key(self):
        return self.member.currentData()

    def member_changed(self):
        key = self.key()
        if key is None:
            return
        description, every_quarter = extras.remembered(self.store, self.creditor, key)
        self.description.setText(description)
        self.repeat.setChecked(every_quarter)
        last = extras.previous_reading(self.store, self.creditor, key, self.period)
        self.previous.setText("" if last is None else extras.format_number(last))
        self.current.clear()
        self.update_preview()

    def readings(self):
        """(previous, current, problem) - the two readings, before anything else is checked."""
        previous, current = extras.parse_reading(self.previous.text()), extras.parse_reading(self.current.text())
        if previous is None or current is None:
            return previous, current, tr("Beide Zählerstände eingeben.")
        if current <= previous:
            return previous, current, tr("Der neue Zählerstand muss größer sein als der alte.")
        return previous, current, None

    def read(self):
        """(extra, problem): problem is a text when the form is not complete."""
        key = self.key()
        if key is None:
            return None, tr("Kein Mitglied mit Verbrauchsposition in dieser Abrechnung.")
        previous, current, problem = self.readings()
        if problem:
            return None, problem
        if not self.description.text().strip():
            return None, tr("Text für die Rechnung eingeben.")
        if not self.reason.text().strip():
            return None, tr("Grund bzw. Beleg der Ablesung eingeben - er steht im Prüfprotokoll.")
        tariff = self.tariffs[key]
        return extras.Extra(member=tariff["member"], name=tariff["name"],
                            description=self.description.text().strip(),
                            previous=previous, current=current, reason=self.reason.text().strip(),
                            entered_by=ledger.current_user()), None

    def update_preview(self):
        key = self.key()
        if key is not None:
            self.tariff_label.setText(_tariff_text(self.tariffs[key]))
        extra, problem = self.read()
        self.buttons.button(QDialogButtonBox.Ok).setEnabled(extra is not None)
        previous, current, reading_problem = self.readings()
        if key is None or reading_problem:
            self.preview.setText(f"<span style='color:{theme.WARNING}'>{problem}</span>")
            return
        # The amount as soon as both readings make sense, whatever else is
        # still missing - it is what the operator is checking while typing.
        kwh = extras.kwh_between(previous, current)
        net, vat, gross = extras.amounts(kwh, self.tariffs[key])
        missing = f"<br><span style='color:{theme.WARNING}'>{problem}</span>" if problem else ""
        self.preview.setText(tr(
            "<b>{kwh} kWh</b> ({current} − {previous}) · netto {net} + USt {vat} = "
            "<b>{gross} brutto</b> zusätzlich auf {document}, wird mit der Rechnung eingezogen.",
            kwh=extras.format_number(kwh), current=extras.format_number(current),
            previous=extras.format_number(previous), net=v.format_euro(net),
            vat=v.format_euro(vat), gross=v.format_euro(gross),
            document=self.tariffs[key]["document"]) + missing)

    def accept_reading(self):
        extra, problem = self.read()
        if extra is None:
            return
        if extra.kwh > 10000:
            answer = QMessageBox.question(
                self, tr("Zusatzposition"),
                tr("{kwh} kWh in einem Quartal ist ungewöhnlich viel. Zählerstände richtig?",
                   kwh=extras.format_number(extra.kwh)))
            if answer != QMessageBox.Yes:
                return
        self.result_extra, self.every_quarter = extra, self.repeat.isChecked()
        self.accept()


class ExtrasDialog(QDialog):
    """This period's extra positions, with add, edit and remove."""

    COLUMNS = ["Mitglied", "Text", "Zählerstand alt", "Zählerstand neu", "kWh", "Brutto", "Grund"]

    def __init__(self, store, creditor, period, data, parent=None):
        super().__init__(parent)
        self.setWindowTitle(tr("Zusatzpositionen {period}", period=period))
        self.resize(980, 460)
        self.store, self.creditor, self.period = store, creditor, period
        self.tariffs = extras.candidates(data)
        self.changed = False

        layout = QVBoxLayout(self)
        intro = QLabel(tr(
            "Für Verbrauch, der nicht in EEG Faktura ankommt (z. B. gemessen vor dem Wechselrichter). "
            "Die Differenz der Zählerstände wird mit dem Verbrauchstarif des Mitglieds berechnet und "
            "auf seiner Rechnung ergänzt - in PDF, Prüfung und SEPA-Lastschrift. Die Daten aus "
            "EEG Faktura bleiben unverändert; dort fehlt dieser Betrag."))
        intro.setWordWrap(True)
        layout.addWidget(intro)
        self.reminder = QLabel()
        self.reminder.setWordWrap(True)
        self.reminder.setStyleSheet(f"color: {theme.WARNING}; font-weight: 600;")
        layout.addWidget(self.reminder)

        self.grid = QTableWidget(0, len(self.COLUMNS))
        self.grid.setHorizontalHeaderLabels([tr(c) for c in self.COLUMNS])
        self.grid.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.grid.setSelectionMode(QAbstractItemView.SingleSelection)
        self.grid.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.grid.verticalHeader().setVisible(False)
        self.grid.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        self.grid.horizontalHeader().setStretchLastSection(True)
        self.grid.doubleClicked.connect(self.edit)
        layout.addWidget(self.grid, 1)

        row = QHBoxLayout()
        self.add_button = QPushButton(tr("Hinzufügen…"))
        self.add_button.clicked.connect(self.add)
        self.edit_button = QPushButton(tr("Bearbeiten…"))
        self.edit_button.clicked.connect(self.edit)
        self.remove_button = QPushButton(tr("Entfernen"))
        self.remove_button.clicked.connect(self.remove)
        for button in (self.add_button, self.edit_button, self.remove_button):
            row.addWidget(button)
        row.addStretch(1)
        close = QDialogButtonBox(QDialogButtonBox.Close)
        close.rejected.connect(self.accept)
        row.addWidget(close)
        layout.addLayout(row)
        self.refresh()

    def entries(self):
        return extras.entries_for(self.store, self.creditor, self.period)

    def refresh(self):
        entries = self.entries()
        self.grid.setRowCount(len(entries))
        self.keys = []
        for r, extra in enumerate(entries):
            tariff = self.tariffs.get(extra.key)
            gross = v.format_euro(extras.amounts(extra.kwh, tariff)[2]) if tariff else tr("keine Rechnung")
            values = [extra.name, extra.description, extras.format_number(extra.previous),
                      extras.format_number(extra.current), extras.format_number(extra.kwh), gross,
                      extra.reason]
            for c, value in enumerate(values):
                item = QTableWidgetItem(value)
                if 2 <= c <= 5:
                    item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
                self.grid.setItem(r, c, item)
            self.keys.append(extra.key)
        self.grid.resizeColumnsToContents()
        missing = extras.missing_readings(self.store, self.creditor, self.period)
        self.reminder.setText(tr("Ablesung fehlt noch für: {names}",
                                 names=", ".join(name for _, name in missing)) if missing else "")
        self.reminder.setVisible(bool(missing))
        self.add_button.setEnabled(bool(self.tariffs))
        has_rows = bool(entries)
        self.edit_button.setEnabled(has_rows)
        self.remove_button.setEnabled(has_rows)
        if has_rows and not self.grid.selectedItems():
            self.grid.selectRow(0)

    def selected(self):
        rows = self.grid.selectionModel().selectedRows()
        if not rows:
            return None
        key = self.keys[rows[0].row()]
        return next((e for e in self.entries() if e.key == key), None)

    def save(self):
        try:
            extras.save_store(self.store)
        except OSError as e:
            QMessageBox.critical(self, tr("Speichern fehlgeschlagen"),
                                 tr("Die Zählerstände konnten nicht gespeichert werden:\n{error}", error=e))
        self.changed = True
        self.refresh()

    def add(self):
        dialog = ReadingDialog(self.store, self.creditor, self.period, self.tariffs, parent=self)
        missing = [key for key, _ in extras.missing_readings(self.store, self.creditor, self.period)
                   if key in self.tariffs]
        if missing:
            dialog.member.setCurrentIndex(max(0, dialog.member.findData(missing[0])))
        if dialog.exec_() == QDialog.Accepted and dialog.result_extra is not None:
            existing = {e.key for e in self.entries()}
            if dialog.result_extra.key in existing and QMessageBox.question(
                    self, tr("Zusatzposition"),
                    tr("Für {name} gibt es in dieser Abrechnung schon eine Ablesung. Ersetzen?",
                       name=dialog.result_extra.name)) != QMessageBox.Yes:
                return
            extras.set_entry(self.store, self.creditor, self.period, dialog.result_extra,
                             dialog.every_quarter)
            self.save()

    def edit(self, *_):
        extra = self.selected()
        if extra is None:
            return
        if extra.key not in self.tariffs:
            QMessageBox.information(self, tr("Zusatzposition"),
                                    tr("{name} hat in dieser Abrechnung keine Rechnung mit "
                                       "Verbrauchsposition.", name=extra.name))
            return
        _, every_quarter = extras.remembered(self.store, self.creditor, extra.key)
        dialog = ReadingDialog(self.store, self.creditor, self.period, self.tariffs, extra=extra,
                               every_quarter=every_quarter, parent=self)
        if dialog.exec_() == QDialog.Accepted and dialog.result_extra is not None:
            extras.set_entry(self.store, self.creditor, self.period, dialog.result_extra,
                             dialog.every_quarter)
            self.save()

    def remove(self):
        extra = self.selected()
        if extra is None:
            return
        if QMessageBox.question(self, tr("Zusatzposition"),
                                tr("Zusatzposition für {name} aus dieser Abrechnung entfernen?",
                                   name=extra.name)) != QMessageBox.Yes:
            return
        extras.remove_entry(self.store, self.creditor, self.period, extra.key)
        self.save()
