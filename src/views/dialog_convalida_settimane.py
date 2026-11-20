"""Dialog per convalidare l'Effettivo dello Scadenzario una o più settimane alla volta."""

from __future__ import annotations

import datetime
from collections.abc import Sequence

from PySide6.QtWidgets import QGridLayout, QLabel, QWidget

from src.views.components.modal_dialog import ModalDialog
from src.views.dialog_esporta_pdf import Intervallo, _OpzioneScelta

_LARGHEZZA = 620


class DialogConvalidaSettimane(ModalDialog):
    """Sceglie le settimane da convalidare; quelle già convalidate restano spuntate e bloccate.

    ``settimane`` sono le voci delle settimane del mese (vedi ``intervalli_mese``, senza
    il mese intero) e ``lunedi`` i rispettivi lunedì. Dopo ``exec()`` accettato i lunedì
    scelti sono in :attr:`scelte`.
    """

    def __init__(
        self,
        *,
        riepilogo: str,
        settimane: Sequence[Intervallo],
        lunedi: Sequence[datetime.date],
        convalidate: set[datetime.date],
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(
            "Convalida Effettivo", riepilogo, section="scadenzario",
            extra_styles=("dialog_esporta.qss",), parent=parent,
        )
        self.resize(_LARGHEZZA, 0)
        self._lunedi = list(lunedi)
        self.scelte: list[datetime.date] = []

        etichetta = QLabel("SETTIMANE DA CONVALIDARE")
        etichetta.setObjectName("LblCampo")
        self.body.addWidget(etichetta)
        suggerimento = QLabel(
            "Le settimane convalidate non si possono più modificare e completano le "
            "attività nel Libretto. Con tutte le settimane convalidate il mese è "
            "convalidato."
        )
        suggerimento.setObjectName("LblSuggerimentoEsporta")
        suggerimento.setWordWrap(True)
        self.body.addWidget(suggerimento)

        griglia = QGridLayout()
        griglia.setHorizontalSpacing(10)
        griglia.setVerticalSpacing(10)
        self._opzioni: list[_OpzioneScelta] = []
        riga, colonna = 0, 0
        for settimana, lunedi_settimana in zip(settimane, self._lunedi):
            gia = lunedi_settimana in convalidate
            dettaglio = settimana.dettaglio + (" · già convalidata" if gia else "")
            opzione = _OpzioneScelta(settimana.titolo, dettaglio, casella=True)
            opzione.setChecked(gia)
            opzione.setEnabled(not gia)
            opzione.toggled.connect(self._aggiorna_pulsante)
            self._opzioni.append(opzione)
            if settimana.riga_intera or gia:
                if colonna:
                    riga, colonna = riga + 1, 0
                griglia.addWidget(opzione, riga, 0, 1, 2)
                riga += 1
            else:
                griglia.addWidget(opzione, riga, colonna)
                riga, colonna = (riga, 1) if colonna == 0 else (riga + 1, 0)
        self.body.addLayout(griglia)

        annulla = self.make_button("Annulla", "secondary")
        annulla.clicked.connect(self.reject)
        self.btn_tutte = self.make_button("Seleziona tutte", "secondary")
        self.btn_tutte.clicked.connect(self._seleziona_tutte)
        self.btn_convalida = self.make_button("Convalida", "primary")
        self.btn_convalida.clicked.connect(self._conferma)
        self.add_footer(annulla, self.btn_convalida, leading=self.btn_tutte)
        self._aggiorna_pulsante()

    def _nuove(self) -> list[datetime.date]:
        return [
            lunedi for lunedi, opzione in zip(self._lunedi, self._opzioni)
            if opzione.isEnabled() and opzione.isChecked()
        ]

    def _aggiorna_pulsante(self, *_args) -> None:
        nuove = len(self._nuove())
        self.btn_convalida.setEnabled(nuove > 0)
        self.btn_convalida.setText(
            "Convalida" if nuove == 0
            else "Convalida 1 settimana" if nuove == 1
            else f"Convalida {nuove} settimane"
        )
        self.btn_tutte.setEnabled(
            any(opzione.isEnabled() and not opzione.isChecked() for opzione in self._opzioni)
        )

    def _seleziona_tutte(self) -> None:
        for opzione in self._opzioni:
            if opzione.isEnabled():
                opzione.setChecked(True)

    def _conferma(self) -> None:
        self.scelte = self._nuove()
        if self.scelte:
            self.accept()
