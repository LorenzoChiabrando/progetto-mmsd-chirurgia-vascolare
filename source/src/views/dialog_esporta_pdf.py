"""Dialog di esportazione PDF: cosa esportare e dove salvarlo, in un solo passaggio."""

from __future__ import annotations

import datetime
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QStandardPaths, Qt
from PySide6.QtWidgets import (
    QButtonGroup, QDialog, QFileDialog, QGridLayout, QHBoxLayout, QLabel, QLineEdit,
    QPushButton, QVBoxLayout, QWidget,
)

from src.calendar_presentation import month_dates
from src.views.components import messages
from src.views.components.modal_dialog import ModalDialog

_LARGHEZZA = 620
_ALTEZZA_OPZIONE = 58
_FILTRO_PDF = "Documento PDF (*.pdf)"


def cartella_desktop() -> Path:
    """Desktop dell'utente, su Linux come su Windows; la cartella home se non esiste.

    Qt chiede la posizione al sistema: su Linux segue le cartelle utente XDG (per
    esempio «Scrivania» nelle installazioni in italiano), su Windows anche il Desktop
    spostato su OneDrive.
    """

    percorso = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DesktopLocation)
    if percorso and Path(percorso).is_dir():
        return Path(percorso)
    return Path.home()


@dataclass(frozen=True)
class Intervallo:
    """Un'opzione di esportazione: titolo, date mostrate sotto e nome di file proposto.

    ``riga_intera`` la mostra su tutta la larghezza, come il mese intero: serve alle
    settimane a cavallo di due mesi, che hanno una nota più lunga.
    """

    titolo: str
    dettaglio: str
    nome_file: str
    riga_intera: bool = False


def intervalli_mese(
    anno: int,
    mese: int,
    settimane: Sequence[Sequence[datetime.date]],
    *,
    nomi_mesi: Sequence[str],
    prefisso: str,
    mese_presente: Callable[[int, int], bool] = lambda _anno, _mese: True,
) -> list[Intervallo]:
    """«Mese intero» e una voce per ciascuna settimana intera di ``month_weeks``.

    Una settimana a cavallo di due mesi dice da quale mese prende gli altri giorni
    feriali e, se quel mese non esiste ancora in questa versione (``mese_presente``),
    avvisa che quei giorni usciranno vuoti. Il nome del file usa la data del lunedì,
    unica anche tra mesi diversi.
    """

    giorni = month_dates(anno, mese)
    voci = [
        Intervallo(
            "Mese intero",
            f"1 – {giorni[-1].day} {nomi_mesi[mese - 1].lower()} {anno}",
            f"{prefisso}-{anno:04d}-{mese:02d}-mese.pdf",
            riga_intera=True,
        )
    ]
    for numero, settimana in enumerate(settimane, 1):
        altri = sorted({
            (giorno.year, giorno.month) for giorno in settimana
            if giorno.weekday() < 5 and (giorno.year, giorno.month) != (anno, mese)
        })
        dettaglio = f"{settimana[0]:%d/%m} – {settimana[-1]:%d/%m}"
        if altri:
            dettaglio += " · con giorni di " + " e ".join(
                nomi_mesi[m - 1].lower()
                + ("" if mese_presente(a, m) else " (vuoti: mese non ancora creato)")
                for a, m in altri
            )
        voci.append(Intervallo(
            f"Settimana {numero}",
            dettaglio,
            f"{prefisso}-settimana-{settimana[0].isoformat()}.pdf",
            riga_intera=bool(altri),
        ))
    return voci


@dataclass(frozen=True)
class Vista:
    """Come disporre le righe del PDF: ``codice`` torna nella scelta, ``suffisso_file``
    distingue il nome proposto (es. ``-per-specializzando``)."""

    codice: str
    titolo: str
    dettaglio: str
    suffisso_file: str = ""


@dataclass(frozen=True)
class SceltaEsportazione:
    indice: int
    percorso: Path
    vista: str | None = None


class _OpzioneScelta(QPushButton):
    """Scheda selezionabile con titolo, una riga di dettaglio e la spunta quando è scelta."""

    def __init__(self, titolo_testo: str, dettaglio_testo: str, parent: QWidget | None = None):
        super().__init__(parent)
        self.setObjectName("OpzioneEsporta")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(_ALTEZZA_OPZIONE)
        self.setAccessibleName(f"{titolo_testo}, {dettaglio_testo}")

        riga = QHBoxLayout(self)
        riga.setContentsMargins(16, 6, 14, 6)
        testi = QVBoxLayout()
        testi.setSpacing(1)
        titolo = QLabel(titolo_testo)
        titolo.setObjectName("OpzioneTitolo")
        dettaglio = QLabel(dettaglio_testo)
        dettaglio.setObjectName("OpzioneDettaglio")
        for etichetta in (titolo, dettaglio):
            etichetta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            testi.addWidget(etichetta)
        riga.addLayout(testi, 1)
        self._spunta = QLabel("✓")
        self._spunta.setObjectName("OpzioneSpunta")
        self._spunta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        riga.addWidget(self._spunta)
        self.toggled.connect(self._spunta.setVisible)
        self._spunta.setVisible(False)


class DialogEsportaPdf(ModalDialog):
    """Sceglie intervallo, righe (se la sezione ne offre più di un tipo) e file.

    Il percorso proposto parte sempre dal Desktop; il nome del file segue intervallo e
    righe scelti finché l'utente non lo cambia a mano. Dopo ``exec()`` accettato, la
    scelta è in :attr:`scelta`.
    """

    def __init__(
        self,
        *,
        sezione: str,
        titolo: str,
        riepilogo: str,
        intervalli: Sequence[Intervallo],
        predefinito: int = 0,
        viste: Sequence[Vista] = (),
        vista_predefinita: int = 0,
        titolo_viste: str = "Righe del calendario",
        parent: QWidget | None = None,
    ) -> None:
        if not intervalli:
            raise ValueError("serve almeno un intervallo da esportare")
        super().__init__(
            titolo, riepilogo, section=sezione,
            extra_styles=("dialog_esporta.qss",), parent=parent,
        )
        self.resize(_LARGHEZZA, 0)
        self._intervalli = list(intervalli)
        self._viste = list(viste)
        self.scelta: SceltaEsportazione | None = None
        self._sovrascrittura_confermata: Path | None = None

        # Con un solo periodo possibile non c'è niente da scegliere: il periodo è già
        # nel riepilogo sotto il titolo.
        sezione_periodo = QWidget()
        colonna_periodo = QVBoxLayout(sezione_periodo)
        colonna_periodo.setContentsMargins(0, 0, 0, 0)
        colonna_periodo.setSpacing(12)
        colonna_periodo.addWidget(self._etichetta_campo("Cosa esportare"))
        griglia = QGridLayout()
        griglia.setHorizontalSpacing(10)
        griglia.setVerticalSpacing(10)
        self._gruppo = QButtonGroup(self)
        self._gruppo.setExclusive(True)
        # Due opzioni per riga; quelle con ``riga_intera`` (mese intero, settimane a
        # cavallo di due mesi) occupano una riga da sole.
        riga, colonna = 0, 0
        for indice, intervallo in enumerate(self._intervalli):
            opzione = _OpzioneScelta(intervallo.titolo, intervallo.dettaglio)
            self._gruppo.addButton(opzione, indice)
            if intervallo.riga_intera:
                if colonna:
                    riga, colonna = riga + 1, 0
                griglia.addWidget(opzione, riga, 0, 1, 2)
                riga += 1
            else:
                griglia.addWidget(opzione, riga, colonna)
                riga, colonna = (riga, 1) if colonna == 0 else (riga + 1, 0)
        colonna_periodo.addLayout(griglia)
        sezione_periodo.setVisible(len(self._intervalli) > 1)
        self.body.addWidget(sezione_periodo)

        self._gruppo_viste = QButtonGroup(self)
        self._gruppo_viste.setExclusive(True)
        if self._viste:
            if len(self._intervalli) > 1:
                self.body.addSpacing(6)
            self.body.addWidget(self._etichetta_campo(titolo_viste))
            riga_viste = QHBoxLayout()
            riga_viste.setSpacing(10)
            for indice, vista in enumerate(self._viste):
                opzione = _OpzioneScelta(vista.titolo, vista.dettaglio)
                self._gruppo_viste.addButton(opzione, indice)
                riga_viste.addWidget(opzione, 1)
            self.body.addLayout(riga_viste)

        self.body.addSpacing(6)
        self.body.addWidget(self._etichetta_campo("Dove salvare"))
        riga_file = QHBoxLayout()
        riga_file.setSpacing(10)
        self.input_percorso = QLineEdit()
        self.input_percorso.setObjectName("InputDialog")
        self.input_percorso.setFixedHeight(44)
        self.input_percorso.setAccessibleName("Percorso del file PDF")
        riga_file.addWidget(self.input_percorso, 1)
        self.btn_sfoglia = self.make_button("Sfoglia…", "secondary")
        self.btn_sfoglia.setMinimumWidth(110)
        self.btn_sfoglia.clicked.connect(self._sfoglia)
        riga_file.addWidget(self.btn_sfoglia)
        self.body.addLayout(riga_file)
        self.lbl_errore = QLabel()
        self.lbl_errore.setObjectName("LblErroreEsporta")
        self.lbl_errore.setWordWrap(True)
        self.lbl_errore.hide()
        self.body.addWidget(self.lbl_errore)

        annulla = self.make_button("Annulla", "secondary")
        annulla.clicked.connect(self.reject)
        self.btn_esporta = self.make_button("Esporta PDF", "primary")
        self.btn_esporta.setDefault(True)
        self.btn_esporta.clicked.connect(self._conferma)
        self.add_footer(annulla, self.btn_esporta)

        self.input_percorso.textEdited.connect(lambda _testo: self.lbl_errore.hide())
        predefinito = predefinito if 0 <= predefinito < len(self._intervalli) else 0
        self._gruppo.button(predefinito).setChecked(True)
        if self._viste:
            if not 0 <= vista_predefinita < len(self._viste):
                vista_predefinita = 0
            self._gruppo_viste.button(vista_predefinita).setChecked(True)
        self.input_percorso.setText(str(cartella_desktop() / self._nome_proposto()))
        self._gruppo.idToggled.connect(self._scelta_cambiata)
        self._gruppo_viste.idToggled.connect(self._scelta_cambiata)

    @staticmethod
    def _etichetta_campo(testo: str) -> QLabel:
        etichetta = QLabel(testo.upper())
        etichetta.setObjectName("LblCampo")
        return etichetta

    def _percorso_attuale(self) -> Path:
        return Path(self.input_percorso.text().strip()).expanduser()

    @staticmethod
    def _con_suffisso(nome_file: str, suffisso: str) -> str:
        base = Path(nome_file)
        return f"{base.stem}{suffisso}{base.suffix}"

    def _nome_proposto(self) -> str:
        """Nome del file per l'intervallo e le righe scelti in questo momento."""

        nome = self._intervalli[self._gruppo.checkedId()].nome_file
        if self._viste:
            vista = self._viste[self._gruppo_viste.checkedId()]
            nome = self._con_suffisso(nome, vista.suffisso_file)
        return nome

    def _scelta_cambiata(self, _indice: int, scelto: bool) -> None:
        """Propone il nome della nuova scelta, ma solo se c'era un nome proposto da noi."""

        if not scelto:
            return
        attuale = self._percorso_attuale()
        suffissi = [vista.suffisso_file for vista in self._viste] or [""]
        nomi_proposti = {
            self._con_suffisso(intervallo.nome_file, suffisso)
            for intervallo in self._intervalli for suffisso in suffissi
        }
        if attuale.name in nomi_proposti:
            self.input_percorso.setText(str(attuale.with_name(self._nome_proposto())))
            self._sovrascrittura_confermata = None

    def _sfoglia(self) -> None:
        attuale = self._percorso_attuale()
        partenza = attuale if attuale.parent.is_dir() else cartella_desktop() / attuale.name
        percorso, _filtro = QFileDialog.getSaveFileName(
            self, "Scegli dove salvare il PDF", str(partenza), _FILTRO_PDF
        )
        if percorso:
            scelto = self._con_estensione(Path(percorso))
            self.input_percorso.setText(str(scelto))
            self.lbl_errore.hide()
            # La finestra di sistema ha già chiesto se sostituire un file esistente.
            self._sovrascrittura_confermata = scelto

    @staticmethod
    def _con_estensione(percorso: Path) -> Path:
        return percorso if percorso.suffix.casefold() == ".pdf" else percorso.with_suffix(".pdf")

    def _mostra_errore(self, testo: str) -> None:
        self.lbl_errore.setText(testo)
        self.lbl_errore.show()
        self.input_percorso.setFocus()

    def _conferma(self) -> None:
        if not self.input_percorso.text().strip():
            self._mostra_errore("Indica il file in cui salvare il PDF.")
            return
        percorso = self._con_estensione(self._percorso_attuale())
        if not percorso.parent.is_dir():
            self._mostra_errore(
                f"La cartella «{percorso.parent}» non esiste. Scegline un'altra con Sfoglia."
            )
            return
        if percorso.is_dir():
            self._mostra_errore("Il percorso indica una cartella: aggiungi il nome del file.")
            return
        if percorso.exists() and percorso != self._sovrascrittura_confermata:
            if not messages.ask_confirmation(
                self,
                "File già esistente",
                f"«{percorso.name}» esiste già in questa cartella.\nVuoi sostituirlo?",
                section=self.property("sezione"),
                confirm_text="Sostituisci",
            ):
                return
        vista = self._viste[self._gruppo_viste.checkedId()].codice if self._viste else None
        self.scelta = SceltaEsportazione(self._gruppo.checkedId(), percorso, vista)
        self.accept()


def chiedi_esportazione(
    parent: QWidget | None,
    *,
    sezione: str,
    titolo: str,
    riepilogo: str,
    intervalli: Sequence[Intervallo],
    predefinito: int = 0,
    viste: Sequence[Vista] = (),
    vista_predefinita: int = 0,
    titolo_viste: str = "Righe del calendario",
) -> SceltaEsportazione | None:
    """Mostra il dialog e restituisce la scelta, oppure ``None`` se l'utente annulla."""

    dialog = DialogEsportaPdf(
        sezione=sezione, titolo=titolo, riepilogo=riepilogo,
        intervalli=intervalli, predefinito=predefinito,
        viste=viste, vista_predefinita=vista_predefinita, titolo_viste=titolo_viste,
        parent=parent,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.scelta
