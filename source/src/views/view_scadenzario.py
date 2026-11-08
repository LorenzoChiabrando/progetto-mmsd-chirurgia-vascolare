import os
from src.data_paths import PROJECT_ROOT
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QAbstractItemView, QTableView, QHeaderView, QScroller,
    QStackedWidget, QLabel, QFrame,
)
from PySide6.QtCore import Qt

from src.views.components.calendar_toolbar import (
    BarraStrumenti, SceltaSegmentata, StatoPeriodo, etichetta_info, pulsante_esporta_pdf,
    riga_periodo, segmentato,
)
from src.views.components.colored_header_view import ColoredHeaderView
from src.views.components.modal_dialog import register_icon_path
from src.views.components.mode_card import CardModalita
from src.views.components.section_header import BandaSezione, pagina_scorrevole
from src.calendar_presentation import ROLE_HEADER_COLORS, row_display_label
from src.views.models.activity_table_model import ROW_KEYS, ActivityTableModel
from src.views.models.resident_table_model import ResidentTableModel


_LARGHEZZA_COLONNA_TOTALE = 72
_LARGHEZZA_GIORNO_SPECIALIZZANDI = 48
# Altezza minima delle righe: la tabella è alta quanto tutte le righe e a scorrere è
# la pagina intera, non il calendario.
_ALTEZZA_RIGA_ATTIVITA = 62
_ALTEZZA_RIGA_SPECIALIZZANDI = 26

# Titolo e significato di ogni stato del mese, mostrati nella fascia sotto il titolo.
_TESTI_STATO = {
    "BOZZA": ("Mese in bozza", "non ancora convalidato: si può ancora modificare"),
    "CONVALIDATO": ("Mese convalidato", "definitivo, in sola lettura"),
    "ASSENTE": ("Effettivo non ancora creato", ""),
}

# Codice, titolo, descrizione (card e banda) e icona SVG della card.
_MODALITA = (
    ("STORICO", "Storico",
     "Consulta e verifica i turni\nconsolidati dei mesi precedenti",
     "modalita-storico.svg"),
    ("CORRENTE", "Mese Corrente",
     "Visualizza e aggiorna i turni\noperativi del mese in corso",
     "modalita-corrente.svg"),
    ("PIANIFICAZIONE", "Pianificazione",
     "Bozza e pianifica i turni\nper i mesi futuri",
     "modalita-pianificazione.svg"),
)

_LEGENDA_GUARDIA = (
    ("118", "Emergenza territoriale", "#991b1b", "#fee2e2"),
    ("PI", "Pronto Intervento", "#9a3412", "#ffedd5"),
    ("L", "Liscia (routinaria)", "#14532d", "#dcfce7"),
)


class ViewScadenzario(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._compact = False

        self.row_labels = list(ROW_KEYS)

        self.setup_ui()
        self.load_styles()
        self._adatta_altezza_tabelle()  # dopo gli stili: l'intestazione ha la sua altezza vera

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Fuori dai margini della pagina calendario, così occupa tutta la larghezza.
        self.banda = BandaSezione(
            "Scadenzario Mensile",
            [(codice, titolo, descrizione.replace("\n", " "))
             for codice, titolo, descrizione, _icona in _MODALITA],
        )
        self.btn_indietro = self.banda.btn_indietro

        self.stacked_widget = QStackedWidget()
        self._build_page_selezione()  # indice 0: le card
        self._build_page_calendario()
        # Indice 1: banda e calendario, che scorrono insieme; le card restano fisse.
        self.scroll_pagina = pagina_scorrevole(self.banda, self.page_calendario)
        self.stacked_widget.addWidget(self.scroll_pagina)
        self.stacked_widget.currentChanged.connect(
            lambda _indice: self.scroll_pagina.verticalScrollBar().setValue(0)
        )
        main_layout.addWidget(self.stacked_widget)

    def _build_page_selezione(self):
        self.page_selezione = QWidget()
        layout = QVBoxLayout(self.page_selezione)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(0)
        layout.setContentsMargins(50, 60, 50, 60)

        header = QVBoxLayout()
        header.setSpacing(10)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        titolo = QLabel("Scadenzario Chirurgico")
        titolo.setObjectName("TitoloSelezione")
        titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(titolo)

        accent_row = QHBoxLayout()
        accent_row.setAlignment(Qt.AlignmentFlag.AlignCenter)
        accent_bar = QFrame()
        accent_bar.setObjectName("AccentBarSelezione")
        accent_bar.setFixedSize(72, 5)
        accent_row.addWidget(accent_bar)
        header.addLayout(accent_row)

        header.addSpacing(6)

        sottotitolo = QLabel("Seleziona la modalità di accesso ai turni mensili")
        sottotitolo.setObjectName("SottoTitoloSelezione")
        sottotitolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(sottotitolo)

        layout.addLayout(header)
        layout.addSpacing(52)

        cards_layout = QHBoxLayout()
        cards_layout.setSpacing(40)
        cards_layout.setAlignment(Qt.AlignmentFlag.AlignCenter)

        card = {
            codice: CardModalita(codice, titolo, descrizione, icona)
            for codice, titolo, descrizione, icona in _MODALITA
        }
        self.btn_storico = card["STORICO"]
        self.btn_corrente = card["CORRENTE"]
        self.btn_pianificazione = card["PIANIFICAZIONE"]

        cards_layout.addWidget(self.btn_storico)
        cards_layout.addWidget(self.btn_corrente)
        cards_layout.addWidget(self.btn_pianificazione)
        layout.addLayout(cards_layout)

        self.stacked_widget.addWidget(self.page_selezione)

    def _build_page_calendario(self):
        self.page_calendario = QWidget()
        layout = QVBoxLayout(self.page_calendario)
        layout.setContentsMargins(30, 12, 30, 24)
        layout.setSpacing(10)

        self.btn_prev = QPushButton("‹")
        self.btn_prev.setObjectName("btnNav")
        self.btn_prev.setFixedSize(46, 46)
        self.btn_prev.setCursor(Qt.CursorShape.PointingHandCursor)
        sp = self.btn_prev.sizePolicy()
        sp.setRetainSizeWhenHidden(True)
        self.btn_prev.setSizePolicy(sp)

        self.btn_mese_anno = QPushButton()
        self.btn_mese_anno.setObjectName("btnMeseAnno")
        self.btn_mese_anno.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_next = QPushButton("›")
        self.btn_next.setObjectName("btnNav")
        self.btn_next.setFixedSize(46, 46)
        self.btn_next.setCursor(Qt.CursorShape.PointingHandCursor)
        sp2 = self.btn_next.sizePolicy()
        sp2.setRetainSizeWhenHidden(True)
        self.btn_next.setSizePolicy(sp2)

        layout.addLayout(riga_periodo(self.btn_prev, self.btn_mese_anno, self.btn_next))

        # Lo stato ha una fascia tutta sua: si deve capire subito se si guarda una bozza.
        self.stato_periodo = StatoPeriodo(_TESTI_STATO)
        self.lbl_versione_info = self.stato_periodo.lbl_dettaglio  # messaggi del controller
        layout.addWidget(self.stato_periodo)

        barra = self.barra_filtri = BarraStrumenti()

        # Pulsanti e non menu a tendina: la versione su cui si lavora deve vedersi subito.
        self.scelta_versione = SceltaSegmentata()
        self.scelta_versione.setProperty("evidenza", True)
        self.scelta_versione.addItem("Previsto", "previsto")
        self.scelta_versione.addItem("Effettivo", "effettivo")
        self.scelta_versione.setAccessibleName("Versione dello scadenzario")
        barra.aggiungi_gruppo("Versione", self.scelta_versione)

        self.btn_per_attivita = QPushButton("Per attività")
        self.btn_per_specializzando = QPushButton("Per specializzando")
        barra.aggiungi_gruppo(
            "Righe", segmentato(self.btn_per_attivita, self.btn_per_specializzando)
        )
        self.btn_per_attivita.setChecked(True)

        self.btn_vista_dettaglio = QPushButton("Dettaglio")
        self.btn_vista_mese = QPushButton("Intero mese")
        barra.aggiungi_gruppo(
            "Visualizzazione", segmentato(self.btn_vista_dettaglio, self.btn_vista_mese)
        )
        self.btn_vista_dettaglio.setChecked(True)

        self.btn_esporta_pdf = pulsante_esporta_pdf("#4338ca")
        barra.aggiungi_azione(self.btn_esporta_pdf)

        self.lbl_dettaglio_cella = etichetta_info(
            "Nella vista mensile fai click sulle iniziali per visualizzare il nome completo."
        )
        barra.aggiungi_info(self.lbl_dettaglio_cella, 1)
        legenda = QLabel("Guardia:")
        legenda.setObjectName("LblGruppoBarra")
        barra.aggiungi_info(legenda)
        for codice, testo, colore, bg in _LEGENDA_GUARDIA:
            chip = QLabel(codice)
            chip.setObjectName("LegendaGuardia")
            chip.setToolTip(testo)
            chip.setStyleSheet(
                f"color: {colore}; font-weight: bold; font-size: 11px; "
                f"background-color: {bg}; border: 1px solid {colore}; "
                f"border-radius: 5px; padding: 2px 8px;"
            )
            barra.aggiungi_info(chip)
        layout.addWidget(barra)

        self.modello_attivita = ActivityTableModel(self)
        self.tabella = QTableView()
        self.tabella.setModel(self.modello_attivita)
        self.tabella.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        # Nelle colonne strette dell'Intero mese le sigle restano leggibili invece di "…".
        self.tabella.setTextElideMode(Qt.TextElideMode.ElideNone)

        self.tabella.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tabella.horizontalHeader().setDefaultSectionSize(150)
        self.tabella.horizontalHeader().setSectionsClickable(False)
        self.tabella.horizontalHeader().setHighlightSections(False)

        self.tabella.setCornerButtonEnabled(False)
        self.tabella.setWordWrap(True)
        self.tabella.setAlternatingRowColors(False)

        QScroller.grabGesture(
            self.tabella.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )
        self.tabella.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.tabella.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)

        color_map = {
            idx: ROLE_HEADER_COLORS.get(label, "#f8fafc")
            for idx, label in enumerate(self.row_labels)
        }
        v_header = ColoredHeaderView(Qt.Orientation.Vertical, color_map, self.tabella)
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v_header.setMinimumSectionSize(_ALTEZZA_RIGA_ATTIVITA)
        v_header.setSectionsClickable(False)
        v_header.setHighlightSections(False)
        self.tabella.setVerticalHeader(v_header)

        self.modello_specializzandi = ResidentTableModel(self)
        self.tabella_specializzandi = QTableView()
        self.tabella_specializzandi.setModel(self.modello_specializzandi)
        self.tabella_specializzandi.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tabella_specializzandi.setSelectionMode(QAbstractItemView.SelectionMode.NoSelection)
        self.tabella_specializzandi.setCornerButtonEnabled(False)
        header_spec = self.tabella_specializzandi.horizontalHeader()
        header_spec.setMinimumSectionSize(18)
        header_spec.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        header_spec.setSectionsClickable(False)
        self.tabella_specializzandi.setTextElideMode(Qt.TextElideMode.ElideNone)
        righe_spec = self.tabella_specializzandi.verticalHeader()
        righe_spec.setSectionsClickable(False)
        righe_spec.setMinimumSectionSize(_ALTEZZA_RIGA_SPECIALIZZANDI)
        righe_spec.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabella_specializzandi.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        QScroller.grabGesture(
            self.tabella_specializzandi.viewport(),
            QScroller.ScrollerGestureType.LeftMouseButtonGesture,
        )
        self.modello_specializzandi.modelReset.connect(self._applica_colonne_specializzandi)
        self.modello_specializzandi.modelReset.connect(self._adatta_altezza_tabelle)
        self.modello_attivita.modelReset.connect(self._adatta_altezza_tabelle)

        self.stack_tabelle = QStackedWidget()
        self.stack_tabelle.addWidget(self.tabella)
        self.stack_tabelle.addWidget(self.tabella_specializzandi)
        layout.addWidget(self.stack_tabelle, 1)

        # Le azioni che cambiano i dati stanno in fondo, come in Sale Operatorie.
        self.btn_crea_effettivo = QPushButton("CREA EFFETTIVO DAL PREVISTO CONVALIDATO")
        self.btn_crea_effettivo.setObjectName("BtnConvalida")
        self.btn_crea_effettivo.setVisible(False)

        self.btn_convalida = QPushButton("CONVALIDA DEFINITIVAMENTE IL MESE")
        self.btn_convalida.setObjectName("BtnConvalida")

        azioni = QHBoxLayout()
        azioni.setSpacing(12)
        for pulsante in (self.btn_crea_effettivo, self.btn_convalida):
            pulsante.setFixedHeight(60)
            pulsante.setCursor(Qt.CursorShape.PointingHandCursor)
            azioni.addWidget(pulsante, 1)
        layout.addLayout(azioni)


    def _applica_colonne_specializzandi(self) -> None:
        """Totale sempre largo; i giorni sono scorrevoli in Dettaglio e tutti visibili nell'Intero mese."""

        header = self.tabella_specializzandi.horizontalHeader()
        if self._compact:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tabella_specializzandi.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAlwaysOff
            )
        else:
            header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            header.setDefaultSectionSize(_LARGHEZZA_GIORNO_SPECIALIZZANDI)
            for column in range(self.modello_specializzandi.columnCount()):
                header.resizeSection(column, _LARGHEZZA_GIORNO_SPECIALIZZANDI)
            self.tabella_specializzandi.setHorizontalScrollBarPolicy(
                Qt.ScrollBarPolicy.ScrollBarAsNeeded
            )
        if self.modello_specializzandi.columnCount():
            totale = self.modello_specializzandi.total_column()
            header.setSectionResizeMode(totale, QHeaderView.ResizeMode.Fixed)
            header.resizeSection(totale, _LARGHEZZA_COLONNA_TOTALE)

    def _adatta_altezza_tabelle(self) -> None:
        """La tabella visibile è alta almeno quanto tutte le sue righe.

        Così il calendario non ha una barra di scorrimento verticale propria: se lo
        schermo è basso scorre la pagina intera. Quella nascosta non impone altezze,
        altrimenti le poche righe per specializzando verrebbero stirate.
        """
        for tabella, altezza_riga in (
            (self.tabella, _ALTEZZA_RIGA_ATTIVITA),
            (self.tabella_specializzandi, _ALTEZZA_RIGA_SPECIALIZZANDI),
        ):
            if self.stack_tabelle.currentWidget() is not tabella:
                tabella.setMinimumHeight(0)
                continue
            altezza = (
                tabella.horizontalHeader().sizeHint().height()
                + tabella.model().rowCount() * altezza_riga
                + 2 * tabella.frameWidth()
            )
            if tabella.horizontalScrollBarPolicy() != Qt.ScrollBarPolicy.ScrollBarAlwaysOff:
                altezza += tabella.horizontalScrollBar().sizeHint().height()
            tabella.setMinimumHeight(altezza)

    def mostra_vista_specializzandi(self, visibile: bool) -> None:
        """Alterna la vista per attività e quella per specializzando (sola consultazione)."""

        self.stack_tabelle.setCurrentWidget(
            self.tabella_specializzandi if visibile else self.tabella
        )
        self.btn_per_specializzando.setChecked(visibile)
        self.btn_per_attivita.setChecked(not visibile)
        self._adatta_altezza_tabelle()

    def set_compact_mode(self, compact: bool) -> None:
        self._compact = compact
        self._applica_colonne_specializzandi()
        self.tabella.setProperty("compact", compact)
        self.tabella.style().unpolish(self.tabella)
        self.tabella.style().polish(self.tabella)
        self.btn_vista_mese.setChecked(compact)
        self.btn_vista_dettaglio.setChecked(not compact)
        self.modello_attivita.set_compact(compact)
        header = self.tabella.horizontalHeader()
        if compact:
            header.setMinimumSectionSize(20)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tabella.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        else:
            header.setMinimumSectionSize(60)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
            header.setDefaultSectionSize(150)
            for column in range(self.modello_attivita.columnCount()):
                header.resizeSection(column, 150)
            self.tabella.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.tabella.viewport().update()
        header.viewport().update()
        self._adatta_altezza_tabelle()

    def mostra_dettaglio_assegnazione(
        self,
        giorno: str,
        riga: str,
        nome_completo: str,
        versione: str = "previsto",
    ) -> None:
        self.lbl_dettaglio_cella.setText(
            f"{versione.capitalize()} · {giorno} · {row_display_label(riga)}: "
            f"{nome_completo or '—'}"
        )

    def aggiorna_badge_modalita(self, modalita, stato, versione="previsto"):
        """Aggiorna la banda della modalità e la fascia dello stato del mese.

        La versione si legge nei pulsanti Versione del pannello dei filtri.
        """
        self.banda.imposta_modalita(modalita)
        self.stato_periodo.imposta_stato(stato)
        # In Pianificazione esiste solo il Previsto: la scelta della versione non compare.
        self.barra_filtri.imposta_gruppo_visibile(
            self.scelta_versione, modalita != "PIANIFICAZIONE"
        )

    def load_styles(self):
        style_path = os.path.join(PROJECT_ROOT, "asset", "styles", "scadenzario.qss")
        register_icon_path()  # la freccia dei menu usa url(icons:...)
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "tabella"):
            self.tabella.viewport().update()
            self.tabella.horizontalHeader().viewport().update()
