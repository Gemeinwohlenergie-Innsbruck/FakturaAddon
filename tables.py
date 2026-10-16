"""The data tables in the main window: filter, sort, resize, every row.

They used to be QTableWidgets filled cell by cell and cut off at 200 rows,
with no way to sort or search - not much use for checking an import. A
model over the DataFrame renders only what is on screen, so all rows can
be shown; a proxy on top does the sorting and filtering.
"""

import datetime as dt
import math
from decimal import Decimal

import pandas as pd
from PyQt5.QtCore import QAbstractTableModel, QModelIndex, QSortFilterProxyModel, Qt
from PyQt5.QtWidgets import (QAbstractItemView, QHBoxLayout, QHeaderView, QLabel, QLineEdit,
                             QTableView, QTableWidgetItem, QVBoxLayout, QWidget)

from i18n import tr


def _blank(value):
    try:
        return value is None or (not isinstance(value, str) and pd.isna(value))
    except (TypeError, ValueError):
        return False


def _text(value):
    if _blank(value):
        return ""
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        return value.strftime("%d.%m.%Y %H:%M") if (value.hour or value.minute) else value.strftime("%d.%m.%Y")
    if isinstance(value, float):
        return f"{value:.6f}".rstrip("0").rstrip(".") if not value.is_integer() else str(int(value))
    return str(value)


def _sort_key(value):
    """Numbers sort as numbers, dates as dates, blanks last."""
    if _blank(value):
        return (2, 0)
    if isinstance(value, (int, float)) and not (isinstance(value, float) and math.isnan(value)):
        return (0, float(value))
    if isinstance(value, (pd.Timestamp, dt.datetime)):
        return (0, value.timestamp())
    return (1, str(value).casefold())


class DataFrameModel(QAbstractTableModel):
    """Read-only view of a DataFrame. A datetime index becomes the first column."""

    SORT_ROLE = Qt.UserRole

    def __init__(self, frame=None, parent=None):
        super().__init__(parent)
        self.set_frame(frame if frame is not None else pd.DataFrame())

    def set_frame(self, frame):
        self.beginResetModel()
        if isinstance(frame.index, pd.DatetimeIndex):
            frame = frame.copy()
            frame.insert(0, tr("Zeit"), frame.index)
        self.headers = [" ".join(str(p) for p in c if not str(p).startswith("Unnamed"))
                        if isinstance(c, tuple) else str(c) for c in frame.columns]
        self.values = frame.to_numpy(dtype=object)
        self.endResetModel()

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.values)

    def columnCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self.headers)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid():
            return None
        value = self.values[index.row(), index.column()]
        if role in (Qt.DisplayRole, Qt.ToolTipRole):
            return _text(value)
        if role == self.SORT_ROLE:
            return _sort_key(value)
        if role == Qt.TextAlignmentRole and isinstance(value, (int, float)) and not _blank(value):
            return Qt.AlignRight | Qt.AlignVCenter
        return None

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role in (Qt.DisplayRole, Qt.ToolTipRole) and orientation == Qt.Horizontal:
            return self.headers[section]
        if role == Qt.DisplayRole and orientation == Qt.Vertical:
            return str(section + 1)
        return None


class _Proxy(QSortFilterProxyModel):
    def lessThan(self, left, right):
        return (self.sourceModel().data(left, DataFrameModel.SORT_ROLE)
                < self.sourceModel().data(right, DataFrameModel.SORT_ROLE))


class DataFrameTable(QWidget):
    """A filter box over a sortable, resizable table of a DataFrame."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.model = DataFrameModel()
        self.proxy = _Proxy(self)
        self.proxy.setSourceModel(self.model)
        self.proxy.setFilterKeyColumn(-1)                 # search every column
        self.proxy.setFilterCaseSensitivity(Qt.CaseInsensitive)

        self.filter = QLineEdit()
        self.filter.setPlaceholderText(tr("Filtern… (sucht in allen Spalten)"))
        self.filter.setClearButtonEnabled(True)
        self.filter.textChanged.connect(self._apply_filter)
        self.count = QLabel()

        self.view = QTableView()
        self.view.setModel(self.proxy)
        self.view.setSortingEnabled(True)
        self.view.sortByColumn(-1, Qt.AscendingOrder)     # keep the file's order until clicked
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setWordWrap(False)
        header = self.view.horizontalHeader()
        header.setSectionResizeMode(QHeaderView.Interactive)
        header.setSectionsMovable(True)
        header.setStretchLastSection(True)
        self.view.verticalHeader().setDefaultSectionSize(22)

        bar = QHBoxLayout()
        bar.setContentsMargins(0, 0, 0, 0)
        bar.addWidget(self.filter, 1)
        bar.addWidget(self.count)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addLayout(bar)
        layout.addWidget(self.view, 1)
        self._update_count()

    def set_new_data(self, data, **_):
        self.model.set_frame(data if data is not None else pd.DataFrame())
        self.view.sortByColumn(-1, Qt.AscendingOrder)
        self._size_columns()
        self._update_count()

    def _size_columns(self):
        # Sized from the first rows only: measuring 8,736 x 98 cells is slow.
        header = self.view.horizontalHeader()
        metrics = self.view.fontMetrics()
        sample = self.model.values[:50]
        for col, title in enumerate(self.model.headers):
            widths = [metrics.horizontalAdvance(title)]
            if len(sample):
                widths += [metrics.horizontalAdvance(_text(v)) for v in sample[:, col]]
            header.resizeSection(col, min(max(max(widths) + 18, 50), 320))

    def _apply_filter(self, text):
        self.proxy.setFilterFixedString(text)
        self._update_count()

    def _update_count(self):
        shown, total = self.proxy.rowCount(), self.model.rowCount()
        self.count.setText(tr("{shown} von {total} Zeilen", shown=shown, total=total)
                           if shown != total else tr("{total} Zeilen", total=total))


class SortableItem(QTableWidgetItem):
    """Sorts by a key set with set_key: numbers as numbers, blanks last."""

    KEY_ROLE = Qt.UserRole + 1

    def set_key(self, value):
        if value is None or (isinstance(value, float) and pd.isna(value)):
            key = (2, 0.0, "")
        elif isinstance(value, (int, float, Decimal)):
            key = (0, float(value), "")
        else:
            key = (1, 0.0, str(value).casefold())
        self.setData(self.KEY_ROLE, key)

    def __lt__(self, other):
        mine, theirs = self.data(self.KEY_ROLE), other.data(self.KEY_ROLE)
        if mine is None or theirs is None:
            return super().__lt__(other)
        return tuple(mine) < tuple(theirs)
