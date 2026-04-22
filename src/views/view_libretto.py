import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect,
    QStackedWidget, QTableWidget, QHeaderView,
    QListWidget, QListWidgetItem, QDateEdit, QComboBox,
)
from PySide6.QtCore import Qt, QSize, QDate
from PySide6.QtGui import QColor

_COLORI_LIVELLO = {
    "Junior": ("#dbeafe", "#1d4ed8"),
    "Senior": ("#ede9fe", "#5b21b6"),
}
_COLORI_STATO = {
    "Molinette":  ("#dcfce7", "#15803d"),
    "Altra Sede": ("#fef9c3", "#854d0e"),
    "Storico":    ("#f1f5f9", "#475569"),
}


class ViewLibretto(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget = QStackedWidget()
        main.addWidget(self.stacked_widget)
        self._build_page_anagrafica()
        self._build_page_dettaglio()

    # ─── PAGE 0: ANAGRAFICA ────────────────────────────────────────────────────

    def _build_page_anagrafica(self):
        self.page_anagrafica = QWidget()
        outer = QVBoxLayout(self.page_anagrafica)
        outer.setContentsMargins(40, 40, 40, 40)

        self.card_container = QFrame()
        self.card_container.setObjectName("MainCard")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 22))
        shadow.setOffset(0, 6)
        self.card_container.setGraphicsEffect(shadow)

        card = QVBoxLayout(self.card_container)
        card.setContentsMargins(40, 35, 40, 40)
        card.setSpacing(18)

        # ── Header ──────────────────────────────────────────────────────────
        header_row = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        lbl_titolo = QLabel("Anagrafica Specializzandi")
        lbl_titolo.setObjectName("TitoloSezione")
        lbl_sottotitolo = QLabel("Gestione e consultazione dei libretti formativi")
        lbl_sottotitolo.setObjectName("SottoTitoloSezione")
        titles.addWidget(lbl_titolo)
        titles.addWidget(lbl_sottotitolo)
        header_row.addLayout(titles)
        header_row.addStretch()
        card.addLayout(header_row)

        # ── Barra di ricerca ─────────────────────────────────────────────────
        self.search_container = QFrame()
        self.search_container.setObjectName("SearchContainer")
        self.search_container.setFixedHeight(50)
        sc = QHBoxLayout(self.search_container)
        sc.setContentsMargins(16, 0, 16, 0)
        sc.setSpacing(12)
        lbl_icon = QLabel("🔍")
        lbl_icon.setObjectName("SearchIcon")
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText("Cerca per nome, cognome o matricola...")
        sc.addWidget(lbl_icon)
        sc.addWidget(self.search_bar)
        card.addWidget(self.search_container)

        # ── Chip filtri ───────────────────────────────────────────────────────
        chips_row = QHBoxLayout()
        chips_row.setSpacing(10)
        lbl_filtri = QLabel("Visualizza:")
        lbl_filtri.setObjectName("LblFiltri")
        chips_row.addWidget(lbl_filtri)

        self.chk_attiva_molinette = QPushButton("● Molinette")
        self.chk_attiva_molinette.setObjectName("ChipMolinette")
        self.chk_attiva_molinette.setCheckable(True)
        self.chk_attiva_molinette.setChecked(True)

        self.chk_attiva_altre = QPushButton("● Altra Sede")
        self.chk_attiva_altre.setObjectName("ChipAltraSede")
        self.chk_attiva_altre.setCheckable(True)

        self.chk_storico = QPushButton("● Storico")
        self.chk_storico.setObjectName("ChipStorico")
        self.chk_storico.setCheckable(True)

        for chip in [self.chk_attiva_molinette, self.chk_attiva_altre, self.chk_storico]:
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(34)
            chips_row.addWidget(chip)
        chips_row.addStretch()
        card.addLayout(chips_row)

        # ── Lista + bottoni ───────────────────────────────────────────────────
        body = QHBoxLayout()
        body.setSpacing(24)

        self.lista_risultati = QListWidget()
        self.lista_risultati.setObjectName("ListaRisultati")
        self.lista_risultati.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lista_risultati.setSpacing(5)

        # Deseleziona cliccando su area vuota
        _orig = self.lista_risultati.mousePressEvent
        def _on_click(ev):
            if not self.lista_risultati.itemAt(ev.pos()):
                self.lista_risultati.clearSelection()
            _orig(ev)
        self.lista_risultati.mousePressEvent = _on_click

        body.addWidget(self.lista_risultati, stretch=7)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(14)

        self.btn_apri = QPushButton("Apri Libretto")
        self.btn_apri.setObjectName("BtnApri")
        self.btn_apri.setFixedHeight(56)
        self.btn_apri.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apri.setEnabled(False)

        self.btn_aggiungi = QPushButton("+ Nuovo Specializzando")
        self.btn_aggiungi.setObjectName("BtnAggiungi")
        self.btn_aggiungi.setFixedHeight(56)
        self.btn_aggiungi.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_col.addWidget(self.btn_apri)
        btn_col.addWidget(self.btn_aggiungi)
        btn_col.addStretch()
        body.addLayout(btn_col, stretch=3)
        card.addLayout(body)

        outer.addWidget(self.card_container)
        self.stacked_widget.addWidget(self.page_anagrafica)

    # ─── PAGE 1: DETTAGLIO ────────────────────────────────────────────────────

    def _build_page_dettaglio(self):
        self.page_dettaglio = QWidget()
        layout = QVBoxLayout(self.page_dettaglio)
        layout.setContentsMargins(40, 28, 40, 28)
        layout.setSpacing(18)

        # Nav bar
        nav = QHBoxLayout()
        nav.setSpacing(12)

        self.btn_indietro = QPushButton("← Indietro")
        self.btn_indietro.setObjectName("BtnIndietro")
        self.btn_indietro.setFixedSize(150, 42)
        self.btn_indietro.setCursor(Qt.CursorShape.PointingHandCursor)
        nav.addWidget(self.btn_indietro)
        nav.addStretch()

        # Nome specializzando: cognome grande + nome piccolo
        name_block = QVBoxLayout()
        name_block.setSpacing(1)
        name_block.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_cognome_medico = QLabel("")
        self.lbl_cognome_medico.setObjectName("LblCognomeMedico")
        self.lbl_cognome_medico.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_nome_proprio_medico = QLabel("")
        self.lbl_nome_proprio_medico.setObjectName("LblNomeProprioMedico")
        self.lbl_nome_proprio_medico.setAlignment(Qt.AlignmentFlag.AlignRight)
        name_block.addWidget(self.lbl_cognome_medico)
        name_block.addWidget(self.lbl_nome_proprio_medico)
        nav.addLayout(name_block)

        nav.addSpacing(20)

        self.btn_modifica = QPushButton("✏  Modifica")
        self.btn_modifica.setObjectName("BtnModifica")
        self.btn_modifica.setFixedHeight(42)
        self.btn_modifica.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_elimina = QPushButton("🗑  Elimina")
        self.btn_elimina.setObjectName("BtnElimina")
        self.btn_elimina.setFixedHeight(42)
        self.btn_elimina.setCursor(Qt.CursorShape.PointingHandCursor)

        nav.addWidget(self.btn_modifica)
        nav.addWidget(self.btn_elimina)

        layout.addLayout(nav)

        # Detail card
        card_det = QFrame()
        card_det.setObjectName("CardDettaglio")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 18))
        shadow.setOffset(0, 4)
        card_det.setGraphicsEffect(shadow)

        cd = QVBoxLayout(card_det)
        cd.setContentsMargins(40, 35, 40, 40)
        cd.setSpacing(24)

        # Info boxes row
        info_row = QHBoxLayout()
        info_row.setSpacing(16)
        box_mat, self.val_matricola = self._crea_info_box("Matricola", "-")
        box_liv, self.val_livello   = self._crea_info_box("Livello", "-")
        box_sta, self.val_stato     = self._crea_info_box("Stato", "-")
        box_sco, self.val_score     = self._crea_info_box("Training Score", "–", accent=True)
        for box in [box_mat, box_liv, box_sta, box_sco]:
            info_row.addWidget(box)
        cd.addLayout(info_row)

        # Divider
        sep = QFrame()
        sep.setObjectName("Separatore")
        sep.setFixedHeight(1)
        cd.addWidget(sep)

        # ── Intestazione tabella + contatore ─────────────────────────────────
        tab_header = QHBoxLayout()
        lbl_tab = QLabel("Registro delle Attività Operative")
        lbl_tab.setObjectName("TitoloTabella")
        tab_header.addWidget(lbl_tab)
        tab_header.addStretch()
        self.lbl_risultati_filtro = QLabel("")
        self.lbl_risultati_filtro.setObjectName("LblRisultatiFiltro")
        tab_header.addWidget(self.lbl_risultati_filtro)
        cd.addLayout(tab_header)

        # ── Barra filtri ──────────────────────────────────────────────────────
        filtro_frame = QFrame()
        filtro_frame.setObjectName("FiltroBar")
        filtro_layout = QHBoxLayout(filtro_frame)
        filtro_layout.setContentsMargins(14, 8, 14, 8)
        filtro_layout.setSpacing(10)

        lbl_da = QLabel("Dal")
        lbl_da.setObjectName("LblFiltroData")
        self.filtro_da = QDateEdit()
        self.filtro_da.setObjectName("FiltroDa")
        self.filtro_da.setCalendarPopup(True)
        self.filtro_da.setDisplayFormat("dd/MM/yyyy")
        self.filtro_da.setFixedHeight(34)
        self.filtro_da.setDate(QDate(2020, 1, 1))

        lbl_a = QLabel("al")
        lbl_a.setObjectName("LblFiltroData")
        self.filtro_a = QDateEdit()
        self.filtro_a.setObjectName("FiltroA")
        self.filtro_a.setCalendarPopup(True)
        self.filtro_a.setDisplayFormat("dd/MM/yyyy")
        self.filtro_a.setFixedHeight(34)
        self.filtro_a.setDate(QDate.currentDate())

        lbl_cpx = QLabel("Complessità")
        lbl_cpx.setObjectName("LblFiltroData")
        self.filtro_cpx = QComboBox()
        self.filtro_cpx.setObjectName("FiltroCpx")
        self.filtro_cpx.addItems(["Tutte", "Alta", "Media", "Bassa"])
        self.filtro_cpx.setFixedHeight(34)

        self.btn_azzera_filtri = QPushButton("× Azzera")
        self.btn_azzera_filtri.setObjectName("BtnAzzeraFiltri")
        self.btn_azzera_filtri.setFixedHeight(34)
        self.btn_azzera_filtri.setCursor(Qt.CursorShape.PointingHandCursor)

        filtro_layout.addWidget(lbl_da)
        filtro_layout.addWidget(self.filtro_da)
        filtro_layout.addWidget(lbl_a)
        filtro_layout.addWidget(self.filtro_a)
        filtro_layout.addSpacing(6)
        filtro_layout.addWidget(lbl_cpx)
        filtro_layout.addWidget(self.filtro_cpx)
        filtro_layout.addSpacing(6)
        filtro_layout.addWidget(self.btn_azzera_filtri)
        filtro_layout.addStretch()
        cd.addWidget(filtro_frame)

        # ── Tabella ───────────────────────────────────────────────────────────
        self.tabella_libretto = QTableWidget(0, 5)
        self.tabella_libretto.setObjectName("TabellaLibretto")
        self.tabella_libretto.setHorizontalHeaderLabels(
            ["Data", "Tipo Intervento", "Sede", "Ruolo", "Complessità"]
        )
        self.tabella_libretto.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabella_libretto.setAlternatingRowColors(True)
        self.tabella_libretto.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.tabella_libretto.verticalHeader().setVisible(False)
        self.tabella_libretto.setMinimumHeight(180)
        self.tabella_libretto.setMaximumHeight(420)
        cd.addWidget(self.tabella_libretto)

        layout.addWidget(card_det)
        self.stacked_widget.addWidget(self.page_dettaglio)

    # ─── Factory helpers ──────────────────────────────────────────────────────

    def _crea_info_box(self, etichetta, valore_iniziale, accent=False):
        """Crea un box informativo con etichetta e valore. Restituisce (QFrame, QLabel_valore)."""
        box = QFrame()
        box.setObjectName("InfoBox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(6)
        lbl = QLabel(etichetta.upper())
        lbl.setObjectName("LblInfo")
        val = QLabel(valore_iniziale)
        val.setObjectName("ValInfoScore" if accent else "ValInfo")
        val.setWordWrap(True)
        bl.addWidget(lbl)
        bl.addWidget(val)
        return box, val

    def crea_item_lista(self, cognome, nome, matricola, livello, stato):
        """Restituisce (QListWidgetItem, QWidget) con card arricchita per la lista."""
        widget = QFrame()
        widget.setObjectName("ItemCard")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        row = QHBoxLayout(widget)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(14)

        # Badge livello
        bg_liv, fg_liv = _COLORI_LIVELLO.get(livello, ("#f1f5f9", "#475569"))
        badge_liv = QLabel(livello if livello else "–")
        badge_liv.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_liv.setFixedWidth(66)
        badge_liv.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        badge_liv.setStyleSheet(
            f"background-color:{bg_liv}; color:{fg_liv}; font-weight:bold; "
            f"font-size:11px; padding:3px 8px; border-radius:10px; "
            f"border:1px solid {fg_liv}50;"
        )

        # Testo: nome + matricola
        txt_col = QVBoxLayout()
        txt_col.setSpacing(2)
        lbl_nome = QLabel(f"{cognome} {nome}")
        lbl_nome.setObjectName("ItemNome")
        lbl_nome.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lbl_mat = QLabel(f"Matricola: {matricola}")
        lbl_mat.setObjectName("ItemMatricola")
        lbl_mat.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        txt_col.addWidget(lbl_nome)
        txt_col.addWidget(lbl_mat)

        # Badge stato
        bg_sta, fg_sta = _COLORI_STATO.get(stato, ("#f1f5f9", "#475569"))
        badge_sta = QLabel(stato if stato else "–")
        badge_sta.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_sta.setFixedWidth(90)
        badge_sta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        badge_sta.setStyleSheet(
            f"background-color:{bg_sta}; color:{fg_sta}; font-weight:bold; "
            f"font-size:11px; padding:3px 8px; border-radius:10px; "
            f"border:1px solid {fg_sta}50;"
        )

        row.addWidget(badge_liv)
        row.addLayout(txt_col, stretch=1)
        row.addWidget(badge_sta)

        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 68))
        return item, widget

    def imposta_dettaglio(self, spec):
        """Popola la pagina dettaglio con i dati dello specializzando scelto."""
        cognome = spec.get("cognome", "").upper()
        nome    = spec.get("nome", "")
        livello = spec.get("livello", "N/D")
        stato   = spec.get("stato", "N/D")

        self.lbl_cognome_medico.setText(cognome)
        self.lbl_nome_proprio_medico.setText(nome)
        self.val_matricola.setText(spec.get("matricola", "N/D"))
        self.val_score.setText("TODO")

        # Badge livello
        bg, fg = _COLORI_LIVELLO.get(livello, ("#f1f5f9", "#475569"))
        self.val_livello.setText(livello)
        self.val_livello.setStyleSheet(
            f"background-color:{bg}; color:{fg}; font-size:18px; "
            f"font-weight:bold; padding:10px 16px; border-radius:10px; "
            f"border:1.5px solid {fg}60;"
        )

        # Badge stato
        bg2, fg2 = _COLORI_STATO.get(stato, ("#f1f5f9", "#475569"))
        self.val_stato.setText(stato)
        self.val_stato.setStyleSheet(
            f"background-color:{bg2}; color:{fg2}; font-size:18px; "
            f"font-weight:bold; padding:10px 16px; border-radius:10px; "
            f"border:1.5px solid {fg2}60;"
        )

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "libretto.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.stacked_widget.currentIndex() == 0:
            self.lista_risultati.clearSelection()
