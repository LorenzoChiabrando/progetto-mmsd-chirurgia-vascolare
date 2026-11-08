"""Banda in cima alle pagine calendario: dice in quale sezione e modalità ci si trova."""

from __future__ import annotations

from collections.abc import Sequence

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QButtonGroup, QFrame, QGridLayout, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QVBoxLayout, QWidget,
)

TONI_MODALITA = {
    "STORICO": ("#334155", "#64748b", "#475569", "#f1f5f9"),
    "CORRENTE": ("#14532d", "#16a34a", "#15803d", "#dcfce7"),
    "CONSULTAZIONE": ("#14532d", "#16a34a", "#15803d", "#dcfce7"),
    "PIANIFICAZIONE": ("#312e81", "#4f46e5", "#3730a3", "#e0e7ff"),
    # Sezioni senza modalità, con l'accento che usano già nelle loro pagine.
    "LIBRETTO": ("#312e81", "#4338ca", "#3730a3", "#e0e7ff"),
    "PAZIENTI": ("#0c4a6e", "#0284c7", "#0369a1", "#e0f2fe"),
}
"""Colori di ogni modalità (e delle sezioni Libretto e Pazienti), condivisi da banda e
card di selezione: inizio e fine della sfumatura, testo in evidenza, tinta chiara."""
_SFONDO_PAGINA = "#f1f5f9"  # la scheda attiva prosegue nella pagina sottostante


class BandaSezione(QFrame):
    """Fascia a tutta larghezza con sezione, modalità, descrizione e schede delle modalità.

    ``modalita`` elenca ``(codice, titolo, descrizione)``. Cliccando una scheda diversa
    da quella attiva emette ``modalita_scelta``; la scheda evidenziata cambia solo con
    :meth:`imposta_modalita`, così se il controller non può aprire quella modalità
    (per esempio uno storico vuoto) la banda continua a mostrare quella vera.

    Senza ``modalita`` è l'intestazione di una pagina di dettaglio (una persona, un
    giorno): niente schede, testi e colori con :meth:`imposta_intestazione`.
    """

    modalita_scelta = Signal(str)

    def __init__(
        self,
        sezione: str,
        modalita: Sequence[tuple[str, str, str]] = (),
        parent=None,
        *,
        testo_indietro: str = "← Indietro",
        aiuto_indietro: str = "Torna alla scelta della modalità",
    ):
        super().__init__(parent)
        self.setObjectName("BandaSezione")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._modalita = {codice: (titolo, descr) for codice, titolo, descr in modalita}
        self._corrente: str | None = None

        griglia = QGridLayout(self)
        # Con le schede il bordo inferiore è la riga delle schede; senza, serve aria.
        griglia.setContentsMargins(24, 18, 20, 0 if modalita else 22)
        griglia.setSpacing(0)

        centro = QVBoxLayout()
        centro.setSpacing(2)

        self.lbl_sezione = QLabel(sezione.upper())
        self.lbl_sezione.setObjectName("BandaSezioneNome")
        font = self.lbl_sezione.font()
        font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 3)
        self.lbl_sezione.setFont(font)
        self.lbl_titolo = QLabel()
        self.lbl_titolo.setObjectName("BandaTitolo")
        self.lbl_descrizione = QLabel()
        self.lbl_descrizione.setObjectName("BandaDescrizione")
        for etichetta in (self.lbl_sezione, self.lbl_titolo, self.lbl_descrizione):
            etichetta.setAlignment(Qt.AlignmentFlag.AlignCenter)
            centro.addWidget(etichetta)
        if modalita:
            centro.addSpacing(14)

        schede = QHBoxLayout()
        schede.setSpacing(6)
        schede.addStretch()
        self._gruppo = QButtonGroup(self)
        self.schede: dict[str, QPushButton] = {}
        for codice, titolo, _descrizione in modalita:
            scheda = QPushButton(titolo)
            scheda.setObjectName("BandaScheda")
            scheda.setCheckable(True)
            scheda.setCursor(Qt.CursorShape.PointingHandCursor)
            scheda.setAccessibleName(f"Passa a {titolo}")
            scheda.clicked.connect(lambda _checked=False, c=codice: self._scheda_cliccata(c))
            self._gruppo.addButton(scheda)
            self.schede[codice] = scheda
            schede.addWidget(scheda)
        schede.addStretch()
        if modalita:
            centro.addLayout(schede)
        griglia.addLayout(centro, 0, 0)

        # Nella stessa cella del testo, allineato in alto a destra: il testo resta centrato
        # sulla banda intera, non sullo spazio rimasto accanto al pulsante.
        self.btn_indietro = QPushButton(testo_indietro)
        self.btn_indietro.setObjectName("BandaIndietro")
        self.btn_indietro.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_indietro.setToolTip(aiuto_indietro)
        griglia.addWidget(
            self.btn_indietro, 0, 0,
            Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignRight,
        )

    @property
    def modalita_corrente(self) -> str | None:
        return self._corrente

    def imposta_modalita(self, codice: str | None) -> None:
        """Mostra titolo, descrizione, colori e scheda attiva della modalità ``codice``."""

        if codice not in self._modalita:
            return
        self._corrente = codice
        titolo, descrizione = self._modalita[codice]
        self.lbl_titolo.setText(titolo)
        self.lbl_descrizione.setText(descrizione)
        self.schede[codice].setChecked(True)
        inizio, fine, testo, _tinta = TONI_MODALITA.get(codice, TONI_MODALITA["STORICO"])
        self.setStyleSheet(_stile(inizio, fine, testo))

    def imposta_intestazione(self, titolo: str, descrizione: str, tono: str) -> None:
        """Testi e colori liberi, per le pagine di dettaglio senza modalità."""

        self.lbl_titolo.setText(titolo)
        self.lbl_descrizione.setText(descrizione)
        inizio, fine, testo, _tinta = TONI_MODALITA.get(tono, TONI_MODALITA["STORICO"])
        self.setStyleSheet(_stile(inizio, fine, testo))

    def _scheda_cliccata(self, codice: str) -> None:
        if self._corrente in self.schede:
            self.schede[self._corrente].setChecked(True)
        if codice != self._corrente:
            self.modalita_scelta.emit(codice)


def pagina_scorrevole(banda: BandaSezione, pagina: QWidget) -> QScrollArea:
    """Banda e pagina del calendario in un'unica area che scorre.

    Scendendo, la banda esce dalla vista; il calendario si mostra per intero e chi
    ha poco schermo scorre la pagina, come in un documento. Va messa nello
    ``QStackedWidget`` al posto della pagina: solo il calendario scorre, la pagina
    delle card resta fissa (lo stack misura anche le pagine nascoste, quindi con
    un'area unica anche le card scorrerebbero nel vuoto, lunghe quanto il calendario).
    """

    contenuto = QWidget()
    contenuto.setObjectName("ContenutoPagina")
    colonna = QVBoxLayout(contenuto)
    colonna.setContentsMargins(0, 0, 0, 0)
    colonna.setSpacing(0)
    colonna.addWidget(banda)
    colonna.addWidget(pagina, 1)

    area = QScrollArea()
    area.setObjectName("ScrollPagina")
    area.setWidgetResizable(True)
    area.setFrameShape(QFrame.Shape.NoFrame)
    area.setWidget(contenuto)
    # Lo sfondo della pagina (#f1f5f9) viene dalla vista che contiene l'area.
    area.viewport().setAutoFillBackground(False)
    contenuto.setAutoFillBackground(False)
    return area


def _stile(inizio: str, fine: str, testo_attivo: str) -> str:
    return f"""
        QFrame#BandaSezione {{
            background: qlineargradient(x1:0, y1:0, x2:1, y2:0,
                                        stop:0 {inizio}, stop:1 {fine});
            border: none;
        }}
        QFrame#BandaSezione QLabel {{ background: transparent; color: #ffffff; }}
        QLabel#BandaSezioneNome {{
            color: rgba(255, 255, 255, 200); font-size: 12px; font-weight: bold;
        }}
        QLabel#BandaTitolo {{ font-size: 30px; font-weight: bold; }}
        QLabel#BandaDescrizione {{ color: rgba(255, 255, 255, 220); font-size: 14px; }}
        QPushButton#BandaIndietro {{
            background-color: rgba(255, 255, 255, 38); color: #ffffff;
            border: 1.5px solid rgba(255, 255, 255, 120); border-radius: 8px;
            font-size: 13px; font-weight: bold; padding: 8px 18px;
        }}
        QPushButton#BandaIndietro:hover {{ background-color: rgba(255, 255, 255, 70); }}
        QPushButton#BandaIndietro:disabled {{
            color: rgba(255, 255, 255, 120); border-color: rgba(255, 255, 255, 60);
        }}
        QPushButton#BandaScheda {{
            background-color: rgba(255, 255, 255, 28); color: rgba(255, 255, 255, 210);
            border: none; border-top-left-radius: 10px; border-top-right-radius: 10px;
            font-size: 13px; font-weight: bold; padding: 10px 28px;
        }}
        QPushButton#BandaScheda:hover {{
            background-color: rgba(255, 255, 255, 60); color: #ffffff;
        }}
        QPushButton#BandaScheda:checked {{
            background-color: {_SFONDO_PAGINA}; color: {testo_attivo};
        }}
        QPushButton#BandaScheda:disabled {{ color: rgba(255, 255, 255, 110); }}
        QPushButton#BandaScheda:checked:disabled {{ color: {testo_attivo}; }}
    """
