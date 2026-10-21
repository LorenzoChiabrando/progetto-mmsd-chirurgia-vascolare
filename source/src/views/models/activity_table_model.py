"""Modello Qt della vista mensile per attività: righe = ruoli, colonne = giorni."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import date

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from src.calendar_presentation import (
    GUARD_TEXT_COLORS,
    ROLE_CELL_COLORS,
    person_initials,
    resolve_resident_name,
    row_display_label,
)
from src.roster_month import GUARD_ROLE, ROLE_KEYS, RosterMonth

DAY_ROW = "Giorno"
ROW_KEYS: tuple[str, ...] = (DAY_ROW, *ROLE_KEYS)

FONT_FAMILY = "Segoe UI"
REST_BACKGROUND = QColor("#e2e8f0")
REST_TEXT = QColor("#94a3b8")
TODAY_CELL_BACKGROUND = QColor("#fef3c7")
TODAY_DAY_BACKGROUND = QColor("#f59e0b")
TEXT_COLOR = QColor("#1e293b")
DAY_TEXT = QColor("#475569")
_WEEKDAY_NAMES = ("LUN", "MAR", "MER", "GIO", "VEN", "SAB", "DOM")
_Role = Qt.ItemDataRole


class ActivityTableModel(QAbstractTableModel):
    """Espone un ``RosterMonth`` alla vista per attività, con la resa grafica dello scadenzario.

    In Dettaglio le celle mostrano ``Cognome N.``; nell'Intero mese (``set_compact``) le
    iniziali e la sola lettera del giorno. Il modello è di sola lettura: le assegnazioni
    passano dal controller.
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._roster: RosterMonth | None = None
        self._residents: tuple[Mapping[str, object], ...] = ()
        self._compact = False
        self._today: date | None = None

    def set_roster(
        self, roster: RosterMonth, residents: Iterable[Mapping[str, object]] = ()
    ) -> None:
        self.beginResetModel()
        self._roster = roster
        self._residents = tuple(residents)
        self.endResetModel()

    def set_compact(self, compact: bool) -> None:
        if compact != self._compact:
            self._compact = compact
            self._refresh()

    def set_today(self, today: date | None) -> None:
        self._today = today
        self._refresh()

    def _refresh(self) -> None:
        if self.rowCount() and self.columnCount():
            last = self.index(self.rowCount() - 1, self.columnCount() - 1)
            self.dataChanged.emit(self.index(0, 0), last)
        self.headerDataChanged.emit(Qt.Orientation.Vertical, 0, len(ROW_KEYS) - 1)

    def role_at(self, row: int) -> str:
        return ROW_KEYS[row]

    def date_at(self, column: int) -> date:
        return self._roster.dates[column]

    def value_at(self, row: int, column: int) -> str:
        """Valore salvato nella cella (``Cognome N.`` o codice guardia); vuoto per i festivi."""

        if self._roster is None or row == 0:
            return ""
        return self._roster.value(self.date_at(column), ROW_KEYS[row])

    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        return 0 if parent.isValid() else len(ROW_KEYS)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: B008
        if parent.isValid() or self._roster is None:
            return 0
        return len(self._roster.dates)

    def flags(self, index: QModelIndex) -> Qt.ItemFlag:
        if not index.isValid():
            return Qt.ItemFlag.NoItemFlags
        return Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable

    def headerData(self, section: int, orientation: Qt.Orientation, role=_Role.DisplayRole):
        if role != _Role.DisplayRole:
            return None
        if orientation == Qt.Orientation.Horizontal:
            return str(section + 1)
        return row_display_label(ROW_KEYS[section], compact=self._compact)

    def data(self, index: QModelIndex, role=_Role.DisplayRole):
        if not index.isValid() or self._roster is None:
            return None
        day = self.date_at(index.column())
        if index.row() == 0:
            return self._day_data(day, role)
        return self._cell_data(ROW_KEYS[index.row()], day, role)

    def _day_data(self, day: date, role):
        rest = not RosterMonth.is_workday(day)
        today = day == self._today and not rest
        if role == _Role.DisplayRole:
            name = _WEEKDAY_NAMES[day.weekday()]
            return name[:1] if self._compact else name
        if role == _Role.BackgroundRole:
            return TODAY_DAY_BACKGROUND if today else REST_BACKGROUND if rest else None
        if role == _Role.ForegroundRole:
            return QColor("#ffffff") if today else REST_TEXT if rest else DAY_TEXT
        if role == _Role.FontRole:
            return QFont(FONT_FAMILY, 8 if self._compact else 11, QFont.Weight.Bold)
        if role == _Role.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        return None

    def _cell_data(self, role_key: str, day: date, role):
        rest = not RosterMonth.is_workday(day)
        value = "-" if rest else self._roster.value(day, role_key)
        guard = role_key == GUARD_ROLE
        if role == _Role.DisplayRole:
            if self._compact and value and not guard and not rest:
                return person_initials(value)
            return value
        if role == _Role.ToolTipRole:
            if rest or not value:
                return None
            return value if guard else resolve_resident_name(value, self._residents)
        if role == _Role.BackgroundRole:
            if rest:
                return REST_BACKGROUND
            if day == self._today:
                return TODAY_CELL_BACKGROUND
            return QColor(ROLE_CELL_COLORS.get(role_key, "#ffffff"))
        if role == _Role.ForegroundRole:
            if rest:
                return REST_TEXT
            return QColor(GUARD_TEXT_COLORS.get(value, "#1e293b")) if guard else TEXT_COLOR
        if role == _Role.FontRole:
            if rest:
                return QFont(FONT_FAMILY, 13, QFont.Weight.Normal)
            if guard:
                return QFont(FONT_FAMILY, 7 if self._compact else 14, QFont.Weight.Bold)
            return QFont(FONT_FAMILY, 7 if self._compact else 13, QFont.Weight.DemiBold)
        if role == _Role.TextAlignmentRole:
            return Qt.AlignmentFlag.AlignCenter
        return None
