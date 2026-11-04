"""Riga del periodo e pannello dei filtri, uguali in Scadenzario e Sale Operatorie.

Qui c'è solo la struttura: i colori stanno nel ``.qss`` di ogni sezione, così ognuna
mantiene il proprio accento (indaco lo Scadenzario, viola le Sale Operatorie).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from PySide6.QtCore import QByteArray, QSize, Qt, Signal
from PySide6.QtGui import QFont, QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QSizePolicy,
    QSpacerItem, QVBoxLayout, QWidget,
)

from src.data_paths import PROJECT_ROOT

_ICONE = PROJECT_ROOT / "asset" / "images" / "icons"


def riga_periodo(
    btn_prev: QPushButton, btn_periodo: QPushButton, btn_next: QPushButton,
) -> QHBoxLayout:
    """``‹ periodo ›`` centrati sulla pagina."""

    riga = QHBoxLayout()
    riga.setContentsMargins(0, 2, 0, 2)
    riga.setSpacing(10)
    riga.addStretch(1)
    riga.addWidget(btn_prev)
    riga.addWidget(btn_periodo)
    riga.addWidget(btn_next)
    riga.addStretch(1)
    return riga


def icona_colorata(nome: str, colore: str, lato: int = 18) -> QIcon:
    """Icona SVG di ``asset/images/icons`` disegnata nel colore ``colore``.

    Le icone sono disegnate in nero (``#000000``): il colore si sostituisce qui, così
    un solo file serve a tutte le sezioni, ognuna con il proprio accento.
    """

    try:
        svg = (_ICONE / nome).read_text(encoding="utf-8").replace("#000000", colore)
    except OSError:
        return QIcon()
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    icona = QIcon()
    for scala in (1, 2):  # nitida anche sugli schermi ad alta densità
        pixmap = QPixmap(lato * scala, lato * scala)
        pixmap.fill(Qt.GlobalColor.transparent)
        pittore = QPainter(pixmap)
        renderer.render(pittore)
        pittore.end()
        pixmap.setDevicePixelRatio(scala)
        icona.addPixmap(pixmap)
    return icona


def pulsante_esporta_pdf(colore: str) -> QPushButton:
    """Pulsante «Esporta PDF» con l'icona del documento nel colore della sezione."""

    pulsante = QPushButton("Esporta PDF")
    pulsante.setObjectName("BtnEsportaPdf")
    pulsante.setIcon(icona_colorata("file-pdf.svg", colore))
    pulsante.setIconSize(QSize(18, 18))
    pulsante.setCursor(Qt.CursorShape.PointingHandCursor)
    pulsante.setToolTip("Esporta il mese o una sua settimana in un file PDF")
    return pulsante


# Colori degli stati, gli stessi dei badge usati finora: (sfondo, bordo, testo, icona).
_COLORI_STATO = {
    "BOZZA": ("#fef3c7", "#fcd34d", "#92400e", "✎"),
    "CONVALIDATO": ("#dcfce7", "#86efac", "#14532d", "✓"),
    "ASSENTE": ("#e2e8f0", "#cbd5e1", "#334155", "○"),
    "RIEPILOGO": ("#dbeafe", "#93c5fd", "#1e3a8a", "≡"),
}


class _TestoFacoltativo(QLabel):
    """Etichetta che sparisce quando non ha testo, senza lasciare una riga vuota."""

    def setText(self, testo: str) -> None:  # noqa: N802 (nome Qt)
        super().setText(testo)
        self.setVisible(bool(testo))


class StatoPeriodo(QFrame):
    """Fascia a tutta larghezza che dice in che stato è il periodo mostrato.

    ``testi`` associa a ogni stato (``BOZZA``, ``CONVALIDATO``, ``ASSENTE``,
    ``RIEPILOGO``) il titolo e il significato, per esempio ``("Mese in bozza",
    "non ancora convalidato: si può ancora modificare")``. Sotto compare
    :attr:`lbl_dettaglio`, il messaggio del controller sulla versione.
    """

    def __init__(self, testi: Mapping[str, tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setObjectName("StatoPeriodo")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._testi = dict(testi)
        self.stato: str | None = None

        riga = QHBoxLayout(self)
        riga.setContentsMargins(14, 10, 16, 10)
        riga.setSpacing(14)

        self.lbl_icona = QLabel()
        self.lbl_icona.setObjectName("StatoIcona")
        self.lbl_icona.setFixedSize(36, 36)
        self.lbl_icona.setAlignment(Qt.AlignmentFlag.AlignCenter)
        riga.addWidget(self.lbl_icona, 0, Qt.AlignmentFlag.AlignVCenter)

        testi_col = QVBoxLayout()
        testi_col.setSpacing(2)
        intestazione = QHBoxLayout()
        intestazione.setSpacing(10)
        self.lbl_titolo = QLabel()
        self.lbl_titolo.setObjectName("StatoTitolo")
        self.lbl_significato = QLabel()
        self.lbl_significato.setObjectName("StatoSignificato")
        intestazione.addWidget(self.lbl_titolo)
        intestazione.addWidget(self.lbl_significato, 1)
        testi_col.addLayout(intestazione)
        self.lbl_dettaglio = _TestoFacoltativo()
        self.lbl_dettaglio.setObjectName("StatoDettaglio")
        self.lbl_dettaglio.setWordWrap(True)
        self.lbl_dettaglio.hide()
        testi_col.addWidget(self.lbl_dettaglio)
        riga.addLayout(testi_col, 1)

    def imposta_stato(self, stato: str) -> None:
        sfondo, bordo, testo, simbolo = _COLORI_STATO.get(stato, _COLORI_STATO["ASSENTE"])
        titolo, significato = self._testi.get(stato, (stato.capitalize(), ""))
        self.stato = stato
        self.lbl_icona.setText(simbolo)
        self.lbl_titolo.setText(titolo)
        self.lbl_significato.setText(f"· {significato}" if significato else "")
        self.setAccessibleName(f"{titolo}. {significato}")
        self.setStyleSheet(f"""
            QFrame#StatoPeriodo {{
                background-color: {sfondo};
                border: 1px solid {bordo};
                border-left: 6px solid {testo};
                border-radius: 10px;
            }}
            QFrame#StatoPeriodo QLabel {{ background: transparent; border: none; color: {testo}; }}
            QFrame#StatoPeriodo QLabel#StatoIcona {{
                background-color: {testo}; color: {sfondo};
                border-radius: 18px; font-size: 18px; font-weight: bold;
            }}
            QLabel#StatoTitolo {{ font-size: 16px; font-weight: bold; }}
            QLabel#StatoSignificato {{ font-size: 14px; }}
            QLabel#StatoDettaglio {{ font-size: 12px; }}
        """)


def _prepara_segmenti(pulsanti: list[QPushButton]) -> None:
    """Solo i bordi esterni del gruppo sono arrotondati: si legge come un unico controllo."""

    ultimo = len(pulsanti) - 1
    for indice, pulsante in enumerate(pulsanti):
        pulsante.setObjectName("BtnSegmento")
        pulsante.setCheckable(True)
        pulsante.setCursor(Qt.CursorShape.PointingHandCursor)
        if ultimo == 0:
            posizione = "unico"
        else:
            posizione = "primo" if indice == 0 else "ultimo" if indice == ultimo else "mezzo"
        pulsante.setProperty("posizione", posizione)
        pulsante.style().unpolish(pulsante)
        pulsante.style().polish(pulsante)


def segmentato(*pulsanti: QPushButton) -> QFrame:
    """Alternative esclusive fatte di pulsanti che il controller collega uno per uno."""

    contenitore = QFrame()
    contenitore.setObjectName("Segmentato")
    riga = QHBoxLayout(contenitore)
    riga.setContentsMargins(0, 0, 0, 0)
    riga.setSpacing(0)
    gruppo = QButtonGroup(contenitore)
    gruppo.setExclusive(True)
    _prepara_segmenti(list(pulsanti))
    for pulsante in pulsanti:
        gruppo.addButton(pulsante)
        riga.addWidget(pulsante)
    return contenitore


class SceltaSegmentata(QFrame):
    """Scelta a pulsanti con la parte di interfaccia di ``QComboBox`` usata dai controller.

    Tutte le opzioni restano visibili (al posto di un menu a tendina) ma il controller
    continua a usare ``addItem``, ``currentData``, ``findData``, ``setCurrentIndex``,
    ``blockSignals`` e ``currentIndexChanged`` come con un menu.
    """

    currentIndexChanged = Signal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Segmentato")
        self._riga = QHBoxLayout(self)
        self._riga.setContentsMargins(0, 0, 0, 0)
        self._riga.setSpacing(0)
        self._gruppo = QButtonGroup(self)
        self._gruppo.setExclusive(True)
        self._gruppo.idClicked.connect(self.setCurrentIndex)
        self._pulsanti: list[QPushButton] = []
        self._dati: list[Any] = []
        self._indice = -1

    def addItem(self, testo: str, dato: Any = None) -> None:
        pulsante = QPushButton(testo)
        self._gruppo.addButton(pulsante, len(self._pulsanti))
        self._pulsanti.append(pulsante)
        self._dati.append(dato)
        self._riga.addWidget(pulsante)
        _prepara_segmenti(self._pulsanti)
        if self._indice < 0:
            self.setCurrentIndex(0)

    def currentIndex(self) -> int:
        return self._indice

    def currentData(self) -> Any:
        return self._dati[self._indice] if 0 <= self._indice < len(self._dati) else None

    def findData(self, dato: Any) -> int:
        return next((i for i, valore in enumerate(self._dati) if valore == dato), -1)

    def setCurrentIndex(self, indice: int) -> None:
        if not 0 <= indice < len(self._pulsanti):
            return
        self._pulsanti[indice].setChecked(True)
        if indice != self._indice:
            self._indice = indice
            self.currentIndexChanged.emit(indice)


class BarraStrumenti(QFrame):
    """Pannello dei filtri: gruppi con il titolo sopra, azioni a destra, note sotto."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("BarraStrumenti")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        colonna = QVBoxLayout(self)
        colonna.setContentsMargins(18, 12, 14, 10)
        colonna.setSpacing(10)

        # Griglia a due righe (titoli, controlli): i titoli restano allineati anche se un
        # controllo è più alto degli altri, e le azioni stanno sulla riga dei controlli.
        self._griglia = QGridLayout()
        self._griglia.setHorizontalSpacing(18)
        self._griglia.setVerticalSpacing(6)
        self._colonne = 0
        self._gruppi: list[tuple[QFrame | None, QLabel, QWidget]] = []
        self._azioni = QHBoxLayout()
        self._azioni.setSpacing(8)
        colonna.addLayout(self._griglia)

        self._divisore_info = QFrame()
        self._divisore_info.setObjectName("BarraStrumentiDivisore")
        self._divisore_info.setFixedHeight(1)
        colonna.addWidget(self._divisore_info)

        self.riga_info = QHBoxLayout()
        self.riga_info.setSpacing(12)
        colonna.addLayout(self.riga_info)

    def aggiungi_gruppo(self, titolo: str, controllo: QWidget) -> None:
        divisore = None
        if self._colonne:
            divisore = QFrame()
            divisore.setObjectName("BarraStrumentiDivisore")
            divisore.setFixedWidth(1)
            self._griglia.addWidget(divisore, 0, self._colonne, 2, 1)
            self._colonne += 1
        etichetta = QLabel(titolo.upper())
        etichetta.setObjectName("LblGruppoBarra")
        font = etichetta.font()
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.2)
        etichetta.setFont(font)
        self._griglia.addWidget(etichetta, 0, self._colonne, Qt.AlignmentFlag.AlignLeft)
        self._griglia.addWidget(
            controllo, 1, self._colonne,
            Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter,
        )
        self._colonne += 1
        self._gruppi.append((divisore, etichetta, controllo))

    def imposta_gruppo_visibile(self, controllo: QWidget, visibile: bool) -> None:
        """Mostra o nasconde il gruppo di ``controllo`` (titolo compreso).

        Le linee divisorie restano solo tra gruppi visibili, così nascondere il primo
        gruppo non lascia una linea in testa al pannello.
        """

        for _divisore, etichetta, gruppo in self._gruppi:
            if gruppo is controllo:
                etichetta.setVisible(visibile)
                gruppo.setVisible(visibile)
        visto_prima = False
        for divisore, _etichetta, gruppo in self._gruppi:
            mostrato = not gruppo.isHidden()
            if divisore is not None:
                divisore.setVisible(mostrato and visto_prima)
            visto_prima = visto_prima or mostrato

    def aggiungi_azione(self, pulsante: QPushButton) -> None:
        """Pulsante a destra, sulla riga dei controlli. Va aggiunto dopo tutti i gruppi."""
        if not self._azioni.count():
            # Lo spazio libero va tra i filtri e le azioni, che restano a destra.
            spazio = self._colonne
            self._griglia.addItem(
                QSpacerItem(0, 0, QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum),
                1, spazio,
            )
            self._griglia.setColumnStretch(spazio, 1)
            self._griglia.addLayout(
                self._azioni, 1, spazio + 1, Qt.AlignmentFlag.AlignVCenter
            )
        self._azioni.addWidget(pulsante)

    def aggiungi_info(self, widget: QWidget, stretch: int = 0) -> None:
        self.riga_info.addWidget(widget, stretch)

    def mostra_riga_info(self, visibile: bool) -> None:
        """Mostra o nasconde la riga delle note sotto i filtri, linea compresa."""

        self._divisore_info.setVisible(visibile)
        for indice in range(self.riga_info.count()):
            widget = self.riga_info.itemAt(indice).widget()
            if widget is not None:
                widget.setVisible(visibile)


def etichetta_info(testo: str = "") -> QLabel:
    """Testo della riga informativa: va a capo invece di essere tagliato."""

    etichetta = QLabel(testo)
    etichetta.setObjectName("LblInfoBarra")
    etichetta.setWordWrap(True)
    etichetta.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
    return etichetta
