"""Cornice comune per tutti i dialog modali dell'applicazione."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import QDir, Qt
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from src.data_paths import PROJECT_ROOT

SECTIONS = ("pazienti", "libretto", "scadenzario", "sale_operatorie", "generale")
"""Sezioni dell'app: ognuna ha il proprio colore di accento in ``dialog.qss``.

``generale`` (grigio neutro) è per i messaggi che non appartengono a una sezione,
come gli errori di avvio o quelli imprevisti.
"""

TONES = ("normale", "avviso", "errore")
"""``avviso`` (ambra) ed ``errore`` (rosso) sostituiscono il colore della sezione."""

_BUTTON_OBJECT_NAMES = {
    "primary": "BtnSalvaDialog",
    "secondary": "BtnAnnullaDialog",
    "danger": "BtnPericoloDialog",
}
_BUTTON_HEIGHT = 44
_BUTTON_MIN_WIDTH = 130
_STYLES_DIR = PROJECT_ROOT / "asset" / "styles"
_ICONS_DIR = PROJECT_ROOT / "asset" / "images" / "icons"
_ICONS_PREFIX = "icons"
_HORIZONTAL_MARGIN = 32


def register_icon_path() -> None:
    """Rende disponibili nei QSS le icone ``url(icons:nome.svg)``.

    I fogli di stile Qt non supportano gli URI ``data:`` e risolvono i path relativi
    rispetto alla cartella di avvio: il search path li rende indipendenti da essa.
    Va chiamata prima di applicare un foglio di stile che usa le icone.
    """

    if str(_ICONS_DIR) not in QDir.searchPaths(_ICONS_PREFIX):
        QDir.addSearchPath(_ICONS_PREFIX, str(_ICONS_DIR))


def _read_style(name: str) -> str:
    try:
        return (_STYLES_DIR / name).read_text(encoding="utf-8")
    except OSError:
        return ""


class ModalDialog(QDialog):
    """Dialog modale con barra colorata, titolo, sottotitolo, contenuto e footer.

    Il contenuto va aggiunto a :attr:`body`; i pulsanti si creano con
    :meth:`make_button` e si dispongono con :meth:`add_footer`.

    Args:
        title: titolo mostrato nel dialog e nella barra della finestra.
        subtitle: testo descrittivo sotto il titolo; vuoto per nasconderlo.
        section: sezione dell'app, determina il colore di accento (vedi ``SECTIONS``).
        tone: ``"avviso"`` o ``"errore"`` per messaggi di attenzione (vedi ``TONES``).
        scrollable: rende scorrevole il contenuto lasciando fissi intestazione e footer.
        extra_styles: fogli QSS della sezione (in ``asset/styles``) con le regole dei
            widget specifici del dialog; la cornice comune viene applicata dopo.

    Raises:
        ValueError: se ``section`` o ``tone`` non sono tra i valori ammessi.
    """

    def __init__(
        self,
        title: str,
        subtitle: str = "",
        *,
        section: str,
        tone: str = "normale",
        scrollable: bool = False,
        extra_styles: Sequence[str] = (),
        parent: QWidget | None = None,
    ) -> None:
        if section not in SECTIONS:
            raise ValueError(f"sezione non valida: {section!r}; ammesse: {', '.join(SECTIONS)}")
        if tone not in TONES:
            raise ValueError(f"tono non valido: {tone!r}; ammessi: {', '.join(TONES)}")
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setModal(True)
        self.setProperty("sezione", section)
        self.setProperty("tono", tone)

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        accent = QFrame()
        accent.setObjectName("AccentBarDialog")
        accent.setFixedHeight(5)
        root.addWidget(accent)

        header = QVBoxLayout()
        header.setContentsMargins(_HORIZONTAL_MARGIN, 24, _HORIZONTAL_MARGIN, 0)
        header.setSpacing(6)
        self.lbl_titolo = QLabel(title)
        self.lbl_titolo.setObjectName("TitoloDialog")
        self.lbl_titolo.setWordWrap(True)
        header.addWidget(self.lbl_titolo)
        self.lbl_sottotitolo = QLabel(subtitle)
        self.lbl_sottotitolo.setObjectName("SottoTitoloDialog")
        self.lbl_sottotitolo.setWordWrap(True)
        self.lbl_sottotitolo.setVisible(bool(subtitle))
        header.addWidget(self.lbl_sottotitolo)
        header.addSpacing(10)
        separator = QFrame()
        separator.setObjectName("SeparatoreDialog")
        separator.setFixedHeight(1)
        header.addWidget(separator)
        root.addLayout(header)

        self.body = QVBoxLayout()
        self.body.setSpacing(12)
        self.body.setContentsMargins(_HORIZONTAL_MARGIN, 16, _HORIZONTAL_MARGIN, 8)
        if scrollable:
            content = QWidget()
            content.setObjectName("DialogContent")
            content.setLayout(self.body)
            scroll = QScrollArea()
            scroll.setObjectName("DialogScroll")
            scroll.setWidgetResizable(True)
            scroll.setFrameShape(QFrame.Shape.NoFrame)
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            scroll.setWidget(content)
            root.addWidget(scroll, 1)
        else:
            root.addLayout(self.body, 1)

        self.footer = QHBoxLayout()
        self.footer.setContentsMargins(_HORIZONTAL_MARGIN, 12, _HORIZONTAL_MARGIN, 24)
        self.footer.setSpacing(12)
        root.addLayout(self.footer)

        register_icon_path()
        styles = [_read_style(name) for name in extra_styles]
        styles.append(_read_style("dialog.qss"))
        self.setStyleSheet("\n".join(styles))

    def showEvent(self, event) -> None:
        """Adatta l'altezza ai testi a capo, che Qt non considera nelle finestre."""

        super().showEvent(event)
        needed = self.heightForWidth(self.width())
        if needed > self.height():
            self.resize(self.width(), needed)

    def make_button(self, text: str, role: str = "primary") -> QPushButton:
        """Crea un pulsante standard: ``primary``, ``secondary`` o ``danger``.

        Raises:
            ValueError: se ``role`` non è uno dei ruoli ammessi.
        """

        if role not in _BUTTON_OBJECT_NAMES:
            raise ValueError(
                f"ruolo pulsante non valido: {role!r}; ammessi: {', '.join(_BUTTON_OBJECT_NAMES)}"
            )
        button = QPushButton(text)
        button.setObjectName(_BUTTON_OBJECT_NAMES[role])
        button.setFixedHeight(_BUTTON_HEIGHT)
        button.setMinimumWidth(_BUTTON_MIN_WIDTH)
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        return button

    def add_footer(self, *buttons: QPushButton, leading: QPushButton | None = None) -> None:
        """Dispone i pulsanti: ``leading`` (es. elimina) a sinistra, gli altri a destra."""

        if leading is not None:
            self.footer.addWidget(leading)
        self.footer.addStretch(1)
        for button in buttons:
            self.footer.addWidget(button)
