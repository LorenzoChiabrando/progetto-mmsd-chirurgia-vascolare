"""Dialog modali per assegnare turni e tipo di guardia nello scadenzario."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.roster_assignment import GUARD_TYPES, ResidentOption
from src.views.components.modal_dialog import ModalDialog

_RESIDENT_ROW_HEIGHT = 62


class _DialogAssegnazione(ModalDialog):
    """Base dei dialog dello scadenzario: contesto nel sottotitolo e pulsante Rimuovi."""

    def __init__(self, title: str, context: str, current: str, parent: QWidget | None) -> None:
        super().__init__(
            title,
            context,
            section="scadenzario",
            extra_styles=("dialog_assegnazione.qss",),
            parent=parent,
        )
        self._value = current

        self.btn_rimuovi = self.make_button("Rimuovi assegnazione", "danger")
        self.btn_rimuovi.setVisible(bool(current))
        self.btn_rimuovi.clicked.connect(lambda: self._confirm(""))
        self.btn_annulla = self.make_button("Annulla", "secondary")
        self.btn_annulla.clicked.connect(self.reject)

    def _add_footer(self, primary: QPushButton | None = None) -> None:
        actions = (self.btn_annulla, primary) if primary is not None else (self.btn_annulla,)
        self.add_footer(*actions, leading=self.btn_rimuovi)

    def _confirm(self, value: str) -> None:
        self._value = value
        self.accept()

    def selected_value(self) -> str:
        """Valore da scrivere nella cella; stringa vuota se l'assegnazione va rimossa."""

        return self._value


class _RigaSpecializzando(QFrame):
    def __init__(self, option: ResidentOption) -> None:
        super().__init__()
        self.setObjectName("RigaSpecializzando")
        self.setProperty("disponibile", option.available)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 6, 14, 6)
        layout.setSpacing(10)

        text = QVBoxLayout()
        text.setSpacing(2)
        name = QLabel(option.full_name)
        name.setObjectName("LblNomeSpec")
        text.addWidget(name)
        if option.conflict:
            reason = QLabel(option.conflict)
            reason.setObjectName("LblMotivoSpec")
            text.addWidget(reason)
        layout.addLayout(text, 1)

        if option.level:
            badge = QLabel(option.level)
            badge.setObjectName("BadgeLivello")
            badge.setProperty("livello", option.level)
            layout.addWidget(badge, 0, Qt.AlignmentFlag.AlignVCenter)


class DialogAssegnazioneSpecializzando(_DialogAssegnazione):
    """Sceglie lo specializzando per una cella dello scadenzario.

    ``options`` arriva già ordinato e con i conflitti calcolati
    (vedi :func:`src.roster_assignment.resident_options`). Gli specializzandi
    non disponibili restano visibili ma non selezionabili, con il motivo.
    """

    def __init__(
        self,
        options: Sequence[ResidentOption],
        context: str,
        current: str = "",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__("Assegna specializzando", context, current, parent)
        self._options = {option.label: option for option in options}
        self.resize(580, 660)

        current_option = self._options.get(current)
        lbl_current = QLabel(
            f"Assegnato ora: {current_option.full_name}"
            if current_option
            else "Nessuno specializzando assegnato"
        )
        lbl_current.setObjectName("LblAttuale")
        self.body.addWidget(lbl_current)

        self.search = QLineEdit()
        self.search.setObjectName("InputDialog")
        self.search.setPlaceholderText("Cerca per cognome o nome…")
        self.search.setClearButtonEnabled(True)
        self.search.setFixedHeight(42)
        self.search.textChanged.connect(self._filter)
        self.body.addWidget(self.search)

        self.lista = QListWidget()
        self.lista.setObjectName("ListaSpecializzandi")
        self.lista.setSelectionMode(QListWidget.SelectionMode.SingleSelection)
        self.lista.setVerticalScrollMode(QListWidget.ScrollMode.ScrollPerPixel)
        for option in options:
            self._add_item(option)
        self.body.addWidget(self.lista, 1)

        self.lbl_vuoto = QLabel("Nessuno specializzando corrisponde alla ricerca.")
        self.lbl_vuoto.setObjectName("LblVuoto")
        self.lbl_vuoto.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_vuoto.setVisible(False)
        self.body.addWidget(self.lbl_vuoto)

        self.btn_assegna = self.make_button("Assegna", "primary")
        self.btn_assegna.clicked.connect(lambda: self._assign(self.lista.currentItem()))
        self._add_footer(self.btn_assegna)

        self.lista.currentItemChanged.connect(self._update_assign_button)
        self.lista.itemDoubleClicked.connect(self._assign)
        if current_option is not None:
            self.lista.setCurrentItem(self._item_for(current))
        self._update_assign_button()
        self.search.setFocus()

    def _add_item(self, option: ResidentOption) -> None:
        item = QListWidgetItem()
        item.setData(Qt.ItemDataRole.UserRole, option.label)
        if not option.available:
            item.setFlags(
                item.flags() & ~(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            )
        row = _RigaSpecializzando(option)
        item.setSizeHint(QSize(0, _RESIDENT_ROW_HEIGHT))
        self.lista.addItem(item)
        self.lista.setItemWidget(item, row)

    def _item_for(self, label: str) -> QListWidgetItem | None:
        for index in range(self.lista.count()):
            item = self.lista.item(index)
            if item.data(Qt.ItemDataRole.UserRole) == label:
                return item
        return None

    @staticmethod
    def _selectable(item: QListWidgetItem | None) -> bool:
        return item is not None and bool(item.flags() & Qt.ItemFlag.ItemIsEnabled)

    def _update_assign_button(self) -> None:
        item = self.lista.currentItem()
        self.btn_assegna.setEnabled(self._selectable(item) and not item.isHidden())

    def _filter(self, query: str) -> None:
        visible = 0
        for index in range(self.lista.count()):
            item = self.lista.item(index)
            option = self._options[item.data(Qt.ItemDataRole.UserRole)]
            item.setHidden(not option.matches(query))
            visible += not item.isHidden()
        self.lbl_vuoto.setVisible(visible == 0)
        self._update_assign_button()

    def _assign(self, item: QListWidgetItem | None) -> None:
        if self._selectable(item):
            self._confirm(item.data(Qt.ItemDataRole.UserRole))


class DialogTipoGuardia(_DialogAssegnazione):
    """Sceglie il tipo di guardia del giorno; il click su un'opzione conferma subito."""

    def __init__(self, context: str, current: str = "", parent: QWidget | None = None) -> None:
        super().__init__("Tipo di guardia", context, current, parent)
        self.resize(480, 0)

        self.pulsanti_guardia: dict[str, QPushButton] = {}
        for code, description in GUARD_TYPES:
            button = QPushButton(f"{code}   ·   {description}")
            button.setObjectName("BtnGuardia")
            button.setProperty("codice", code)
            button.setCheckable(True)
            button.setChecked(code == current)
            button.setFixedHeight(54)
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            button.clicked.connect(lambda _checked=False, value=code: self._confirm(value))
            self.body.addWidget(button)
            self.pulsanti_guardia[code] = button

        self._add_footer()
