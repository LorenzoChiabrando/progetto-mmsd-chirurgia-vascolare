"""Messaggi, conferme e scelte nello stile comune dei dialog.

Sostituiscono ``QMessageBox`` e ``QInputDialog`` usando :class:`ModalDialog`, così
anche gli avvisi hanno la cornice e il colore della sezione che li apre.
"""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QLabel, QPushButton, QWidget

from src.views.components.modal_dialog import ModalDialog

_KIND_TONES = {"info": "normale", "warning": "avviso", "error": "errore"}
_MESSAGE_WIDTH = 460
_OPTION_HEIGHT = 48


def _message_dialog(
    parent: QWidget | None, title: str, text: str, section: str, tone: str
) -> ModalDialog:
    dialog = ModalDialog(title, section=section, tone=tone, parent=parent)
    dialog.resize(_MESSAGE_WIDTH, 0)
    label = QLabel(text)
    label.setObjectName("LblMessaggioDialog")
    label.setWordWrap(True)
    label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
    dialog.body.addWidget(label)
    return dialog


def show_message(
    parent: QWidget | None, title: str, text: str, *, section: str, kind: str = "info"
) -> None:
    """Mostra un messaggio con il solo pulsante OK.

    Args:
        kind: ``"info"`` (colore della sezione), ``"warning"`` (ambra) o ``"error"`` (rosso).

    Raises:
        ValueError: se ``kind`` o ``section`` non sono validi.
    """

    if kind not in _KIND_TONES:
        raise ValueError(f"kind non valido: {kind!r}; ammessi: {', '.join(_KIND_TONES)}")
    dialog = _message_dialog(parent, title, text, section, _KIND_TONES[kind])
    ok = dialog.make_button("OK", "primary")
    ok.setDefault(True)
    ok.clicked.connect(dialog.accept)
    dialog.add_footer(ok)
    dialog.exec()


def ask_confirmation(
    parent: QWidget | None,
    title: str,
    text: str,
    *,
    section: str,
    confirm_text: str = "Conferma",
    destructive: bool = False,
) -> bool:
    """Chiede conferma con i pulsanti Annulla e ``confirm_text``.

    Con ``destructive=True`` il pulsante di conferma è rosso e Invio preme Annulla,
    per le operazioni non reversibili.

    Returns:
        ``True`` solo se l'utente ha confermato.
    """

    dialog = _message_dialog(parent, title, text, section, "normale")
    cancel = dialog.make_button("Annulla", "secondary")
    cancel.clicked.connect(dialog.reject)
    confirm = dialog.make_button(confirm_text, "danger" if destructive else "primary")
    confirm.clicked.connect(dialog.accept)
    (cancel if destructive else confirm).setDefault(True)
    dialog.add_footer(cancel, confirm)
    return dialog.exec() == QDialog.DialogCode.Accepted


def choose_option(
    parent: QWidget | None,
    title: str,
    text: str,
    options: Sequence[str],
    *,
    section: str,
) -> str | None:
    """Propone ``options`` come pulsanti: il click sceglie e chiude il dialog.

    Returns:
        L'opzione scelta, oppure ``None`` se l'utente annulla.

    Raises:
        ValueError: se ``options`` è vuota.
    """

    if not options:
        raise ValueError("servono una o più opzioni tra cui scegliere")
    dialog = ModalDialog(title, text, section=section, parent=parent)
    dialog.resize(_MESSAGE_WIDTH, 0)
    chosen: list[str] = []

    def choose(value: str) -> None:
        chosen.append(value)
        dialog.accept()

    for option in options:
        button = QPushButton(option)
        button.setObjectName("BtnOpzioneDialog")
        button.setFixedHeight(_OPTION_HEIGHT)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.clicked.connect(lambda _checked=False, value=option: choose(value))
        dialog.body.addWidget(button)

    cancel = dialog.make_button("Annulla", "secondary")
    cancel.clicked.connect(dialog.reject)
    dialog.add_footer(cancel)
    if dialog.exec() != QDialog.DialogCode.Accepted or not chosen:
        return None
    return chosen[-1]
