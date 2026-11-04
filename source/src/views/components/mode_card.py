"""Card di scelta della modalità (Storico, Mese Corrente/Consultazione, Pianificazione)."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QGraphicsDropShadowEffect, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)

from src.views.components.calendar_toolbar import icona_colorata
from src.views.components.section_header import TONI_MODALITA

_ALTEZZA = 318
_LATO_BADGE = 84
_LATO_ICONA = 40
_RAGGIO = 18
_OMBRA = {False: (28, 6, 26), True: (46, 14, 46)}
"""Ombra a riposo e con il mouse sopra: (sfocatura, scostamento verticale, opacità)."""


class CardModalita(QPushButton):
    """Card cliccabile con bordo superiore colorato, icona SVG nel tondo, titolo,
    descrizione e invito «Accedi».

    Usa i colori di :data:`TONI_MODALITA`, gli stessi della banda della pagina in cui
    porta. Con il mouse sopra (o il focus da tastiera) la card si solleva e icona e
    invito si riempiono del colore della modalità.
    """

    def __init__(self, codice: str, titolo: str, descrizione: str, icona: str, parent=None):
        super().__init__(parent)
        self.setObjectName("CardModalita")
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        # Altezza fissa: titolo della pagina e card restano un blocco unico, centrato.
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(_ALTEZZA)
        self.setMinimumWidth(236)
        self.setMaximumWidth(360)
        self.setAccessibleName(f"{titolo}: {descrizione.replace(chr(10), ' ')}")
        self._inizio, self._fine, self._testo, self._tinta = TONI_MODALITA[codice]
        self._icona_colore = icona_colorata(icona, self._testo, _LATO_ICONA)
        self._icona_bianca = icona_colorata(icona, "#ffffff", _LATO_ICONA)
        self._focus_da_tastiera = False

        self._ombra = QGraphicsDropShadowEffect(self)
        self.setGraphicsEffect(self._ombra)

        interno = QVBoxLayout(self)
        interno.setContentsMargins(22, 30, 22, 26)
        interno.setSpacing(0)

        self._badge = QLabel()
        self._badge.setObjectName("CardIcona")
        self._badge.setFixedSize(_LATO_BADGE, _LATO_BADGE)
        self._badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        interno.addWidget(self._badge, 0, Qt.AlignmentFlag.AlignHCenter)
        interno.addSpacing(20)

        lbl_titolo = QLabel(titolo)
        lbl_titolo.setObjectName("CardTitolo")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        interno.addWidget(lbl_titolo)
        interno.addSpacing(8)

        lbl_descrizione = QLabel(descrizione)
        lbl_descrizione.setObjectName("CardDescrizione")
        lbl_descrizione.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_descrizione.setWordWrap(True)
        interno.addWidget(lbl_descrizione)
        interno.addStretch(1)

        self._azione = QLabel("Accedi  →")
        self._azione.setObjectName("CardAzione")
        self._azione.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._azione.setFixedHeight(38)
        self._azione.setMinimumWidth(130)
        interno.addWidget(self._azione, 0, Qt.AlignmentFlag.AlignHCenter)

        for etichetta in (self._badge, lbl_titolo, lbl_descrizione, self._azione):
            etichetta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        self.setStyleSheet(self._stile())
        self._evidenzia(False)

    def _stile(self) -> str:
        sfumatura = (
            f"qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {self._inizio}, "
            f"stop:1 {self._fine})"
        )
        return f"""
            /* Il bordo superiore spesso fa da striscia colorata e segue gli angoli. */
            QPushButton#CardModalita {{
                background-color: #ffffff;
                border: 1px solid #e2e8f0;
                border-top: 6px solid {self._fine};
                border-radius: {_RAGGIO}px;
            }}
            QPushButton#CardModalita:hover,
            QPushButton#CardModalita[evidenziata="true"] {{
                border: 1.5px solid {self._fine};
                border-top: 6px solid {self._inizio};
            }}
            QPushButton#CardModalita:pressed {{ background-color: {self._tinta}; }}
            QLabel {{ background: transparent; border: none; }}
            QLabel#CardTitolo {{
                font-family: "Segoe UI"; font-size: 22px; font-weight: bold;
                color: {self._testo};
            }}
            QLabel#CardDescrizione {{ font-size: 14px; color: #64748b; }}
            QLabel#CardIcona[attiva="false"] {{
                background-color: {self._tinta}; border-radius: {_LATO_BADGE // 2}px;
            }}
            QLabel#CardIcona[attiva="true"] {{
                background: {sfumatura}; border-radius: {_LATO_BADGE // 2}px;
            }}
            QLabel#CardAzione {{
                font-size: 13px; font-weight: bold; letter-spacing: 0.5px;
                border-radius: 19px; padding: 0 22px;
            }}
            QLabel#CardAzione[attiva="false"] {{
                background-color: {self._tinta}; color: {self._testo};
            }}
            QLabel#CardAzione[attiva="true"] {{
                background: {sfumatura}; color: #ffffff;
            }}
        """

    def _evidenzia(self, attiva: bool) -> None:
        icona = self._icona_bianca if attiva else self._icona_colore
        self._badge.setPixmap(icona.pixmap(QSize(_LATO_ICONA, _LATO_ICONA)))
        self.setProperty("evidenziata", attiva)
        for etichetta in (self._badge, self._azione):
            etichetta.setProperty("attiva", attiva)
        for widget in (self, self._badge, self._azione):
            widget.style().unpolish(widget)
            widget.style().polish(widget)
        sfocatura, scostamento, opacita = _OMBRA[attiva]
        self._ombra.setBlurRadius(sfocatura)
        self._ombra.setOffset(0, scostamento)
        self._ombra.setColor(QColor(15, 23, 42, opacita))

    def enterEvent(self, event) -> None:  # noqa: N802 (nome Qt)
        super().enterEvent(event)
        self._evidenzia(True)

    def leaveEvent(self, event) -> None:  # noqa: N802
        super().leaveEvent(event)
        self._evidenzia(self._focus_da_tastiera)

    def focusInEvent(self, event) -> None:  # noqa: N802
        # Solo il focus portato dall'utente con Tab: quello che Qt dà da solo alla prima
        # card quando la pagina compare sembrerebbe una scelta già fatta.
        super().focusInEvent(event)
        self._focus_da_tastiera = event.reason() in (
            Qt.FocusReason.TabFocusReason, Qt.FocusReason.BacktabFocusReason
        )
        if self._focus_da_tastiera:
            self._evidenzia(True)

    def focusOutEvent(self, event) -> None:  # noqa: N802
        super().focusOutEvent(event)
        self._focus_da_tastiera = False
        self._evidenzia(self.underMouse())
