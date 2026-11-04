"""Finestra di attesa mentre il modello calcola il piano: rotellina, tempo e annullamento."""

from __future__ import annotations

import time

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import QLabel, QProgressBar, QWidget

from src.views.components.modal_dialog import ModalDialog
from src.views.dialog_pianificazione import testo_tempo

_ACCENTO = "#6f42c1"
_TRACCIA = "#ede9fe"


class Rotellina(QWidget):
    """Arco che gira: il programma sta lavorando."""

    def __init__(self, lato: int = 64, parent: QWidget | None = None):
        super().__init__(parent)
        self.setFixedSize(lato, lato)
        self._angolo = 0
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._avanza)
        self._timer.start(16)

    def ferma(self) -> None:
        self._timer.stop()

    def _avanza(self) -> None:
        self._angolo = (self._angolo + 6) % 360
        self.update()

    def paintEvent(self, _evento) -> None:  # noqa: N802 (nome Qt)
        pittore = QPainter(self)
        pittore.setRenderHint(QPainter.RenderHint.Antialiasing)
        spessore = 6
        area = QRectF(spessore, spessore, self.width() - 2 * spessore, self.height() - 2 * spessore)
        penna = QPen(QColor(_TRACCIA), spessore)
        pittore.setPen(penna)
        pittore.drawEllipse(area)
        penna.setColor(QColor(_ACCENTO))
        penna.setCapStyle(Qt.PenCapStyle.RoundCap)
        pittore.setPen(penna)
        # Qt misura gli angoli in sedicesimi di grado, in senso antiorario.
        pittore.drawArc(area, -self._angolo * 16, 100 * 16)
        pittore.end()


class DialogAttesaPianificazione(ModalDialog):
    """Resta aperta finché il calcolo non finisce; ``chiudi()`` la chiude dal controller.

    «Annulla pianificazione», Esc o la chiusura della finestra emettono
    :attr:`annullamento_richiesto`: il calcolo si ferma in modo cooperativo e la finestra
    si chiude quando il lavoro è davvero terminato.
    """

    annullamento_richiesto = Signal()

    def __init__(self, *, settimana: str, limite_secondi: float, parent: QWidget | None = None):
        super().__init__(
            "Pianificazione in corso",
            f"Sale Operatorie · {settimana} · Previsto",
            section="sale_operatorie",
            extra_styles=("dialog_pianificazione.qss",),
            parent=parent,
        )
        self.resize(460, 0)
        self._limite = max(1.0, float(limite_secondi))
        self._inizio = time.monotonic()
        self._chiudibile = False

        self.rotellina = Rotellina()
        self.body.addSpacing(6)
        self.body.addWidget(self.rotellina, 0, Qt.AlignmentFlag.AlignHCenter)
        self.lbl_messaggio = QLabel("Il modello sta cercando il piano migliore…")
        self.lbl_messaggio.setObjectName("MessaggioAttesa")
        self.lbl_messaggio.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.lbl_messaggio.setWordWrap(True)
        self.body.addWidget(self.lbl_messaggio)
        self.lbl_tempo = QLabel()
        self.lbl_tempo.setObjectName("TempoAttesa")
        self.lbl_tempo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.body.addWidget(self.lbl_tempo)
        self.barra_tempo = QProgressBar()
        self.barra_tempo.setObjectName("BarraTempoAttesa")
        self.barra_tempo.setRange(0, 1000)
        self.barra_tempo.setTextVisible(False)
        self.barra_tempo.setFixedHeight(6)
        self.body.addWidget(self.barra_tempo)

        self.btn_annulla = self.make_button("Annulla pianificazione", "danger")
        self.btn_annulla.clicked.connect(self._chiedi_annullamento)
        self.add_footer(self.btn_annulla)

        self._orologio = QTimer(self)
        self._orologio.timeout.connect(self._aggiorna_tempo)
        self._orologio.start(250)
        self._aggiorna_tempo()

    def _aggiorna_tempo(self) -> None:
        trascorsi = time.monotonic() - self._inizio
        self.lbl_tempo.setText(
            f"Trascorsi {testo_tempo(trascorsi)} · limite {testo_tempo(self._limite)}"
        )
        self.barra_tempo.setValue(min(1000, int(trascorsi / self._limite * 1000)))

    def _chiedi_annullamento(self) -> None:
        if not self.btn_annulla.isEnabled():
            return
        self.btn_annulla.setEnabled(False)
        self.btn_annulla.setText("Annullamento in corso…")
        self.lbl_messaggio.setText("Interruzione del calcolo: il piano precedente resta invariato.")
        self.annullamento_richiesto.emit()

    def reject(self) -> None:
        """Esc e chiusura non nascondono la finestra: chiedono di annullare il calcolo."""
        if self._chiudibile:
            super().reject()
        else:
            self._chiedi_annullamento()

    def chiudi(self) -> None:
        """Chiamata dal controller quando il calcolo è finito (in qualsiasi modo)."""
        self._chiudibile = True
        self._orologio.stop()
        self.rotellina.ferma()
        self.accept()
