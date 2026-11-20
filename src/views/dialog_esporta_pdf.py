"""Dialog di esportazione PDF: cosa esportare e dove salvarlo, in un solo passaggio.

Dopo l'esportazione :func:`mostra_pdf_creato` conferma dove è il file e lo apre, se
richiesto, con il visualizzatore del sistema.
"""

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
from src.desktop_open import open_in_default_app
from src.error_messages import describe_error
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
    settimane a cavallo di due mesi, che hanno una nota più lunga. Un intervallo
    ``esclusivo`` (il mese intero) non si combina con gli altri quando il dialog
    permette di sceglierne più d'uno.
    """

    titolo: str
    dettaglio: str
    nome_file: str
    riga_intera: bool = False
    esclusivo: bool = False


def intervalli_mese(
    anno: int,
    mese: int,
    settimane: Sequence[Sequence[datetime.date]],
    *,
    nomi_mesi: Sequence[str],
    prefisso: str,
    mese_presente: Callable[[int, int], bool] = lambda _anno, _mese: True,
    nota_settimana: Callable[[Sequence[datetime.date]], str] = lambda _settimana: "",
) -> list[Intervallo]:
    """«Mese intero» e una voce per ciascuna settimana intera di ``month_weeks``.

    La voce ``i`` è la settimana ``i`` del mese (la ``0`` è il mese intero): è la
    numerazione che usa :func:`nome_file_settimane`.

    Una settimana a cavallo di due mesi dice da quale mese prende gli altri giorni
    feriali e, se quel mese non esiste ancora in questa versione (``mese_presente``),
    avvisa che quei giorni usciranno vuoti. ``nota_settimana`` aggiunge un avviso
    per settimana (es. «vuota: Effettivo non ancora creato»). Il nome del file usa
    la data del lunedì, unica anche tra mesi diversi.
    """

    giorni = month_dates(anno, mese)
    voci = [
        Intervallo(
            "Mese intero",
            f"1 – {giorni[-1].day} {nomi_mesi[mese - 1].lower()} {anno}",
            f"{prefisso}-{anno:04d}-{mese:02d}-mese.pdf",
            riga_intera=True,
            esclusivo=True,
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
        nota = nota_settimana(settimana)
        if nota:
            dettaglio += f" · {nota}"
        voci.append(Intervallo(
            f"Settimana {numero}",
            dettaglio,
            f"{prefisso}-settimana-{settimana[0].isoformat()}.pdf",
            riga_intera=bool(altri or nota),
        ))
    return voci


def nome_file_settimane(
    prefisso: str, anno: int, mese: int
) -> Callable[[Sequence[int]], str]:
    """Nome del file per più settimane di :func:`intervalli_mese`, dai loro numeri.

    Es. ``scadenzario-previsto-2026-11-settimane-1-3.pdf``.
    """

    def nome(indici: Sequence[int]) -> str:
        numeri = "-".join(str(indice) for indice in sorted(indici))
        return f"{prefisso}-{anno:04d}-{mese:02d}-settimane-{numeri}.pdf"

    return nome


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
    """``indici``: gli intervalli scelti, in ordine (uno solo se non si combinano)."""

    indici: tuple[int, ...]
    percorso: Path
    vista: str | None = None


class _OpzioneScelta(QPushButton):
    """Scheda selezionabile con titolo, una riga di dettaglio e la spunta quando è scelta.

    Con ``casella`` la spunta sta in una casella a sinistra, visibile anche vuota: dice
    che la scheda si può scegliere insieme ad altre.
    """

    def __init__(
        self,
        titolo_testo: str,
        dettaglio_testo: str,
        parent: QWidget | None = None,
        *,
        casella: bool = False,
    ):
        super().__init__(parent)
        self.setObjectName("OpzioneEsporta")
        self.setCheckable(True)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setFixedHeight(_ALTEZZA_OPZIONE)
        self.setAccessibleName(f"{titolo_testo}, {dettaglio_testo}")

        riga = QHBoxLayout(self)
        riga.setContentsMargins(14 if casella else 16, 6, 14, 6)
        riga.setSpacing(12)
        if casella:
            self._casella = QLabel()
            self._casella.setObjectName("OpzioneCasella")
            self._casella.setFixedSize(22, 22)
            self._casella.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._casella.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            riga.addWidget(self._casella)
            self.toggled.connect(self._aggiorna_casella)
            self._aggiorna_casella(False)
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
        if not casella:
            self.toggled.connect(self._spunta.setVisible)
        self._spunta.setVisible(False)

    def _aggiorna_casella(self, spuntata: bool) -> None:
        self._casella.setText("✓" if spuntata else "")
        self._casella.setProperty("spuntata", spuntata)
        # Il foglio di stile dipende dalla proprietà: va riapplicato.
        self._casella.style().unpolish(self._casella)
        self._casella.style().polish(self._casella)


class DialogEsportaPdf(ModalDialog):
    """Sceglie intervalli, righe (se la sezione ne offre più di un tipo) e file.

    Con ``nome_combinato`` si possono scegliere più intervalli insieme (le settimane),
    tranne quelli ``esclusivo`` (il mese intero), che tolgono gli altri; la funzione
    dà il nome del file per gli indici scelti. Almeno un intervallo resta scelto.

    Il percorso proposto parte sempre dal Desktop; il nome del file segue intervalli e
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
        nome_combinato: Callable[[Sequence[int]], str] | None = None,
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
        self._nome_combinato = nome_combinato
        self.scelta: SceltaEsportazione | None = None
        self._sovrascrittura_confermata: Path | None = None

        # Con un solo periodo possibile non c'è niente da scegliere: il periodo è già
        # nel riepilogo sotto il titolo.
        sezione_periodo = QWidget()
        colonna_periodo = QVBoxLayout(sezione_periodo)
        colonna_periodo.setContentsMargins(0, 0, 0, 0)
        colonna_periodo.setSpacing(12)
        multipla = nome_combinato is not None and sum(
            not intervallo.esclusivo for intervallo in self._intervalli
        ) > 1
        colonna_periodo.addWidget(self._etichetta_campo("Cosa esportare"))
        self._gruppo = QButtonGroup(self)
        # Con la scelta multipla l'esclusione (mese intero contro settimane) e il
        # «sempre almeno uno» li gestisce _periodo_cliccato.
        self._gruppo.setExclusive(not multipla)
        self.lbl_conteggio = QLabel()
        self.lbl_conteggio.setObjectName("LblConteggioEsporta")
        tutti = list(range(len(self._intervalli)))
        if not multipla:
            colonna_periodo.addLayout(self._griglia_opzioni(tutti, casella=False))
        else:
            # Prima il mese intero, poi le settimane sotto un sottotitolo che dice che
            # se ne possono spuntare più d'una, con il conteggio delle spuntate.
            esclusivi = [i for i in tutti if self._intervalli[i].esclusivo]
            combinabili = [i for i in tutti if not self._intervalli[i].esclusivo]
            if esclusivi:
                colonna_periodo.addLayout(self._griglia_opzioni(esclusivi, casella=False))
            intestazione = QVBoxLayout()
            intestazione.setContentsMargins(0, 4, 0, 0)
            intestazione.setSpacing(2)
            riga_titolo = QHBoxLayout()
            sottotitolo = QLabel(
                "Oppure una o più settimane" if esclusivi else "Una o più settimane"
            )
            sottotitolo.setObjectName("LblSottotitoloEsporta")
            riga_titolo.addWidget(sottotitolo)
            riga_titolo.addStretch(1)
            riga_titolo.addWidget(self.lbl_conteggio)
            intestazione.addLayout(riga_titolo)
            suggerimento = QLabel(
                "Spunta tutte quelle da includere: ognuna va su una pagina del PDF."
            )
            suggerimento.setObjectName("LblSuggerimentoEsporta")
            suggerimento.setWordWrap(True)
            intestazione.addWidget(suggerimento)
            colonna_periodo.addLayout(intestazione)
            colonna_periodo.addLayout(self._griglia_opzioni(combinabili, casella=True))
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
        self._aggiorna_conteggio()
        self._ultimo_nome_proposto = self._nome_proposto()
        self.input_percorso.setText(str(cartella_desktop() / self._ultimo_nome_proposto))
        self._gruppo.idClicked.connect(self._periodo_cliccato)
        self._gruppo_viste.idToggled.connect(self._vista_cambiata)

    def _griglia_opzioni(self, indici: Sequence[int], *, casella: bool) -> QGridLayout:
        """Schede degli intervalli ``indici``, due per riga; quelle con ``riga_intera``
        (mese intero, settimane a cavallo di due mesi) occupano una riga da sole."""

        griglia = QGridLayout()
        griglia.setHorizontalSpacing(10)
        griglia.setVerticalSpacing(10)
        riga, colonna = 0, 0
        for indice in indici:
            intervallo = self._intervalli[indice]
            opzione = _OpzioneScelta(intervallo.titolo, intervallo.dettaglio, casella=casella)
            self._gruppo.addButton(opzione, indice)
            if intervallo.riga_intera:
                if colonna:
                    riga, colonna = riga + 1, 0
                griglia.addWidget(opzione, riga, 0, 1, 2)
                riga += 1
            else:
                griglia.addWidget(opzione, riga, colonna)
                riga, colonna = (riga, 1) if colonna == 0 else (riga + 1, 0)
        return griglia

    def _aggiorna_conteggio(self) -> None:
        settimane = sum(
            not self._intervalli[indice].esclusivo for indice in self.indici_scelti()
        )
        self.lbl_conteggio.setText(
            "" if not settimane
            else "1 selezionata" if settimane == 1
            else f"{settimane} selezionate"
        )

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

    def indici_scelti(self) -> tuple[int, ...]:
        """Indici degli intervalli scelti, in ordine."""

        return tuple(
            indice for indice in range(len(self._intervalli))
            if self._gruppo.button(indice).isChecked()
        )

    def _periodo_cliccato(self, indice: int) -> None:
        """Con la scelta multipla: il mese intero toglie le settimane e viceversa; un
        click sull'unica voce scelta la lascia scelta."""

        if not self._gruppo.exclusive():
            pulsante = self._gruppo.button(indice)
            if pulsante.isChecked():
                esclusivo = self._intervalli[indice].esclusivo
                for altro, intervallo in enumerate(self._intervalli):
                    if altro != indice and (esclusivo or intervallo.esclusivo):
                        self._gruppo.button(altro).setChecked(False)
            elif not self.indici_scelti():
                pulsante.setChecked(True)
        self._aggiorna_conteggio()
        self._aggiorna_nome_proposto()

    def _vista_cambiata(self, _indice: int, scelta: bool) -> None:
        if scelta:
            self._aggiorna_nome_proposto()

    def _nome_proposto(self) -> str:
        """Nome del file per gli intervalli e le righe scelti in questo momento."""

        indici = self.indici_scelti()
        if len(indici) > 1 and self._nome_combinato is not None:
            nome = self._nome_combinato(indici)
        else:
            nome = self._intervalli[indici[0]].nome_file
        if self._viste:
            vista = self._viste[self._gruppo_viste.checkedId()]
            nome = self._con_suffisso(nome, vista.suffisso_file)
        return nome

    def _aggiorna_nome_proposto(self) -> None:
        """Propone il nome della nuova scelta, ma solo se c'era un nome proposto da noi:
        un nome scritto a mano resta com'è."""

        nuovo = self._nome_proposto()
        attuale = self._percorso_attuale()
        if nuovo != attuale.name and attuale.name == self._ultimo_nome_proposto:
            self.input_percorso.setText(str(attuale.with_name(nuovo)))
            self._sovrascrittura_confermata = None
        self._ultimo_nome_proposto = nuovo

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
        self.scelta = SceltaEsportazione(self.indici_scelti(), percorso, vista)
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
    nome_combinato: Callable[[Sequence[int]], str] | None = None,
) -> SceltaEsportazione | None:
    """Mostra il dialog e restituisce la scelta, oppure ``None`` se l'utente annulla."""

    dialog = DialogEsportaPdf(
        sezione=sezione, titolo=titolo, riepilogo=riepilogo,
        intervalli=intervalli, predefinito=predefinito,
        viste=viste, vista_predefinita=vista_predefinita, titolo_viste=titolo_viste,
        nome_combinato=nome_combinato, parent=parent,
    )
    if dialog.exec() != QDialog.DialogCode.Accepted:
        return None
    return dialog.scelta


def mostra_pdf_creato(
    parent: QWidget | None, titolo: str, percorso: Path, *, sezione: str
) -> None:
    """Conferma dove è stato salvato il PDF e, se l'utente lo chiede, lo apre.

    Il file si apre con il visualizzatore PDF predefinito del sistema; se non si apre,
    un messaggio d'errore lo dice e ricorda dov'è il file.
    """

    if not messages.ask_confirmation(
        parent,
        titolo,
        f"Calendario esportato in:\n{percorso}",
        section=sezione,
        confirm_text="Apri PDF",
        cancel_text="Chiudi",
    ):
        return
    try:
        open_in_default_app(percorso)
    except OSError as error:
        messages.show_message(
            parent,
            "PDF non aperto",
            f"Impossibile aprire il PDF:\n{describe_error(error)}\n\n"
            f"Il file è in:\n{percorso}",
            section=sezione,
            kind="error",
        )
