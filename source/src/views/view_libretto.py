import os
from datetime import date as _date
from src.app_paths import get_asset_dir

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect,
    QStackedWidget, QAbstractItemView,
    QListWidget, QListWidgetItem, QScrollArea, QGridLayout, QComboBox,
)
from PySide6.QtCore import Qt, QSize
from PySide6.QtGui import QColor, QPalette

_COLORI_LIVELLO = {
    "Junior": ("#dbeafe", "#1d4ed8"),
    "Senior": ("#ede9fe", "#5b21b6"),
}
_COLORI_STATO = {
    "Molinette":  ("#dcfce7", "#15803d"),
    "Altra Sede": ("#fef9c3", "#854d0e"),
    "Storico":    ("#f1f5f9", "#475569"),
}
_GIORNI_ITA = ["Lunedì", "Martedì", "Mercoledì", "Giovedì",
               "Venerdì", "Sabato", "Domenica"]
_MESI_ITA = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
             "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
_DISPLAY_RUOLO = {
    "OR I":  "Sala Op. I",
    "OR II": "Sala Op. II",
}
_TAG_COLORS = {
    "Sala Op. I":   ("#dbeafe", "#1d4ed8"),
    "Sala Op. II":  ("#dbeafe", "#2563eb"),
    "Giro Visite":  ("#d1fae5", "#065f46"),
    "Reparto I":    ("#ffedd5", "#c2410c"),
    "Reparto II":   ("#ffedd5", "#c2410c"),
    "Reparto":      ("#ffedd5", "#c2410c"),
    "Day Hospital": ("#ede9fe", "#6d28d9"),
    "Day Surgery":  ("#fce7f3", "#9d174d"),
}
_TAG_DEFAULT = ("#f1f5f9", "#475569")


def _fmt_data(data_str: str) -> str:
    try:
        d = _date.fromisoformat(data_str)
        return f"{_GIORNI_ITA[d.weekday()]} {d.day} {_MESI_ITA[d.month - 1]} {d.year}"
    except ValueError:
        return data_str


def _day_summary(attivita_list: list) -> str:
    seen = []
    for att in attivita_list:
        ruolo = att.get("ruolo", "")
        display = _DISPLAY_RUOLO.get(ruolo, ruolo) if ruolo else att.get("sede", "")
        if display and display not in seen:
            seen.append(display)
    return "  ·  ".join(seen) if seen else "–"


def _day_activity_tags(attivita_list: list) -> list[str]:
    seen = []
    for att in attivita_list:
        ruolo = att.get("ruolo", "")
        display = _DISPLAY_RUOLO.get(ruolo, ruolo) if ruolo else att.get("sede", "")
        if display and display not in seen:
            seen.append(display)
    return seen or ["–"]


def _day_ora(attivita_list: list) -> str:
    oras_i = [a.get("ora_inizio", "") for a in attivita_list if a.get("ora_inizio")]
    oras_f = [a.get("ora_fine",   "") for a in attivita_list if a.get("ora_fine")]
    ora_i = min(oras_i) if oras_i else "08:00"
    ora_f = max(oras_f) if oras_f else "18:00"
    return f"{ora_i} – {ora_f}"


def _day_sede(attivita_list: list) -> str:
    for a in attivita_list:
        if a.get("sede") == "Altra Sede":
            return "Altra Sede"
    return "Molinette"


def _transparent_scroll(scroll: QScrollArea) -> QScrollArea:
    scroll.setWidgetResizable(True)
    scroll.setFrameShape(QFrame.Shape.NoFrame)
    scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
    scroll.setStyleSheet("QScrollArea { background: transparent; border: none; }")
    scroll.viewport().setStyleSheet("background: transparent;")
    return scroll


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
        self._build_page_giorno()

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

        body = QHBoxLayout()
        body.setSpacing(24)

        self.lista_risultati = QListWidget()
        self.lista_risultati.setObjectName("ListaRisultati")
        self.lista_risultati.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lista_risultati.setSpacing(5)

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

    def _build_page_dettaglio(self):
        self.page_dettaglio = QWidget()
        layout = QVBoxLayout(self.page_dettaglio)
        layout.setContentsMargins(40, 28, 40, 28)
        layout.setSpacing(18)

        nav = QHBoxLayout()
        nav.setSpacing(12)

        self.btn_indietro = QPushButton("← Indietro")
        self.btn_indietro.setObjectName("BtnIndietro")
        self.btn_indietro.setFixedSize(150, 42)
        self.btn_indietro.setCursor(Qt.CursorShape.PointingHandCursor)
        nav.addWidget(self.btn_indietro)
        nav.addStretch()

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

        card_det = QFrame()
        card_det.setObjectName("CardDettaglio")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 18))
        shadow.setOffset(0, 4)
        card_det.setGraphicsEffect(shadow)

        cd = QVBoxLayout(card_det)
        cd.setContentsMargins(40, 35, 40, 40)
        cd.setSpacing(20)

        info_row = QHBoxLayout()
        info_row.setSpacing(16)
        box_mat, self.val_matricola = self._crea_info_box("Matricola", "-")
        box_liv, self.val_livello   = self._crea_info_box("Livello", "-")
        box_sta, self.val_stato     = self._crea_info_box("Stato", "-")
        box_sco, self.val_score     = self._crea_info_box("Training Score", "–", accent=True)
        for box in [box_mat, box_liv, box_sta, box_sco]:
            info_row.addWidget(box)
        cd.addLayout(info_row)

        sep = QFrame()
        sep.setObjectName("Separatore")
        sep.setFixedHeight(1)
        cd.addWidget(sep)

        tab_row = QHBoxLayout()
        tab_row.setSpacing(8)

        self.btn_tab_completate = QPushButton("Completate")
        self.btn_tab_completate.setObjectName("TabBtnCompletate")
        self.btn_tab_completate.setCheckable(True)
        self.btn_tab_completate.setChecked(True)
        self.btn_tab_completate.setFixedHeight(36)
        self.btn_tab_completate.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_tab_pianificate = QPushButton("Pianificate")
        self.btn_tab_pianificate.setObjectName("TabBtnPianificate")
        self.btn_tab_pianificate.setCheckable(True)
        self.btn_tab_pianificate.setChecked(False)
        self.btn_tab_pianificate.setFixedHeight(36)
        self.btn_tab_pianificate.setCursor(Qt.CursorShape.PointingHandCursor)

        self.lbl_n_attivita = QLabel("")
        self.lbl_n_attivita.setObjectName("LblNAttivita")

        tab_row.addWidget(self.btn_tab_completate)
        tab_row.addWidget(self.btn_tab_pianificate)
        tab_row.addStretch()
        tab_row.addWidget(self.lbl_n_attivita)
        cd.addLayout(tab_row)

        self.lista_attivita = QListWidget()
        self.lista_attivita.setObjectName("ListaAttivita")
        self.lista_attivita.setSpacing(3)
        self.lista_attivita.setVerticalScrollMode(
            QAbstractItemView.ScrollMode.ScrollPerPixel)
        self.lista_attivita.setCursor(Qt.CursorShape.PointingHandCursor)
        cd.addWidget(self.lista_attivita)

        layout.addWidget(card_det)
        self.stacked_widget.addWidget(self.page_dettaglio)

    def _build_page_giorno(self):
        self.page_attivita = QWidget()
        self.page_attivita.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        layout = QVBoxLayout(self.page_attivita)
        layout.setContentsMargins(40, 28, 40, 28)
        layout.setSpacing(18)

        nav = QHBoxLayout()
        self.btn_indietro_att = QPushButton("← Torna al libretto")
        self.btn_indietro_att.setObjectName("BtnIndietro")
        self.btn_indietro_att.setFixedSize(200, 42)
        self.btn_indietro_att.setCursor(Qt.CursorShape.PointingHandCursor)
        nav.addWidget(self.btn_indietro_att)
        nav.addStretch()
        layout.addLayout(nav)

        card = QFrame()
        card.setObjectName("CardDettaglio")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 18))
        shadow.setOffset(0, 4)
        card.setGraphicsEffect(shadow)

        cd = QVBoxLayout(card)
        cd.setContentsMargins(40, 30, 40, 36)
        cd.setSpacing(16)

        self.lbl_giorno_titolo = QLabel("")
        self.lbl_giorno_titolo.setObjectName("TitoloAttivita")
        cd.addWidget(self.lbl_giorno_titolo)

        sep = QFrame()
        sep.setObjectName("Separatore")
        sep.setFixedHeight(1)
        cd.addWidget(sep)

        meta_frame = QFrame()
        meta_frame.setObjectName("MetaGiornoFrame")
        meta_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        mf = QHBoxLayout(meta_frame)
        mf.setContentsMargins(20, 10, 20, 10)
        mf.setSpacing(10)

        lbl_ora_key = QLabel("ORA")
        lbl_ora_key.setObjectName("LblMetaGiornoKey")
        self.inp_meta_ora_inizio = QLineEdit("08:00")
        self.inp_meta_ora_inizio.setObjectName("InputMetaOra")
        self.inp_meta_ora_inizio.setFixedWidth(72)
        self.inp_meta_ora_inizio.setPlaceholderText("HH:MM")
        lbl_ora_sep = QLabel("–")
        lbl_ora_sep.setObjectName("LblMetaDash")
        self.inp_meta_ora_fine = QLineEdit("18:00")
        self.inp_meta_ora_fine.setObjectName("InputMetaOra")
        self.inp_meta_ora_fine.setFixedWidth(72)
        self.inp_meta_ora_fine.setPlaceholderText("HH:MM")

        lbl_sede_key = QLabel("SEDE")
        lbl_sede_key.setObjectName("LblMetaGiornoKey")
        self.combo_meta_sede = QComboBox()
        self.combo_meta_sede.setObjectName("ComboMetaSede")
        self.combo_meta_sede.setFixedWidth(150)
        self.combo_meta_sede.addItems(["Molinette", "Altra Sede"])

        mf.addWidget(lbl_ora_key)
        mf.addSpacing(6)
        mf.addWidget(self.inp_meta_ora_inizio)
        mf.addSpacing(6)
        mf.addWidget(lbl_ora_sep)
        mf.addSpacing(6)
        mf.addWidget(self.inp_meta_ora_fine)
        mf.addSpacing(24)
        mf.addWidget(lbl_sede_key)
        mf.addSpacing(6)
        mf.addWidget(self.combo_meta_sede)
        mf.addStretch()

        self.btn_salva_meta = QPushButton("Salva info giorno")
        self.btn_salva_meta.setObjectName("BtnSalvaMeta")
        self.btn_salva_meta.setFixedHeight(34)
        self.btn_salva_meta.setCursor(Qt.CursorShape.PointingHandCursor)
        mf.addWidget(self.btn_salva_meta)

        self._on_save_meta_fn = None
        self.btn_salva_meta.clicked.connect(self._dispatch_save_meta)

        cd.addWidget(meta_frame)

        sep2 = QFrame()
        sep2.setObjectName("Separatore")
        sep2.setFixedHeight(1)
        cd.addWidget(sep2)

        scroll = _transparent_scroll(QScrollArea())
        container = QWidget()
        container.setStyleSheet("background: transparent;")
        self.giorno_cards_layout = QVBoxLayout(container)
        self.giorno_cards_layout.setContentsMargins(0, 4, 0, 4)
        self.giorno_cards_layout.setSpacing(14)
        scroll.setWidget(container)
        cd.addWidget(scroll)

        layout.addWidget(card)
        self.stacked_widget.addWidget(self.page_attivita)

    def crea_header_giorni(self):
        """Column label row at the top of the day list."""
        widget = QFrame()
        widget.setObjectName("RowColonne")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        hl = QHBoxLayout(widget)
        hl.setContentsMargins(18, 6, 18, 6)
        hl.setSpacing(0)

        def _h(text, min_w=None, stretch=0, align=Qt.AlignmentFlag.AlignLeft):
            lbl = QLabel(text)
            lbl.setObjectName("LblColonna")
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl.setAlignment(align)
            if min_w:
                lbl.setMinimumWidth(min_w)
            hl.addWidget(lbl, stretch=stretch)

        def _sep():
            hl.addSpacing(8)
            hl.addWidget(self._vsep())
            hl.addSpacing(8)

        _h("GIORNO", stretch=2)
        _sep()
        _h("ORA", min_w=130, align=Qt.AlignmentFlag.AlignCenter)
        _sep()
        _h("SEDE", min_w=120, align=Qt.AlignmentFlag.AlignCenter)
        _sep()
        _h("ATTIVITÀ", stretch=3)
        hl.addSpacing(90)  # room for badge + arrow

        item = QListWidgetItem()
        item.setFlags(Qt.ItemFlag.NoItemFlags)
        item.setSizeHint(QSize(0, 30))
        item.setData(Qt.ItemDataRole.UserRole, None)
        return item, widget

    def crea_item_giorno(self, data_str: str, attivita_list: list, meta: dict = None):
        label_txt = _fmt_data(data_str)
        tags      = _day_activity_tags(attivita_list)
        n         = len(attivita_list)
        n_txt     = f"{n} att."

        if meta:
            ora_txt  = f"{meta.get('ora_inizio', '08:00')} – {meta.get('ora_fine', '18:00')}"
            sede_txt = meta.get("sede", _day_sede(attivita_list))
        else:
            ora_txt  = _day_ora(attivita_list)
            sede_txt = _day_sede(attivita_list)

        widget = QFrame()
        widget.setObjectName("ItemGiorno")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        hl = QHBoxLayout(widget)
        hl.setContentsMargins(18, 0, 18, 0)
        hl.setSpacing(0)
        hl.setAlignment(Qt.AlignmentFlag.AlignVCenter)

        def _sep():
            hl.addSpacing(8)
            hl.addWidget(self._vsep())
            hl.addSpacing(8)

        lbl_data = QLabel(label_txt)
        lbl_data.setObjectName("ItemGiornoData")
        lbl_data.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        hl.addWidget(lbl_data, stretch=2)

        _sep()

        lbl_ora = QLabel(ora_txt)
        lbl_ora.setObjectName("ItemGiornoOra")
        lbl_ora.setMinimumWidth(130)
        lbl_ora.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ora.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        hl.addWidget(lbl_ora)

        _sep()

        lbl_sede = QLabel(sede_txt)
        lbl_sede.setObjectName("ItemGiornoSede")
        lbl_sede.setMinimumWidth(120)
        lbl_sede.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_sede.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        hl.addWidget(lbl_sede)

        _sep()

        tags_wrap = QWidget()
        tags_wrap.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        tags_wrap.setStyleSheet("background: transparent;")
        tags_layout = QHBoxLayout(tags_wrap)
        tags_layout.setContentsMargins(0, 0, 0, 0)
        tags_layout.setSpacing(6)
        tags_layout.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)

        for tag in tags[:4]:
            bg, fg = _TAG_COLORS.get(tag, _TAG_DEFAULT)
            pill = QLabel(f"  {tag}  ")
            pill.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            pill.setFixedHeight(22)
            pill.setAlignment(Qt.AlignmentFlag.AlignCenter)
            pill.setStyleSheet(
                f"background:{bg}; color:{fg}; font-size:11px; font-weight:bold;"
                f"border-radius:11px; border:1px solid {fg}30; padding:0 2px;"
            )
            tags_layout.addWidget(pill)
        if len(tags) > 4:
            extra = QLabel(f"+{len(tags) - 4}")
            extra.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            extra.setFixedHeight(22)
            extra.setAlignment(Qt.AlignmentFlag.AlignCenter)
            extra.setStyleSheet(
                "background:#f1f5f9; color:#475569; font-size:11px; font-weight:bold;"
                "border-radius:11px; border:1px solid #cbd5e1; padding:0 6px;"
            )
            tags_layout.addWidget(extra)
        tags_layout.addStretch()
        hl.addWidget(tags_wrap, stretch=3)

        badge = QLabel(n_txt)
        badge.setObjectName("ItemGiornoBadge")
        badge.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        badge.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(badge)

        arrow = QLabel("›")
        arrow.setObjectName("CellArrow")
        arrow.setFixedWidth(24)
        arrow.setAlignment(Qt.AlignmentFlag.AlignCenter)
        arrow.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        hl.addWidget(arrow)

        item = QListWidgetItem()
        item.setSizeHint(QSize(0, 62))
        item.setData(Qt.ItemDataRole.UserRole, {"data": data_str, "attivita": attivita_list})
        return item, widget

    def popola_dettaglio_giorno(self, data_str: str, attivita: list,
                                extra_dict: dict, on_save,
                                meta: dict = None, on_save_meta=None):
        self.lbl_giorno_titolo.setText(_fmt_data(data_str))

        m = meta or {}
        self.inp_meta_ora_inizio.setText(m.get("ora_inizio", "08:00"))
        self.inp_meta_ora_fine.setText(m.get("ora_fine", "18:00"))
        sede_val = m.get("sede", "Molinette")
        idx = self.combo_meta_sede.findText(sede_val)
        self.combo_meta_sede.setCurrentIndex(idx if idx >= 0 else 0)

        self._on_save_meta_fn = on_save_meta

        while self.giorno_cards_layout.count():
            child = self.giorno_cards_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        for att in attivita:
            if att.get("tipo") == "completata":
                if att.get("ruolo") in ("OR I", "OR II"):
                    card = self._crea_card_or(att)
                else:
                    card = self._crea_card_completata_semplice(att)
            elif att.get("or_pianificata"):
                key   = (att["data"], att["sede"], att["attivita"])
                saved = extra_dict.get(key, {})
                card  = self._crea_card_or_pianificata(att, saved, on_save)
            else:
                key   = (att["data"], att["sede"], att["attivita"])
                saved = extra_dict.get(key, {})
                card  = self._crea_card_extra_semplice(att, saved, on_save)
            self.giorno_cards_layout.addWidget(card)

        self.giorno_cards_layout.addStretch()

    def _crea_card_or(self, att: dict) -> QFrame:
        """Read-only card for a convalidated OR activity."""
        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1.5px solid #e2e8f0; "
            "border-radius: 14px; }"
        )

        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 18, 24, 18)
        vl.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)

        badge_c = QLabel("✔  Completata")
        badge_c.setStyleSheet(
            "background:#dcfce7; color:#15803d; font-weight:bold; font-size:12px;"
            "padding:3px 14px; border-radius:10px; border:1px solid #86efac;"
        )
        lbl_tipo = QLabel(att.get("attivita", "Intervento Chirurgico"))
        lbl_tipo.setStyleSheet("font-size:15px; font-weight:bold; color:#1e293b; border:none; background:transparent;")
        lbl_ora = QLabel(f"{att.get('ora_inizio','08:00')} – {att.get('ora_fine','18:00')}")
        lbl_ora.setStyleSheet("font-size:13px; font-weight:bold; color:#4338ca; border:none; background:transparent;")
        hdr.addWidget(badge_c)
        hdr.addWidget(lbl_tipo, stretch=1)
        hdr.addWidget(lbl_ora)
        vl.addLayout(hdr)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#f1f5f9; border:none;")
        vl.addWidget(sep)

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(12)
        grid.setColumnMinimumWidth(0, 130)
        grid.setColumnStretch(1, 2)
        grid.setColumnMinimumWidth(2, 130)
        grid.setColumnStretch(3, 2)

        r = [0]

        def _lbl_key(text):
            l = QLabel(text)
            l.setStyleSheet("font-size:11px; font-weight:bold; color:#94a3b8; "
                            "letter-spacing:0.8px; border:none; background:transparent;")
            return l

        def _lbl_val(text):
            l = QLabel(text)
            l.setWordWrap(True)
            l.setStyleSheet("font-size:14px; color:#1e293b; border:none; background:transparent;")
            return l

        def _pair(l1, v1, l2="", v2=""):
            if not v1 and not v2:
                return
            grid.addWidget(_lbl_key(l1), r[0], 0)
            grid.addWidget(_lbl_val(v1 or "–"), r[0], 1)
            if l2:
                grid.addWidget(_lbl_key(l2), r[0], 2)
                grid.addWidget(_lbl_val(v2 or "–"), r[0], 3)
            r[0] += 1

        def _span(label, value):
            if not value:
                return
            grid.addWidget(_lbl_key(label), r[0], 0)
            grid.addWidget(_lbl_val(value), r[0], 1, 1, 3)
            r[0] += 1

        _pair("SEDE", "Molinette", "ATTIVITÀ", att.get("attivita", "Sala Operatoria"))

        interv  = att.get("intervento", "")
        cod     = att.get("codice_intervento", "")
        _span("INTERVENTO", f"[{cod}]  {interv}" if cod and interv else interv)

        _pair("PAZIENTE",   att.get("nome_paziente", ""),
              "DIAGNOSI",   att.get("diagnosi", ""))
        _pair("CHIRURGO",   att.get("chirurgo", ""),
              "RUOLO",      att.get("ruolo", ""))
        _pair("COMPLESSITÀ", att.get("complessita", ""),
              "TIPO CHIRURGIA", att.get("tipo_chirurgia", ""))
        _span("NOTE", att.get("note", ""))

        vl.addLayout(grid)
        return card

    def _crea_card_or_pianificata(self, att: dict, saved: dict, on_save) -> QFrame:
        """Card for a pianificata OR day: read-only slot details + editable Note."""
        _slot_fmt = {
            "8.00-10.00":  "08:00 – 10:00",
            "10.00-12.00": "10:00 – 12:00",
            "14.00-16.00": "14:00 – 16:00",
            "16.00-18.00": "16:00 – 18:00",
        }

        def _lbl_key(text):
            l = QLabel(text)
            l.setStyleSheet("font-size:11px; font-weight:bold; color:#94a3b8; "
                            "letter-spacing:0.8px; border:none; background:transparent;")
            return l

        def _lbl_val(text):
            l = QLabel(str(text) if text else "–")
            l.setWordWrap(True)
            l.setStyleSheet("font-size:14px; color:#1e293b; border:none; background:transparent;")
            return l

        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame { background: #eff6ff; border: 1.5px solid #bfdbfe; "
            "border-radius: 14px; }"
        )

        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 18, 24, 20)
        vl.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        badge_ruolo = QLabel(att.get("ruolo", "Sala Op."))
        badge_ruolo.setStyleSheet(
            "background:#dbeafe; color:#1d4ed8; font-weight:bold; font-size:12px;"
            "padding:3px 14px; border-radius:10px; border:1px solid #93c5fd;"
        )
        hdr.addWidget(badge_ruolo)
        lbl_tipo = QLabel("Intervento Chirurgico")
        lbl_tipo.setStyleSheet("font-size:15px; font-weight:bold; color:#1e293b; border:none; background:transparent;")
        hdr.addWidget(lbl_tipo, stretch=1)
        stato_txt = "Confermata" if saved else "Da confermare"
        badge_stato = QLabel(stato_txt)
        badge_stato.setStyleSheet(
            ("background:#f0fdf4; color:#15803d; font-weight:bold; font-size:11px; "
             "padding:2px 10px; border-radius:8px; border:1px solid #86efac;")
            if saved else
            ("background:#fef9c3; color:#854d0e; font-weight:bold; font-size:11px; "
             "padding:2px 10px; border-radius:8px; border:1px solid #fde047;")
        )
        hdr.addWidget(badge_stato)
        vl.addLayout(hdr)

        sep1 = QFrame()
        sep1.setFixedHeight(1)
        sep1.setStyleSheet("background:#bfdbfe; border:none;")
        vl.addWidget(sep1)

        slots = att.get("slots", [])
        if slots:
            for slot in slots:
                slot_frame = QFrame()
                slot_frame.setStyleSheet(
                    "QFrame { background: #ffffff; border: 1px solid #e2e8f0; "
                    "border-radius: 10px; }"
                )
                sf = QVBoxLayout(slot_frame)
                sf.setContentsMargins(16, 12, 16, 12)
                sf.setSpacing(8)

                ora_txt = _slot_fmt.get(slot.get("label", ""), slot.get("label", ""))
                lbl_ora = QLabel(ora_txt)
                lbl_ora.setStyleSheet("font-size:12px; font-weight:bold; color:#4338ca; border:none; background:transparent;")
                sf.addWidget(lbl_ora)

                grid = QGridLayout()
                grid.setHorizontalSpacing(20)
                grid.setVerticalSpacing(8)
                grid.setColumnMinimumWidth(0, 110)
                grid.setColumnStretch(1, 2)
                grid.setColumnMinimumWidth(2, 110)
                grid.setColumnStretch(3, 2)

                nome_paz = slot.get("nome_paziente", "")
                id_paz   = slot.get("id_paziente", "")
                paz_str  = f"{nome_paz}  [{id_paz}]" if nome_paz and id_paz else nome_paz
                grid.addWidget(_lbl_key("PAZIENTE"), 0, 0)
                grid.addWidget(_lbl_val(paz_str), 0, 1)
                grid.addWidget(_lbl_key("DIAGNOSI"), 0, 2)
                grid.addWidget(_lbl_val(slot.get("diagnosi", "")), 0, 3)

                interv = slot.get("intervento", "")
                cod    = slot.get("codice_intervento", "")
                interv_str = f"[{cod}]  {interv}" if cod and interv else interv
                if interv_str:
                    grid.addWidget(_lbl_key("INTERVENTO"), 1, 0)
                    grid.addWidget(_lbl_val(interv_str), 1, 1, 1, 3)
                    grid.addWidget(_lbl_key("CHIRURGO"), 2, 0)
                    grid.addWidget(_lbl_val(slot.get("chirurgo", "")), 2, 1)
                    grid.addWidget(_lbl_key("COMPLESSITÀ"), 2, 2)
                    grid.addWidget(_lbl_val(slot.get("complessita", "")), 2, 3)
                else:
                    grid.addWidget(_lbl_key("CHIRURGO"), 1, 0)
                    grid.addWidget(_lbl_val(slot.get("chirurgo", "")), 1, 1)
                    grid.addWidget(_lbl_key("COMPLESSITÀ"), 1, 2)
                    grid.addWidget(_lbl_val(slot.get("complessita", "")), 1, 3)

                sf.addLayout(grid)
                vl.addWidget(slot_frame)
        else:
            lbl_empty = QLabel("Nessun dettaglio intervento disponibile per questo giorno.")
            lbl_empty.setStyleSheet("font-size:13px; color:#64748b; border:none; background:transparent;")
            vl.addWidget(lbl_empty)

        sep2 = QFrame()
        sep2.setFixedHeight(1)
        sep2.setStyleSheet("background:#e0e7ff; border:none;")
        vl.addWidget(sep2)

        note_lbl = QLabel("NOTE")
        note_lbl.setStyleSheet("font-size:11px; font-weight:bold; color:#64748b; "
                               "letter-spacing:0.6px; border:none; background:transparent;")
        vl.addWidget(note_lbl)

        inp_note = QLineEdit(saved.get("note", att.get("note", "")))
        inp_note.setPlaceholderText("Note aggiuntive...")
        inp_note.setEnabled(not bool(saved))
        inp_note.setStyleSheet(
            "QLineEdit { background:#ffffff; border:1.5px solid #93c5fd; "
            "border-radius:8px; padding:0 10px; font-size:14px; color:#1e293b; "
            "min-height:34px; }"
            "QLineEdit:focus { border-color:#2563eb; }"
            "QLineEdit:disabled { background:#f1f5f9; color:#94a3b8; }"
        )
        vl.addWidget(inp_note)

        save_row = QHBoxLayout()
        save_row.addStretch()
        btn_salva = QPushButton("Conferma" if not saved else "✔ Confermata")
        btn_salva.setFixedHeight(36)
        btn_salva.setMinimumWidth(120)
        btn_salva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_salva.setEnabled(not bool(saved))
        btn_salva.setStyleSheet(
            "QPushButton { background:#2563eb; color:#fff; font-weight:bold; "
            "font-size:13px; border:none; border-radius:8px; padding:0 16px; }"
            "QPushButton:hover { background:#1d4ed8; }"
            "QPushButton:disabled { background:#e2e8f0; color:#94a3b8; }"
        )
        save_row.addWidget(btn_salva)
        vl.addLayout(save_row)

        def _do_save():
            on_save({
                "data":     att["data"],
                "sede":     att["sede"],
                "attivita": att["attivita"],
                "ruolo":    att.get("ruolo", ""),
                "note":     inp_note.text().strip(),
                "tipo":     "extra",
            })
            badge_stato.setText("Confermata")
            badge_stato.setStyleSheet(
                "background:#f0fdf4; color:#15803d; font-weight:bold; font-size:11px; "
                "padding:2px 10px; border-radius:8px; border:1px solid #86efac;"
            )
            btn_salva.setText("✔ Confermata")
            btn_salva.setEnabled(False)
            inp_note.setEnabled(False)

        btn_salva.clicked.connect(_do_save)
        return card

    def _crea_card_extra_semplice(self, att: dict, saved: dict, on_save) -> QFrame:
        """Editable card for a non-OR pianificata activity: only Descrizione + Note."""
        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame { background: #faf5ff; border: 1.5px solid #e9d5ff; "
            "border-radius: 14px; }"
        )

        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 18, 24, 20)
        vl.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        badge_p = QLabel(f"  {att.get('attivita', att.get('sede', 'Attività'))}  ")
        badge_p.setStyleSheet(
            "background:#ede9fe; color:#5b21b6; font-weight:bold; font-size:12px;"
            "padding:3px 14px; border-radius:10px; border:1px solid #c4b5fd;"
        )
        hdr.addWidget(badge_p)
        ruolo_raw = att.get("ruolo", "")
        if ruolo_raw and ruolo_raw != att.get("attivita", ""):
            badge_ruolo = QLabel(ruolo_raw)
            badge_ruolo.setStyleSheet(
                "background:#f1f5f9; color:#475569; font-weight:bold; font-size:11px;"
                "padding:2px 10px; border-radius:8px; border:1px solid #cbd5e1;"
            )
            hdr.addWidget(badge_ruolo)
        stato_txt = "Confermata" if saved else "Da confermare"
        badge_stato = QLabel(stato_txt)
        badge_stato.setStyleSheet(
            ("background:#f0fdf4; color:#15803d; font-weight:bold; font-size:11px; "
             "padding:2px 10px; border-radius:8px; border:1px solid #86efac;")
            if saved else
            ("background:#fef9c3; color:#854d0e; font-weight:bold; font-size:11px; "
             "padding:2px 10px; border-radius:8px; border:1px solid #fde047;")
        )
        hdr.addWidget(badge_stato)
        hdr.addStretch()
        vl.addLayout(hdr)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#e9d5ff; border:none;")
        vl.addWidget(sep)

        def _lbl(text):
            l = QLabel(text)
            l.setStyleSheet("font-size:11px; font-weight:bold; color:#64748b; "
                            "letter-spacing:0.6px; border:none; background:transparent;")
            return l

        def _inp(val, placeholder=""):
            e = QLineEdit(val)
            e.setPlaceholderText(placeholder)
            e.setEnabled(not bool(saved))
            e.setStyleSheet(
                "QLineEdit { background:#ffffff; border:1.5px solid #ddd6fe; "
                "border-radius:8px; padding:0 10px; font-size:14px; color:#1e293b; "
                "min-height:34px; }"
                "QLineEdit:focus { border-color:#7c3aed; }"
                "QLineEdit:disabled { background:#f1f5f9; color:#94a3b8; }"
            )
            return e

        form = QGridLayout()
        form.setHorizontalSpacing(16)
        form.setVerticalSpacing(12)
        form.setColumnMinimumWidth(0, 110)
        form.setColumnStretch(1, 1)

        inp_descr = _inp(saved.get("descrizione", ""), "Descrizione attività svolta...")
        inp_note  = _inp(saved.get("note", att.get("note", "")), "Note aggiuntive...")

        form.addWidget(_lbl("DESCRIZIONE"), 0, 0)
        form.addWidget(inp_descr, 0, 1)
        form.addWidget(_lbl("NOTE"), 1, 0)
        form.addWidget(inp_note, 1, 1)

        vl.addLayout(form)

        save_row = QHBoxLayout()
        save_row.addStretch()
        btn_salva = QPushButton("Conferma" if not saved else "✔ Confermata")
        btn_salva.setFixedHeight(36)
        btn_salva.setMinimumWidth(120)
        btn_salva.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_salva.setEnabled(not bool(saved))
        btn_salva.setStyleSheet(
            "QPushButton { background:#7c3aed; color:#fff; font-weight:bold; "
            "font-size:13px; border:none; border-radius:8px; padding:0 16px; }"
            "QPushButton:hover { background:#6d28d9; }"
            "QPushButton:disabled { background:#e2e8f0; color:#94a3b8; }"
        )
        save_row.addWidget(btn_salva)
        vl.addLayout(save_row)

        def _do_save():
            on_save({
                "data":        att["data"],
                "sede":        att["sede"],
                "attivita":    att["attivita"],
                "ruolo":       att.get("ruolo", ""),
                "descrizione": inp_descr.text().strip(),
                "note":        inp_note.text().strip(),
                "tipo":        "extra",
            })
            badge_stato.setText("Confermata")
            badge_stato.setStyleSheet(
                "background:#f0fdf4; color:#15803d; font-weight:bold; font-size:11px; "
                "padding:2px 10px; border-radius:8px; border:1px solid #86efac;"
            )
            btn_salva.setText("✔ Confermata")
            btn_salva.setEnabled(False)
            inp_descr.setEnabled(False)
            inp_note.setEnabled(False)

        btn_salva.clicked.connect(_do_save)
        return card

    def _crea_card_completata_semplice(self, att: dict) -> QFrame:
        """Read-only card for a manually confirmed (non-OR) activity."""
        card = QFrame()
        card.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        card.setStyleSheet(
            "QFrame { background: #ffffff; border: 1.5px solid #e2e8f0; "
            "border-radius: 14px; }"
        )

        vl = QVBoxLayout(card)
        vl.setContentsMargins(24, 18, 24, 18)
        vl.setSpacing(14)

        hdr = QHBoxLayout()
        hdr.setSpacing(10)
        badge_c = QLabel("✔  Completata")
        badge_c.setStyleSheet(
            "background:#dcfce7; color:#15803d; font-weight:bold; font-size:12px;"
            "padding:3px 14px; border-radius:10px; border:1px solid #86efac;"
        )
        lbl_tipo = QLabel(att.get("attivita", att.get("sede", "Attività")))
        lbl_tipo.setStyleSheet("font-size:15px; font-weight:bold; color:#1e293b; border:none; background:transparent;")
        hdr.addWidget(badge_c)
        hdr.addWidget(lbl_tipo, stretch=1)
        ruolo_raw = att.get("ruolo", "")
        if ruolo_raw and ruolo_raw != att.get("attivita", ""):
            badge_r = QLabel(ruolo_raw)
            badge_r.setStyleSheet(
                "background:#f1f5f9; color:#475569; font-weight:bold; font-size:11px;"
                "padding:2px 10px; border-radius:8px; border:1px solid #cbd5e1;"
            )
            hdr.addWidget(badge_r)
        vl.addLayout(hdr)

        sep = QFrame()
        sep.setFixedHeight(1)
        sep.setStyleSheet("background:#f1f5f9; border:none;")
        vl.addWidget(sep)

        def _lbl_key(text):
            l = QLabel(text)
            l.setStyleSheet("font-size:11px; font-weight:bold; color:#94a3b8; "
                            "letter-spacing:0.8px; border:none; background:transparent;")
            return l

        def _lbl_val(text):
            l = QLabel(str(text) if text else "–")
            l.setWordWrap(True)
            l.setStyleSheet("font-size:14px; color:#1e293b; border:none; background:transparent;")
            return l

        grid = QGridLayout()
        grid.setHorizontalSpacing(20)
        grid.setVerticalSpacing(10)
        grid.setColumnMinimumWidth(0, 110)
        grid.setColumnStretch(1, 1)

        row = 0
        sede = att.get("sede", "")
        if sede:
            grid.addWidget(_lbl_key("SEDE"), row, 0)
            grid.addWidget(_lbl_val(sede), row, 1)
            row += 1
        descrizione = att.get("descrizione", "")
        if descrizione:
            grid.addWidget(_lbl_key("DESCRIZIONE"), row, 0)
            grid.addWidget(_lbl_val(descrizione), row, 1)
            row += 1
        note = att.get("note", "")
        if note:
            grid.addWidget(_lbl_key("NOTE"), row, 0)
            grid.addWidget(_lbl_val(note), row, 1)
            row += 1

        if row > 0:
            vl.addLayout(grid)

        return card

    def _dispatch_save_meta(self):
        if self._on_save_meta_fn:
            self._on_save_meta_fn({
                "ora_inizio": self.inp_meta_ora_inizio.text().strip(),
                "ora_fine":   self.inp_meta_ora_fine.text().strip(),
                "sede":       self.combo_meta_sede.currentText(),
            })

    def _vsep(self):
        sep = QFrame()
        sep.setObjectName("CellSep")
        sep.setFixedWidth(1)
        sep.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        return sep

    def _crea_info_box(self, etichetta, valore_iniziale, accent=False):
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
        widget = QFrame()
        widget.setObjectName("ItemCard")
        widget.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        row = QHBoxLayout(widget)
        row.setContentsMargins(16, 10, 16, 10)
        row.setSpacing(14)

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
        cognome = spec.get("cognome", "").upper()
        nome    = spec.get("nome", "")
        livello = spec.get("livello", "N/D")
        stato   = spec.get("stato", "N/D")

        self.lbl_cognome_medico.setText(cognome)
        self.lbl_nome_proprio_medico.setText(nome)
        self.val_matricola.setText(spec.get("matricola", "N/D"))

        bg, fg = _COLORI_LIVELLO.get(livello, ("#f1f5f9", "#475569"))
        self.val_livello.setText(livello)
        self.val_livello.setStyleSheet(
            f"background-color:{bg}; color:{fg}; font-size:18px; "
            f"font-weight:bold; padding:10px 16px; border-radius:10px; "
            f"border:1.5px solid {fg}60;"
        )

        bg2, fg2 = _COLORI_STATO.get(stato, ("#f1f5f9", "#475569"))
        self.val_stato.setText(stato)
        self.val_stato.setStyleSheet(
            f"background-color:{bg2}; color:{fg2}; font-size:18px; "
            f"font-weight:bold; padding:10px 16px; border-radius:10px; "
            f"border:1.5px solid {fg2}60;"
        )

    def load_styles(self):
        style_path = str(get_asset_dir() / "styles" / "libretto.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.stacked_widget.currentIndex() == 0:
            self.lista_risultati.clearSelection()
