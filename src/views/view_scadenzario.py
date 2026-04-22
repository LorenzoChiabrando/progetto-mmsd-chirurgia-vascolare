import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QScroller,
    QStackedWidget, QLabel, QSizePolicy, QGraphicsDropShadowEffect, QFrame,
    QSpacerItem
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap, QColor, QFont

from src.views.components.colored_header_view import ColoredHeaderView


# ── Palette cromatica per tipo di riga ───────────────────────────────────────
_COLORI_RIGA = {
    "Reparto I":    "#dbeafe",   # blue-100
    "Reparto II":   "#dbeafe",   # blue-100
    "Sala Op. I":   "#dcfce7",   # green-100
    "Sala Op. II":  "#dcfce7",   # green-100
    "Giro Visite":  "#fef9c3",   # yellow-100
    "Day Hospital": "#fae8ff",   # fuchsia-100
    "Day Surgery":  "#fae8ff",   # fuchsia-100
}

# Colori intestazioni verticali (usati dal ColoredHeaderView)
_COLORI_HEADER = {
    "Giorno":       "#e2e8f0",   # slate-200
    "Tipo Guardia": "#c7d2fe",   # indigo-200
    "Reparto I":    "#bfdbfe",   # blue-200
    "Reparto II":   "#bfdbfe",
    "Sala Op. I":   "#bbf7d0",   # green-200
    "Sala Op. II":  "#bbf7d0",
    "Giro Visite":  "#fde68a",   # amber-200
    "Day Hospital": "#e9d5ff",   # violet-200
    "Day Surgery":  "#e9d5ff",
}

# Colori testo per il Tipo Guardia
_COLORI_GUARDIA = {
    "118": "#b91c1c",   # red-700
    "PI":  "#c2410c",   # orange-700
    "L":   "#15803d",   # green-700
}


class ViewScadenzario(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self.row_labels = [
            "Giorno", "Tipo Guardia", "Reparto I", "Reparto II",
            "Sala Op. I", "Sala Op. II", "Giro Visite",
            "Day Hospital", "Day Surgery"
        ]

        self.setup_ui()
        self.load_styles()

    # ── Costruzione UI ────────────────────────────────────────────────────────

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

        # ── Header: titolo + accent bar + sottotitolo ─────────────────────────
        header = QVBoxLayout()
        header.setSpacing(10)
        header.setAlignment(Qt.AlignmentFlag.AlignCenter)

        titolo = QLabel("Scadenzario Chirurgico")
        titolo.setObjectName("TitoloSelezione")
        titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        header.addWidget(titolo)

        # Accent bar centrata sotto il titolo
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

        # ── Cards ─────────────────────────────────────────────────────────────
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

        # Barra navigazione
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

        # Badge modalità e stato
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

        # Legenda tipi guardia
        legenda = QHBoxLayout()
        legenda.setSpacing(16)
        legenda.addStretch()
        for codice, testo, colore, bg in [
            ("118", "Emergenza territoriale", "#991b1b", "#fee2e2"),
            ("PI",  "Pronto Intervento",      "#9a3412", "#ffedd5"),
            ("L",   "Liscia (routinaria)",    "#14532d", "#dcfce7"),
        ]:
            lbl = QLabel(f"  {codice} — {testo}  ")
            lbl.setStyleSheet(
                f"color: {colore}; font-weight: bold; font-size: 11px; "
                f"background-color: {bg}; border: 1px solid {colore}; "
                f"border-radius: 5px; padding: 2px 8px;"
            )
            legenda.addWidget(lbl)
        legenda.addStretch()
        layout.addLayout(legenda)

        # Tabella
        self.tabella = QTableWidget()
        self.tabella.setRowCount(len(self.row_labels))
        self.tabella.setVerticalHeaderLabels(self.row_labels)

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
        self.tabella.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

        # Header verticale colorato
        color_map = {
            idx: _COLORI_HEADER.get(label, "#f8fafc")
            for idx, label in enumerate(self.row_labels)
        }
        v_header = ColoredHeaderView(Qt.Orientation.Vertical, color_map, self.tabella)
        v_header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        v_header.setMinimumSectionSize(62)
        v_header.setSectionsClickable(False)
        v_header.setHighlightSections(False)
        self.tabella.setVerticalHeader(v_header)

        layout.addWidget(self.tabella)

        # Bottone convalida
        self.btn_convalida = QPushButton("CONVALIDA DEFINITIVAMENTE IL MESE")
        self.btn_convalida.setObjectName("BtnConvalida")
        self.btn_convalida.setFixedHeight(60)
        self.btn_convalida.setCursor(Qt.CursorShape.PointingHandCursor)
        layout.addWidget(self.btn_convalida)

        self.stacked_widget.addWidget(self.page_calendario)

    # ── Factory card ──────────────────────────────────────────────────────────

    def _crea_card(self, titolo, descrizione, icon_path, object_name):
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

        # Separatore interno
        sep = QFrame()
        sep.setObjectName("CardSeparatore")
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setFixedHeight(1)

        # Etichetta azione
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

    # ── Factory celle tabella ─────────────────────────────────────────────────

    def crea_item_giorno(self, nome_giorno, is_festivo, is_oggi=False):
        """Item stilizzato per la riga-header del giorno (riga 0)."""
        item = QTableWidgetItem(nome_giorno)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

        if is_oggi and not is_festivo:
            item.setBackground(QColor("#f59e0b"))   # amber-500 vivace
            item.setForeground(QColor("#ffffff"))
        elif is_festivo:
            item.setBackground(QColor("#e2e8f0"))
            item.setForeground(QColor("#94a3b8"))
        else:
            item.setBackground(QColor(Qt.GlobalColor.transparent))
            item.setForeground(QColor("#475569"))

        return item

    def crea_item_cella(self, valore, is_festivo, nome_riga=None, is_oggi=False):
        """Item stilizzato per una cella dati."""
        item = QTableWidgetItem(valore)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)

        if is_festivo:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setBackground(QColor("#e2e8f0"))
            item.setForeground(QColor("#94a3b8"))
            item.setFont(QFont("Segoe UI", 13, QFont.Weight.Normal))
        else:
            # Sfondo: "oggi" ha priorità sul colore di riga
            if is_oggi:
                item.setBackground(QColor("#fef3c7"))   # amber-100
            else:
                bg = _COLORI_RIGA.get(nome_riga, "")
                item.setBackground(QColor(bg) if bg else QColor(Qt.GlobalColor.transparent))

            # Font e colore testo
            if nome_riga == "Tipo Guardia":
                item.setForeground(QColor(_COLORI_GUARDIA.get(valore, "#1e293b")))
                item.setFont(QFont("Segoe UI", 14, QFont.Weight.Bold))
            else:
                item.setForeground(QColor("#1e293b"))
                item.setFont(QFont("Segoe UI", 13, QFont.Weight.DemiBold))

        return item

    def aggiorna_stile_cella(self, riga, colonna, valore, nome_riga, is_festivo, is_oggi=False):
        """Riapplica lo stile a una singola cella dopo che il suo valore è cambiato."""
        self.tabella.blockSignals(True)
        self.tabella.setItem(
            riga, colonna,
            self.crea_item_cella(valore, is_festivo, nome_riga, is_oggi)
        )
        self.tabella.blockSignals(False)

    # ── Badge navigazione ─────────────────────────────────────────────────────

    def aggiorna_badge_modalita(self, modalita, stato):
        """Aggiorna i badge con colori semantici. In STORICO nasconde il badge stato."""
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
        self.lbl_modalita.setText(f"  {modalita}  ")
        self.lbl_modalita.setStyleSheet(
            f"color: {fg_m}; background-color: {bg_m}; font-weight: bold; "
            f"font-size: 12px; border-radius: 8px; padding: 5px 10px;"
        )

        if modalita == "STORICO":
            self.lbl_stato.setVisible(False)
        else:
            self.lbl_stato.setVisible(True)
            fg_s, bg_s = colori_stato.get(stato, ("#334155", "#e2e8f0"))
            self.lbl_stato.setText(f"  {stato}  ")
            self.lbl_stato.setStyleSheet(
                f"color: {fg_s}; background-color: {bg_s}; font-weight: bold; "
                f"font-size: 12px; border-radius: 8px; padding: 5px 10px;"
            )

    # ── Stili ─────────────────────────────────────────────────────────────────

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "scadenzario.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "tabella"):
            self.tabella.viewport().update()
            self.tabella.horizontalHeader().viewport().update()
