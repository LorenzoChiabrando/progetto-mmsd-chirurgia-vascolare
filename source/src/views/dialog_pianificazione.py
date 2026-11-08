"""Finestra «Pianifica settimana»: limite di tempo e gap relativo con due slider."""

from __future__ import annotations

import math

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDialog, QHBoxLayout, QLabel, QSlider, QVBoxLayout, QWidget

from src.optimization.parametri import ConfigurazioneParametri, ParametriPianificazione
from src.views.components.modal_dialog import ModalDialog

_LARGHEZZA = 620


def testo_tempo(secondi: float) -> str:
    """«45 s», «5 min», «1 min 30 s», «30 min»."""
    secondi = int(round(secondi))
    if secondi < 60:
        return f"{secondi} s"
    minuti, resto = divmod(secondi, 60)
    return f"{minuti} min {resto} s" if resto else f"{minuti} min"


def testo_percento(percento: float) -> str:
    """«0,01%», «0,5%», «10%»: virgola decimale, senza zeri inutili."""
    testo = f"{percento:.4f}".rstrip("0").rstrip(".")
    return f"{testo.replace('.', ',')}%"


def _indice_vicino(valori: tuple[float, ...], valore: float) -> int:
    """Posizione dello slider più vicina a ``valore`` (anche se fuori dai limiti attuali)."""
    if valore <= 0:
        return 0
    return min(
        range(len(valori)),
        key=lambda i: abs(math.log(valori[i]) - math.log(valore)),
    )


class _CursoreParametro(QWidget):
    """Titolo, valore scelto, slider e i due estremi sotto."""

    def __init__(self, titolo: str, aiuto: str, valori: tuple[float, ...], formatta):
        super().__init__()
        self._valori = valori
        self._formatta = formatta
        colonna = QVBoxLayout(self)
        colonna.setContentsMargins(0, 0, 0, 0)
        colonna.setSpacing(6)

        intestazione = QHBoxLayout()
        etichetta = QLabel(titolo.upper())
        etichetta.setObjectName("LblCampo")
        self.lbl_valore = QLabel()
        self.lbl_valore.setObjectName("ValoreParametro")
        intestazione.addWidget(etichetta)
        intestazione.addStretch()
        intestazione.addWidget(self.lbl_valore)
        colonna.addLayout(intestazione)

        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setObjectName("SliderParametro")
        self.slider.setRange(0, len(valori) - 1)
        self.slider.setPageStep(max(1, len(valori) // 10))
        self.slider.setCursor(Qt.CursorShape.PointingHandCursor)
        self.slider.setAccessibleName(titolo)
        self.slider.valueChanged.connect(self._aggiorna_testo)
        colonna.addWidget(self.slider)

        estremi = QHBoxLayout()
        for testo, allineamento in (
            (formatta(valori[0]), Qt.AlignmentFlag.AlignLeft),
            (formatta(valori[-1]), Qt.AlignmentFlag.AlignRight),
        ):
            estremo = QLabel(testo)
            estremo.setObjectName("EstremoParametro")
            estremo.setAlignment(allineamento)
            estremi.addWidget(estremo)
        colonna.addLayout(estremi)

        lbl_aiuto = QLabel(aiuto)
        lbl_aiuto.setObjectName("AiutoParametro")
        lbl_aiuto.setWordWrap(True)
        colonna.addWidget(lbl_aiuto)

    @property
    def valore(self) -> float:
        return self._valori[self.slider.value()]

    def imposta(self, valore: float) -> None:
        self.slider.setValue(_indice_vicino(self._valori, valore))
        self._aggiorna_testo()

    def _aggiorna_testo(self, _indice: int = 0) -> None:
        self.lbl_valore.setText(self._formatta(self.valore))


class DialogPianificazione(ModalDialog):
    """Sceglie i parametri del risolutore per una pianificazione.

    Propone ``iniziali`` (gli ultimi usati per la settimana, oppure i predefiniti) e
    li riporta ai predefiniti della configurazione con «Ripristina predefiniti».
    Dopo ``exec()`` accettato, i parametri scelti sono in :attr:`parametri`.
    """

    def __init__(
        self,
        *,
        configurazione: ConfigurazioneParametri,
        iniziali: ParametriPianificazione,
        nota_iniziali: str,
        settimana: str,
        sovrascrive: bool,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Pianifica settimana",
            f"Sale Operatorie · {settimana} · Previsto",
            section="sale_operatorie",
            extra_styles=("dialog_pianificazione.qss",),
            parent=parent,
        )
        self.resize(_LARGHEZZA, 0)
        self._configurazione = configurazione
        self.parametri: ParametriPianificazione | None = None

        if sovrascrive:
            avviso = QLabel(
                "La settimana ha già un piano: verrà rigenerato e sovrascritto."
            )
            avviso.setObjectName("AvvisoSovrascrittura")
            avviso.setWordWrap(True)
            self.body.addWidget(avviso)

        self.lbl_nota = QLabel(nota_iniziali)
        self.lbl_nota.setObjectName("NotaParametri")
        self.lbl_nota.setWordWrap(True)
        self.body.addWidget(self.lbl_nota)

        self.cursore_tempo = _CursoreParametro(
            "Limite di tempo",
            "Allo scadere il calcolo si ferma e salva la migliore soluzione trovata.",
            configurazione.valori_tempo(),
            testo_tempo,
        )
        self.body.addWidget(self.cursore_tempo)
        self.body.addSpacing(6)
        self.cursore_gap = _CursoreParametro(
            "Gap relativo accettato",
            "Il calcolo si ferma prima se la soluzione è entro questo scarto dall'ottimo: "
            "più è alto, più è veloce ma meno precisa.",
            configurazione.valori_gap_percento(),
            testo_percento,
        )
        self.body.addWidget(self.cursore_gap)

        self.btn_predefiniti = self.make_button("Ripristina predefiniti", "secondary")
        self.btn_predefiniti.setMinimumWidth(210)  # il testo non deve essere tagliato
        self.btn_predefiniti.clicked.connect(self.ripristina_predefiniti)
        annulla = self.make_button("Annulla", "secondary")
        annulla.clicked.connect(self.reject)
        self.btn_avvia = self.make_button(
            "Rigenera piano" if sovrascrive else "Avvia pianificazione", "primary"
        )
        self.btn_avvia.setDefault(True)
        self.btn_avvia.clicked.connect(self._conferma)
        self.add_footer(annulla, self.btn_avvia, leading=self.btn_predefiniti)

        self.cursore_tempo.slider.valueChanged.connect(self._aggiorna_predefiniti)
        self.cursore_gap.slider.valueChanged.connect(self._aggiorna_predefiniti)
        self.cursore_tempo.imposta(iniziali.limite_tempo_secondi)
        self.cursore_gap.imposta(iniziali.gap_relativo * 100)
        self._aggiorna_predefiniti()

    def parametri_scelti(self) -> ParametriPianificazione:
        return ParametriPianificazione(self.cursore_tempo.valore, self.cursore_gap.valore / 100)

    def ripristina_predefiniti(self) -> None:
        predefiniti = self._configurazione.predefiniti()
        self.cursore_tempo.imposta(predefiniti.limite_tempo_secondi)
        self.cursore_gap.imposta(predefiniti.gap_relativo * 100)
        self.lbl_nota.setText("Valori predefiniti dell'applicazione.")

    def _aggiorna_predefiniti(self, _valore: int = 0) -> None:
        predefiniti = self._configurazione.predefiniti()
        scelti = self.parametri_scelti()
        self.btn_predefiniti.setEnabled(not (
            math.isclose(scelti.limite_tempo_secondi, predefiniti.limite_tempo_secondi)
            and math.isclose(scelti.gap_relativo, predefiniti.gap_relativo)
        ))

    def _conferma(self) -> None:
        self.parametri = self.parametri_scelti()
        self.accept()


def chiedi_parametri_pianificazione(parent: QWidget | None, **opzioni) -> ParametriPianificazione | None:
    """Mostra la finestra e restituisce i parametri, oppure ``None`` se si annulla."""
    dialog = DialogPianificazione(parent=parent, **opzioni)
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.parametri
