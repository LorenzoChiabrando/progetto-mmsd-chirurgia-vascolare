"""Modello Qt della vista per specializzando: righe = persone, colonne = Totale + giorni."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from src.calendar_presentation import ROLE_HEADER_COLORS, row_display_label
from src.roster_month import RESIDENT_ROLE_CODES, ResidentRow, RosterMonth
from src.views.models.activity_table_model import (
    FONT_FAMILY,
    REST_BACKGROUND,
    TEXT_COLOR,
    TODAY_CELL_BACKGROUND,
)

_CODE_ROLES = {code: role for role, code in RESIDENT_ROLE_CODES.items()}
_TOTAL_BACKGROUND = QColor("#f1f5f9")
_Role = Qt.ItemDataRole


class ResidentTableModel(QAbstractTableModel):
    """Sola consultazione: in ogni cella la sigla del ruolo, colorata come il ruolo.

    La colonna 0 è il totale dei turni (resta visibile anche scorrendo i giorni); la
    colonna ``n`` è il giorno ``n`` del mese.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._roster: RosterMonth | None = None
        self._rows: tuple[ResidentRow, ...] = ()
        self._today: date | None = None

    def set_rows(self, roster: RosterMonth, rows: Sequence[ResidentRow]) -> None:
        self.beginResetModel()
        self._roster = roster
        self._rows = tuple(rows)
        self.endResetModel()

    def set_today(self, today: date | None) -> None:
        self._today = today
        if self.rowCount() and self.columnCount():
            last = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(self.index(0, 0), last)

    def total_column(self) -> int:
        return 0

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(self._rows)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid() or self._roster is None:
            return 0
        return len(self._roster.dates) + 1

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        return Qt.ItemFlag.ItemIsEnabled if index.isValid() else Qt.ItemFlag.NoItemFlags

    def headerData(self, section: int, orientation: Qt.Orientation, role=_Role.DisplayRole):
        if orientation == Qt.Orientation.Horizontal:
            if role != _Role.DisplayRole:
                return None
            return "Totale" if section == self.total_column() else str(section)
        row = self._rows[section]
        if role == _Role.DisplayRole:
            return row.label
        if role == _Role.ToolTipRole:
            return row.full_name
        return None

    def data(self, index: QModelIndex, role=_Role.DisplayRole):
        if not index.isValid() or self._roster is None:
            return None
        row = self._rows[index.row()]
        if index.column() == self.total_column():
            return self._total_data(row, role)
        day = self._roster.dates[index.column() - 1]
        code = row.codes[index.column() - 1]
        if role == _Role.DisplayRole:
            return code
        if role == _Role.ToolTipRole:
            if not code:
                return None
            return " + ".join(row_display_label(_CODE_ROLES[part]) for part in code.split("+"))
        if role == _Role.BackgroundRole:
            if not RosterMonth.is_workday(day):
                return REST_BACKGROUND
            if code:
                return QColor(ROLE_HEADER_COLORS[_CODE_ROLES[code.split("+")[0]]])
            return TODAY_CELL_BACKGROUND if day == self._today else None
        if role == _Role.ForegroundRole:
            return TEXT_COLOR
        if role == _Role.FontRole:
            return QFont(FONT_FAMILY, 9, QFont.Weight.Bold)
        if role == _Role.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        return None

    @staticmethod
    def _total_data(row: ResidentRow, role):
        if role == _Role.DisplayRole:
            return str(row.total)
        if role == _Role.BackgroundRole:
            return _TOTAL_BACKGROUND
        if role == _Role.FontRole:
            return QFont(FONT_FAMILY, 10, QFont.Weight.Bold)
        if role == _Role.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        return None
