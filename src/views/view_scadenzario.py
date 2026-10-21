import os
from src.data_paths import PROJECT_ROOT
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QComboBox,
    QAbstractItemView, QTableView, QHeaderView, QScroller,
    QStackedWidget, QLabel, QSizePolicy, QGraphicsDropShadowEffect, QFrame,
    QSpacerItem
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor

from src.views.components.colored_header_view import ColoredHeaderView
from src.views.components.modal_dialog import register_icon_path
from src.calendar_presentation import ROLE_HEADER_COLORS, row_display_label
from src.views.models.activity_table_model import ROW_KEYS, ActivityTableModel
from src.views.models.resident_table_model import ResidentTableModel


_LARGHEZZA_COLONNA_TOTALE = 72
_LARGHEZZA_GIORNO_SPECIALIZZANDI = 48

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

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)

        self.stacked_widget = QStackedWidget()
        main_layout.addWidget(self.stacked_widget)

        self._build_page_selezione()
        self._build_page_calendario()

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

        self.btn_storico = self._crea_card(
            "Storico",
            "Consulta e verifica i turni\nconsolidati dei mesi precedenti",
            "asset/images/scadenzario/icona_storico.png",
            "CardStorico",
        )
        self.btn_corrente = self._crea_card(
            "Mese Corrente",
            "Visualizza e aggiorna i turni\noperativi del mese in corso",
            "asset/images/scadenzario/icona_corrente.png",
            "CardCorrente",
        )
        self.btn_pianificazione = self._crea_card(
            "Pianificazione",
            "Bozza e pianifica i turni\nper i mesi futuri",
            "asset/images/scadenzario/icona_pianificazione.png",
            "CardPianificazione",
        )

        cards_layout.addWidget(self.btn_storico)
        cards_layout.addWidget(self.btn_corrente)
        cards_layout.addWidget(self.btn_pianificazione)
        layout.addLayout(cards_layout)

        self.stacked_widget.addWidget(self.page_selezione)

    def _build_page_calendario(self):
        self.page_calendario = QWidget()
        layout = QVBoxLayout(self.page_calendario)
        layout.setContentsMargins(30, 16, 30, 24)
        layout.setSpacing(10)

        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 6)

        self.btn_indietro = QPushButton("← Indietro")
        self.btn_indietro.setObjectName("BtnIndietroScadenzario")
        self.btn_indietro.setFixedSize(150, 40)
        self.btn_indietro.setCursor(Qt.CursorShape.PointingHandCursor)

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

        self.lbl_modalita = QLabel("")
        self.lbl_modalita.setObjectName("LblModalita")
        self.lbl_modalita.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.lbl_stato = QLabel("")
        self.lbl_stato.setObjectName("LblStato")
        self.lbl_stato.setAlignment(Qt.AlignmentFlag.AlignCenter)

        badge_row = QHBoxLayout()
        badge_row.setSpacing(8)
        badge_row.addWidget(self.lbl_modalita)
        badge_row.addWidget(self.lbl_stato)

        nav.addWidget(self.btn_indietro)
        nav.addStretch()
        nav.addWidget(self.btn_prev)
        nav.addWidget(self.btn_mese_anno)
        nav.addWidget(self.btn_next)
        nav.addStretch()
        nav.addLayout(badge_row)
        layout.addLayout(nav)

        version_row = QHBoxLayout()
        version_row.setSpacing(12)
        version_label = QLabel("Calendario:")
        version_label.setObjectName("LblCalendarTools")
        version_row.addWidget(version_label)
        self.combo_versione = QComboBox()
        self.combo_versione.setObjectName("ComboVersioneScadenzario")
        self.combo_versione.addItem("Previsto", "previsto")
        self.combo_versione.addItem("Effettivo", "effettivo")
        self.combo_versione.setAccessibleName("Versione dello scadenzario")
        self.combo_versione.setMinimumWidth(150)
        version_row.addWidget(self.combo_versione)
        self.lbl_versione_info = QLabel("")
        self.lbl_versione_info.setObjectName("LblCalendarTools")
        self.lbl_versione_info.setWordWrap(True)
        version_row.addWidget(self.lbl_versione_info, 1)
        self.btn_crea_effettivo = QPushButton("Crea Effettivo dal Previsto")
        self.btn_crea_effettivo.setObjectName("BtnCalendarTool")
        self.btn_crea_effettivo.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_crea_effettivo.setVisible(False)
        version_row.addWidget(self.btn_crea_effettivo)
        layout.addLayout(version_row)

        tools = QHBoxLayout()
        tools.setSpacing(8)

        self.btn_vista_dettaglio = QPushButton("Dettaglio")
        self.btn_vista_dettaglio.setObjectName("BtnCalendarTool")
        self.btn_vista_dettaglio.setCheckable(True)
        self.btn_vista_dettaglio.setChecked(True)
        self.btn_vista_dettaglio.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_vista_mese = QPushButton("Intero mese")
        self.btn_vista_mese.setObjectName("BtnCalendarTool")
        self.btn_vista_mese.setCheckable(True)
        self.btn_vista_mese.setCursor(Qt.CursorShape.PointingHandCursor)

        self.lbl_dettaglio_cella = QLabel(
            "Nella vista mensile fai click sulle iniziali per visualizzare il nome completo."
        )
        self.lbl_dettaglio_cella.setObjectName("LblCellDetail")
        # Il suggerimento si accorcia quando lo spazio manca, invece di allargare la finestra.
        self.lbl_dettaglio_cella.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred
        )

        self.btn_esporta_pdf = QPushButton("Esporta PDF")
        self.btn_esporta_pdf.setObjectName("BtnCalendarExport")
        self.btn_esporta_pdf.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_per_attivita = QPushButton("Per attività")
        self.btn_per_attivita.setObjectName("BtnCalendarTool")
        self.btn_per_attivita.setCheckable(True)
        self.btn_per_attivita.setChecked(True)
        self.btn_per_attivita.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_per_specializzando = QPushButton("Per specializzando")
        self.btn_per_specializzando.setObjectName("BtnCalendarTool")
        self.btn_per_specializzando.setCheckable(True)
        self.btn_per_specializzando.setCursor(Qt.CursorShape.PointingHandCursor)

        tools.addWidget(self.btn_per_attivita)
        tools.addWidget(self.btn_per_specializzando)
        tools.addSpacing(12)
        tools.addWidget(self.btn_vista_dettaglio)
        tools.addWidget(self.btn_vista_mese)
        tools.addWidget(self.lbl_dettaglio_cella, 1)
        for codice, testo, colore, bg in _LEGENDA_GUARDIA:
            chip = QLabel(codice)
            chip.setObjectName("LegendaGuardia")
            chip.setToolTip(testo)
            chip.setStyleSheet(
                f"color: {colore}; font-weight: bold; font-size: 11px; "
                f"background-color: {bg}; border: 1px solid {colore}; "
                f"border-radius: 5px; padding: 2px 8px;"
            )
            tools.addWidget(chip)
        tools.addSpacing(8)
        tools.addWidget(self.btn_esporta_pdf)
        layout.addLayout(tools)

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
        v_header.setMinimumSectionSize(62)
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
        righe_spec.setMinimumSectionSize(26)
        righe_spec.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabella_specializzandi.setHorizontalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel
        )
        QScroller.grabGesture(
            self.tabella_specializzandi.viewport(),
            QScroller.ScrollerGestureType.LeftMouseButtonGesture,
        )
        self.modello_specializzandi.modelReset.connect(self._applica_colonne_specializzandi)

        self.stack_tabelle = QStackedWidget()
        self.stack_tabelle.addWidget(self.tabella)
        self.stack_tabelle.addWidget(self.tabella_specializzandi)
        layout.addWidget(self.stack_tabelle, 1)

        self.btn_convalida = QPushButton("CONVALIDA DEFINITIVAMENTE IL MESE")
        self.btn_convalida.setObjectName("BtnConvalida")
        self.btn_convalida.setFixedHeight(60)
        self.btn_convalida.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.btn_convalida)

        self.stacked_widget.addWidget(self.page_calendario)

    def _crea_card(self, titolo, descrizione, icon_path, object_name):
        icon_path = str(PROJECT_ROOT / icon_path)
        btn = QPushButton()
        btn.setObjectName(object_name)
        btn.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        btn.setMinimumSize(240, 290)
        btn.setMaximumSize(380, 360)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)

        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(30)
        shadow.setColor(QColor(0, 0, 0, 25))
        shadow.setOffset(0, 8)
        btn.setGraphicsEffect(shadow)

        inner = QVBoxLayout(btn)
        inner.setAlignment(Qt.AlignmentFlag.AlignCenter)
        inner.setContentsMargins(28, 32, 28, 28)
        inner.setSpacing(10)

        lbl_icona = QLabel()
        lbl_icona.setAlignment(Qt.AlignmentFlag.AlignCenter)
        if os.path.exists(icon_path):
            px = QPixmap(icon_path).scaled(
                80, 80, Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation
            )
            lbl_icona.setPixmap(px)

        lbl_titolo = QLabel(titolo)
        lbl_titolo.setObjectName("CardTitolo")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_desc = QLabel(descrizione)
        lbl_desc.setObjectName("CardDescrizione")
        lbl_desc.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_desc.setWordWrap(True)

        sep = QFrame()
        sep.setObjectName("CardSeparatore")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)

        lbl_azione = QLabel("Accedi  →")
        lbl_azione.setObjectName("CardAzione")
        lbl_azione.setAlignment(Qt.AlignmentFlag.AlignCenter)

        inner.addStretch()
        inner.addWidget(lbl_icona)
        inner.addSpacing(4)
        inner.addWidget(lbl_titolo)
        inner.addWidget(lbl_desc)
        inner.addStretch()
        inner.addWidget(sep)
        inner.addSpacing(4)
        inner.addWidget(lbl_azione)

        return btn

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

    def mostra_vista_specializzandi(self, visibile: bool) -> None:
        """Alterna la vista per attività e quella per specializzando (sola consultazione)."""

        self.stack_tabelle.setCurrentWidget(
            self.tabella_specializzandi if visibile else self.tabella
        )
        self.btn_per_specializzando.setChecked(visibile)
        self.btn_per_attivita.setChecked(not visibile)

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
        """Mostra modalità, versione e stato anche per gli effettivi storici."""
        colori_modalita = {
            "STORICO":        ("#334155", "#e2e8f0"),
            "CORRENTE":       ("#14532d", "#dcfce7"),
            "PIANIFICAZIONE": ("#1e3a8a", "#dbeafe"),
        }
        colori_stato = {
            "BOZZA":       ("#92400e", "#fef3c7"),
            "CONVALIDATO": ("#14532d", "#dcfce7"),
        }

        fg_m, bg_m = colori_modalita.get(modalita, ("#334155", "#e2e8f0"))
        self.lbl_modalita.setText(f"  {modalita or 'CALENDARIO'} · {versione.upper()}  ")
        self.lbl_modalita.setStyleSheet(
            f"color: {fg_m}; background-color: {bg_m}; font-weight: bold; "
            f"font-size: 12px; border-radius: 8px; padding: 5px 10px;"
        )

        self.lbl_stato.setVisible(True)
        fg_s, bg_s = colori_stato.get(stato, ("#334155", "#e2e8f0"))
        self.lbl_stato.setText(f"  {stato}  ")
        self.lbl_stato.setStyleSheet(
            f"color: {fg_s}; background-color: {bg_s}; font-weight: bold; "
            f"font-size: 12px; border-radius: 8px; padding: 5px 10px;"
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
