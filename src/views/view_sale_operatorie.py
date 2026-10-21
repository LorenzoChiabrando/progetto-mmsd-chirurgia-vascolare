import os
from src.data_paths import PROJECT_ROOT
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QScroller,
    QStackedWidget, QLabel, QSizePolicy, QGraphicsDropShadowEffect,
    QGraphicsOpacityEffect, QFrame, QApplication, QComboBox,
)
from PySide6.QtCore import QByteArray, QMimeData, Qt, Signal
from PySide6.QtGui import QPixmap, QColor, QFont, QDrag, QPainter

from src.calendar_presentation import person_initials
from src.calendar_versions import CalendarVersion
from src.views.components.modal_dialog import register_icon_path


_OPERATION_MIME_TYPE = "application/x-mmsd-operation"


class EtichettaAdattiva(QLabel):
    """Etichetta che mostra la più completa delle ``varianti`` di testo che ci sta intera.

    Le varianti vanno dalla più lunga alla più corta; se nessuna ci sta, l'ultima viene
    accorciata con «…». La larghezza suggerita è ignorata: il layout le dà lo spazio che
    resta, così il testo non comprime i badge accanto e Qt non lo taglia a metà carattere.
    """

    def __init__(self, varianti: list[str]):
        super().__init__(varianti[0])
        self._varianti = varianti
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        metriche = self.fontMetrics()
        spazio = self.contentsRect().width()
        testo = next(
            (t for t in self._varianti if metriche.horizontalAdvance(t) <= spazio),
            metriche.elidedText(self._varianti[-1], Qt.TextElideMode.ElideRight, spazio),
        )
        if testo != self.text():
            self.setText(testo)


def varianti_codici(codici: list[str]) -> list[str]:
    """Testi per la riga dei codici ICD-9, dal più completo al più corto.

    Un codice compare sempre intero: quelli che non ci stanno sono contati con «+N»,
    perché un codice tagliato («39.9» al posto di «39.90») sembrerebbe un altro codice.
    """
    varianti = []
    for prefisso in ("ICD-9: ", ""):
        for mostrati in range(len(codici), 0, -1):
            nascosti = len(codici) - mostrati
            testo = prefisso + "  ·  ".join(codici[:mostrati])
            varianti.append(f"{testo}  +{nascosti}" if nascosti else testo)
    return varianti


class DraggableOperationFrame(QFrame):
    """Frame per un'operazione pianificata: supporta click (popup) e drag (sposta giorno)."""

    def __init__(self):
        super().__init__()
        self._drag_start_pos = None
        self._drag_col = -1
        self._drag_op_idx = -1
        self._can_drag = False
        self._dragging = False
        self._on_click = None
        self._riga_comprimibile: tuple[QHBoxLayout, QLabel] | None = None

    def set_badge_facoltativo(self, riga: QHBoxLayout, badge: QLabel) -> None:
        """Mostra ``badge`` solo quando l'intera ``riga`` ci sta senza comprimere le etichette.

        Sotto la larghezza minima Qt stringe tutte le etichette della riga e le taglia;
        togliendo il badge facoltativo le altre restano sempre leggibili per intero.
        """
        self._riga_comprimibile = (riga, badge)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._adatta_badge_facoltativo()

    def _adatta_badge_facoltativo(self) -> None:
        if self._riga_comprimibile is None or self.layout() is None:
            return
        riga, badge = self._riga_comprimibile
        self.ensurePolished()  # le misure delle etichette dipendono dal foglio di stile
        widgets = [riga.itemAt(i).widget() for i in range(riga.count())]
        larghezze = [w.sizeHint().width() for w in widgets if w is not None]
        necessaria = sum(larghezze) + riga.spacing() * (len(larghezze) - 1)
        margini = self.layout().contentsMargins()
        disponibile = self.contentsRect().width() - margini.left() - margini.right()
        if badge.isVisibleTo(self) != (necessaria <= disponibile):
            badge.setVisible(necessaria <= disponibile)
            # Il layout ha già diviso lo spazio per questa misura: va rifatto adesso,
            # non al prossimo giro dell'event loop, o l'orario resta compresso.
            self.layout().activate()

    def setup_drag(self, col: int, op_idx: int, enabled: bool):
        self._drag_col = col
        self._drag_op_idx = op_idx
        self._can_drag = enabled

    def set_on_click(self, callback):
        self._on_click = callback

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._drag_start_pos = event.position().toPoint()
            self._dragging = False
        event.accept()

    def mouseMoveEvent(self, event):
        if (self._can_drag
                and (event.buttons() & Qt.MouseButton.LeftButton)
                and self._drag_start_pos is not None
                and not self._dragging):
            dist = (event.position().toPoint() - self._drag_start_pos).manhattanLength()
            if dist >= QApplication.startDragDistance():
                self._dragging = True
                self._esegui_drag()
        event.accept()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton and not self._dragging:
            if self._on_click:
                self._on_click()
        self._drag_start_pos = None
        self._dragging = False
        event.accept()

    def _esegui_drag(self):
        source_pix = self.grab()

        dim = QGraphicsOpacityEffect()
        dim.setOpacity(0.35)
        self.setGraphicsEffect(dim)

        ghost = QPixmap(source_pix.size())
        ghost.fill(Qt.GlobalColor.transparent)
        p = QPainter(ghost)
        p.setOpacity(0.78)
        p.drawPixmap(0, 0, source_pix)
        p.end()

        drag = QDrag(self)
        mime = QMimeData()
        payload = f"{self._drag_col}:{self._drag_op_idx}".encode("ascii")
        mime.setData(_OPERATION_MIME_TYPE, QByteArray(payload))
        drag.setMimeData(mime)
        drag.setPixmap(ghost)
        if self._drag_start_pos is not None:
            drag.setHotSpot(self._drag_start_pos)

        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            # Dopo un drop valido il controller può aver ricreato il widget.
            try:
                self.setGraphicsEffect(None)
            except RuntimeError:
                pass


class TabellaOperatorie(QTableWidget):
    """QTableWidget con supporto drop: sposta tra giorni o scambia nello stesso giorno."""

    operazione_spostata  = Signal(int, int, int)  # src_col, src_op_idx, dst_col
    operazione_scambiata = Signal(int, int, int)  # col, src_op_idx, dst_op_idx

    def __init__(self):
        super().__init__()
        self._drag_over_col = -1
        self._drop_targets: dict = {}  # col → prima riga vuota (per move cross-giorno)
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self._cell_overlay = QFrame(self.viewport())
        self._cell_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._cell_overlay.hide()
        self._cell_overlay_mode = ""  # "move" | "swap"

    def set_drop_targets(self, targets: dict):
        self._drop_targets = targets

    def _decode_drag_payload(self, event) -> tuple[int, int] | None:
        mime = event.mimeData()
        if not mime.hasFormat(_OPERATION_MIME_TYPE):
            return None
        try:
            raw = bytes(mime.data(_OPERATION_MIME_TYPE)).decode("ascii")
            fields = raw.split(":")
            if len(fields) != 2:
                return None
            src_col, src_op_idx = map(int, fields)
        except (UnicodeDecodeError, ValueError):
            return None

        n_ops = self._drop_targets.get(src_col, 2) - 2
        if not (0 <= src_col < self.columnCount() and 0 <= src_op_idx < n_ops):
            return None
        return src_col, src_op_idx

    def _mostra_overlay(self, row: int, col: int, mode: str):
        """Posiziona e mostra l'overlay sulla cella (row, col)."""
        rect = self.visualRect(self.model().index(row, col))
        if not rect.isValid() or rect.isEmpty():
            self._cell_overlay.hide()
            return
        if mode != self._cell_overlay_mode:
            self._cell_overlay_mode = mode
            if mode == "swap":
                self._cell_overlay.setStyleSheet(
                    "background-color: rgba(234, 88, 12, 45);"
                    "border: 2px dashed rgba(234, 88, 12, 200);"
                    "border-radius: 6px;"
                )
            else:
                self._cell_overlay.setStyleSheet(
                    "background-color: rgba(59, 130, 246, 50);"
                    "border: 2px dashed rgba(59, 130, 246, 210);"
                    "border-radius: 6px;"
                )
        self._cell_overlay.setGeometry(rect.adjusted(3, 3, -3, -3))
        self._cell_overlay.show()
        self._cell_overlay.raise_()

    def _aggiorna_overlay(self, col: int, src_col: int, src_op_idx: int, cursor_y: int):
        if col < 0:
            self._cell_overlay.hide()
            return

        if col == src_col:
            target_row = self.rowAt(cursor_y)
            src_row = src_op_idx + 2
            n_ops = self._drop_targets.get(col, 2) - 2
            if (target_row >= 2
                    and target_row != src_row
                    and (target_row - 2) < n_ops):
                self._mostra_overlay(target_row, col, "swap")
            else:
                self._cell_overlay.hide()
        else:
            target_row = self._drop_targets.get(col, -1)
            if target_row < 0 or target_row >= self.rowCount():
                self._cell_overlay.hide()
                return
            self._mostra_overlay(target_row, col, "move")

    def dragEnterEvent(self, event):
        if self._decode_drag_payload(event) is None:
            event.ignore()
            return
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragMoveEvent(self, event):
        payload = self._decode_drag_payload(event)
        if payload is None:
            self._cell_overlay.hide()
            event.ignore()
            return
        pos = event.position().toPoint()
        col = self.columnAt(pos.x())
        if not 0 <= col < self.columnCount():
            self._cell_overlay.hide()
            event.ignore()
            return
        src_col, src_op_idx = payload
        self._drag_over_col = col
        self._aggiorna_overlay(col, src_col, src_op_idx, pos.y())
        event.setDropAction(Qt.DropAction.MoveAction)
        event.accept()

    def dragLeaveEvent(self, event):
        self._drag_over_col = -1
        self._cell_overlay.hide()
        super().dragLeaveEvent(event)

    def dropEvent(self, event):
        self._drag_over_col = -1
        self._cell_overlay.hide()
        payload = self._decode_drag_payload(event)
        if payload is None or not isinstance(event.source(), DraggableOperationFrame):
            event.ignore()
            return
        src_col, src_idx = payload

        pos = event.position().toPoint()
        dst_col = self.columnAt(pos.x())
        if not 0 <= dst_col < self.columnCount():
            event.ignore()
            return

        accepted = False
        if dst_col == src_col:
            target_row = self.rowAt(pos.y())
            n_ops = self._drop_targets.get(dst_col, 2) - 2
            src_row = src_idx + 2
            if (target_row >= 2
                    and target_row != src_row
                    and (target_row - 2) < n_ops):
                self.operazione_scambiata.emit(dst_col, src_idx, target_row - 2)
                accepted = True
        else:
            target_row = self._drop_targets.get(dst_col, -1)
            if 0 <= target_row < self.rowCount():
                self.operazione_spostata.emit(src_col, src_idx, dst_col)
                accepted = True

        if accepted:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()


class ViewSaleOperatorie(QWidget):
    DEFAULT_OPS = 5   # righe operazione visibili di default
    MIN_VISIBLE_OPS = 2   # sotto, la tabella scorre invece di spingere fuori i pulsanti
    ACTION_HEIGHT = 52
    MAX_OPS = 24      # 12 interventi per ciascuna delle due sale fisiche

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._month_mode = False

        self.current_max_ops = self.DEFAULT_OPS
        self.row_labels = (
            ["Giorno", "Specializzandi"]
            + [f"Op. {i+1}" for i in range(self.current_max_ops)]
        )

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

        titolo = QLabel("Sale Operatorie")
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

        sottotitolo = QLabel("Seleziona la modalità di accesso alla programmazione settimanale")
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
            "Consulta le settimane\nconvalidate in passato",
            "asset/images/scadenzario/icona_storico.png",
            "CardStorico",
        )
        self.btn_consultazione = self._crea_card(
            "Consultazione",
            "Rivedi il piano e convalida\nla settimana corrente",
            "asset/images/scadenzario/icona_corrente.png",
            "CardConsultazione",
        )
        self.btn_pianificazione = self._crea_card(
            "Pianificazione",
            "Gestisci il piano\nper le settimane future",
            "asset/images/scadenzario/icona_pianificazione.png",
            "CardPianificazione",
        )

        cards_layout.addWidget(self.btn_storico)
        cards_layout.addWidget(self.btn_consultazione)
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
        self.btn_indietro.setObjectName("BtnIndietroSaleOperatorie")
        self.btn_indietro.setFixedSize(150, 42)
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
        self.btn_mese_anno.setEnabled(False)
        self.btn_mese_anno.setFixedHeight(46)

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

        # Come nello Scadenzario: la versione si sceglie accanto al calendario che cambia.
        version_row = QHBoxLayout()
        version_row.setSpacing(12)
        version_label = QLabel("Versione:")
        version_label.setObjectName("LblCalendarTools")
        version_row.addWidget(version_label)
        self.combo_versione = QComboBox()
        self.combo_versione.setObjectName("ComboVersioneSale")
        self.combo_versione.setMinimumWidth(145)
        self.combo_versione.addItem("Previsto", CalendarVersion.PREVISTO)
        self.combo_versione.addItem("Effettivo", CalendarVersion.EFFETTIVO)
        self.combo_versione.setAccessibleName("Versione del calendario sale operatorie")
        version_row.addWidget(self.combo_versione)
        self.lbl_versione_status = QLabel()
        self.lbl_versione_status.setObjectName("LblCellDetail")
        self.lbl_versione_status.setWordWrap(True)
        self.lbl_versione_status.hide()
        version_row.addWidget(self.lbl_versione_status, 1)
        version_row.addStretch()  # tiene il menu a sinistra quando il messaggio è nascosto
        layout.addLayout(version_row)

        tools = QHBoxLayout()
        tools.setSpacing(8)
        lbl_vista = QLabel("Visualizzazione:")
        lbl_vista.setObjectName("LblCalendarTools")
        tools.addWidget(lbl_vista)

        self.btn_vista_settimana = QPushButton("Settimana")
        self.btn_vista_settimana.setObjectName("BtnCalendarTool")
        self.btn_vista_settimana.setCheckable(True)
        self.btn_vista_settimana.setChecked(True)
        self.btn_vista_settimana.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_vista_mese = QPushButton("Intero mese")
        self.btn_vista_mese.setObjectName("BtnCalendarTool")
        self.btn_vista_mese.setCheckable(True)
        self.btn_vista_mese.setCursor(Qt.CursorShape.PointingHandCursor)

        self.lbl_dettaglio_cella = QLabel(
            "La vista mensile usa le iniziali; fai click per aprire i dettagli."
        )
        self.lbl_dettaglio_cella.setObjectName("LblCellDetail")

        self.btn_esporta_pdf = QPushButton("Esporta PDF")
        self.btn_esporta_pdf.setObjectName("BtnCalendarExport")
        self.btn_esporta_pdf.setCursor(Qt.CursorShape.PointingHandCursor)

        tools.addWidget(self.btn_vista_settimana)
        tools.addWidget(self.btn_vista_mese)
        tools.addWidget(self.lbl_dettaglio_cella, 1)
        tools.addWidget(self.btn_esporta_pdf)
        layout.addLayout(tools)

        self.tabella = TabellaOperatorie()
        self.tabella.setRowCount(2 + self.current_max_ops)
        self.tabella.setVerticalHeaderLabels(self.row_labels)

        self.tabella.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabella.horizontalHeader().setSectionsClickable(False)
        self.tabella.horizontalHeader().setHighlightSections(False)

        self.tabella.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tabella.verticalHeader().setSectionsClickable(False)
        self.tabella.verticalHeader().setHighlightSections(False)

        self.tabella.setRowHeight(0, 46)   # Giorno
        self.tabella.setRowHeight(1, 60)   # Specializzandi
        for i in range(2, 2 + self.current_max_ops):
            self.tabella.setRowHeight(i, 82)

        self.tabella.setCornerButtonEnabled(False)
        self.tabella.setWordWrap(True)
        self.tabella.setAlternatingRowColors(False)

        QScroller.grabGesture(
            self.tabella.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )
        self.tabella.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)

        layout.addWidget(self.tabella, 1)

        self.btn_pianifica = QPushButton("PIANIFICA SETTIMANA")
        self.btn_pianifica.setObjectName("BtnPianifica")
        self.btn_pianifica.setVisible(False)

        self.btn_pulisci = QPushButton("PULISCI PIANO")
        self.btn_pulisci.setObjectName("BtnPulisci")
        self.btn_pulisci.setVisible(False)

        self.btn_crea_effettivo = QPushButton("CREA EFFETTIVO DAL PREVISTO CONVALIDATO")
        self.btn_crea_effettivo.setObjectName("BtnConvalida")
        self.btn_crea_effettivo.hide()

        self.btn_convalida = QPushButton("CONVALIDA SETTIMANA")
        self.btn_convalida.setObjectName("BtnConvalida")
        self.btn_convalida.setVisible(False)

        # Azioni su una riga sola: impilate superavano l'altezza di uno schermo da portatile.
        azioni = QHBoxLayout()
        azioni.setSpacing(12)
        for pulsante in (
            self.btn_pianifica, self.btn_pulisci, self.btn_crea_effettivo, self.btn_convalida,
        ):
            pulsante.setFixedHeight(self.ACTION_HEIGHT)
            pulsante.setCursor(Qt.CursorShape.PointingHandCursor)
            azioni.addWidget(pulsante, 1)
        layout.addLayout(azioni)
        layout.addStretch()  # lo spazio in più va sotto i pulsanti, non dentro la tabella

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
                Qt.TransformationMode.SmoothTransformation,
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

    def adatta_righe_operazioni(self, n_actual: int):
        """
        Ridimensiona le righe operazione (min DEFAULT_OPS, max MAX_OPS)
        e aggiorna l'altezza massima della tabella per evitare spazio bianco
        vuoto sotto l'ultima riga prima dei pulsanti.
        """
        n_display = max(self.DEFAULT_OPS, min(n_actual, self.MAX_OPS))

        if n_display != self.current_max_ops:
            self.current_max_ops = n_display
            self.tabella.setRowCount(n_display + 2)
            specialist_label = "Spec." if self._month_mode else "Specializzandi"
            labels = ["Giorno", specialist_label] + [f"Op. {i+1}" for i in range(n_display)]
            self.tabella.setVerticalHeaderLabels(labels)
        operation_height = 38 if self._month_mode else 82
        self.tabella.setRowHeight(0, 34 if self._month_mode else 46)
        self.tabella.setRowHeight(1, 44 if self._month_mode else 60)
        for i in range(2, n_display + 2):
            self.tabella.setRowHeight(i, operation_height)

        self._adatta_altezza_tabella()

    def _adatta_altezza_tabella(self):
        """Tutte le righe se c'è spazio, almeno MIN_VISIBLE_OPS interventi se lo schermo è basso.

        Il massimo evita lo spazio bianco sotto l'ultima riga; il minimo basso lascia la
        pagina dentro uno schermo da portatile: la tabella scorre, i pulsanti restano visibili.
        """
        h_header = self.tabella.horizontalHeader().height()
        if h_header <= 0:
            h_header = 42
        h_fisse = h_header + self.tabella.rowHeight(0) + self.tabella.rowHeight(1) + 4
        h_operazioni = [self.tabella.rowHeight(i) for i in range(2, self.tabella.rowCount())]
        self.tabella.setMinimumHeight(h_fisse + sum(h_operazioni[: self.MIN_VISIBLE_OPS]))
        self.tabella.setMaximumHeight(h_fisse + sum(h_operazioni))

    def crea_item_giorno(self, nome_giorno, is_festivo, is_oggi=False):
        display_name = nome_giorno[:1] if self._month_mode else nome_giorno
        item = QTableWidgetItem(display_name)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
        item.setFont(QFont("Segoe UI", 7 if self._month_mode else 11, QFont.Weight.Bold))
        item.setToolTip(nome_giorno)

        if is_oggi:
            item.setBackground(QColor("#f59e0b"))
            item.setForeground(QColor("#ffffff"))
        elif is_festivo:
            item.setBackground(QColor("#e2e8f0"))
            item.setForeground(QColor("#94a3b8"))
        else:
            item.setBackground(QColor(Qt.GlobalColor.transparent))
            item.setForeground(QColor("#475569"))
        return item

    def crea_item_cella(self, valore, is_inattivo, is_oggi=False, compact=False):
        display_value = valore
        if compact and valore:
            display_value = "\n".join(
                person_initials(line) for line in valore.splitlines() if line.strip()
            )
        item = QTableWidgetItem(display_value)
        item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        item.setData(Qt.ItemDataRole.UserRole, valore)
        if valore:
            item.setToolTip(valore)

        if is_inattivo:
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            item.setBackground(QColor("#fffbeb") if is_oggi else QColor(Qt.GlobalColor.transparent))
            item.setForeground(QColor(Qt.GlobalColor.transparent))
            item.setFont(QFont("Segoe UI", 10, QFont.Weight.Normal))
        else:
            item.setBackground(QColor("#fef3c7") if is_oggi else QColor(Qt.GlobalColor.transparent))
            item.setForeground(QColor("#1e293b"))
            item.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        return item

    def crea_widget_operazione(self, op: dict, is_oggi: bool = False, on_click=None,
                               draggable: bool = False, col: int = -1,
                               op_idx: int = -1,
                               compact: bool = False) -> DraggableOperationFrame:
        frame = DraggableOperationFrame()
        frame.setObjectName("CellaOperazioneOggi" if is_oggi else "CellaOperazione")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        if compact:
            layout = QVBoxLayout(frame)
            layout.setContentsMargins(1, 1, 1, 1)
            compact_name = person_initials(op.get("nome_paziente", "")) or "-"
            label = QLabel(compact_name)
            label.setObjectName("LblCompactOp")
            label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            label.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            layout.addWidget(label)
            details = " · ".join(
                value
                for value in (
                    op.get("nome_paziente", ""),
                    op.get("sala_operatoria", ""),
                    f"{op.get('ora_inizio', '')}-{op.get('ora_fine', '')}".strip("-"),
                )
                if value
            )
            frame.setToolTip(details)
            frame.set_on_click(on_click)
            frame.setup_drag(col, op_idx, False)
            if on_click:
                frame.setCursor(Qt.CursorShape.PointingHandCursor)
            return frame

        vl = QVBoxLayout(frame)
        vl.setContentsMargins(8, 6, 8, 6)
        vl.setSpacing(3)

        ora_row = QHBoxLayout()
        ora_row.setSpacing(6)
        # Senza spazi attorno al trattino: a 1280 px sala e orario stanno interi nella colonna.
        lbl_ora = QLabel(f"{op.get('ora_inizio','?')}–{op.get('ora_fine','?')}")
        lbl_ora.setObjectName("LblOraOp")
        lbl_ora.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        room_id = op.get("sala_operatoria", "")
        if room_id:
            badge_room = QLabel(room_id)
            badge_room.setObjectName("BadgeSalaOp")
            badge_room.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            ora_row.addWidget(badge_room)
        badge_dur = QLabel(f"{op.get('durata', '?')} min")
        badge_dur.setObjectName("BadgeDurataOp")
        badge_dur.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        ora_row.addWidget(lbl_ora)
        ora_row.addStretch()
        ora_row.addWidget(badge_dur)
        # La durata si ricava già dall'orario: è il badge che lascia spazio se la colonna è stretta.
        frame.set_badge_facoltativo(ora_row, badge_dur)

        lbl_nome = EtichettaAdattiva([op.get("nome_paziente", "—")])
        lbl_nome.setObjectName("LblNomePazOp")
        lbl_nome.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(6)

        interventi_list = op.get("interventi", [])
        codici = [i.get("codice", "") for i in interventi_list if i.get("codice")]
        if not codici and op.get("codice_intervento"):
            codici = [op["codice_intervento"]]
        if codici:
            lbl_codici = EtichettaAdattiva(varianti_codici(codici))
            lbl_codici.setObjectName("LblSubOp")
            lbl_codici.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            bottom_row.addWidget(lbl_codici, 1)  # prende lo spazio fino al badge complessità
        else:
            bottom_row.addStretch()

        cpx = op.get("complessita", "")
        if cpx:
            badge_cpx = QLabel(cpx)
            badge_cpx.setObjectName("BadgeComplessitaOp")
            badge_cpx.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            bottom_row.addWidget(badge_cpx)

        vl.addLayout(ora_row)
        vl.addWidget(lbl_nome)
        vl.addLayout(bottom_row)

        frame.set_on_click(on_click)
        frame.setup_drag(col, op_idx, draggable)
        if on_click or draggable:
            frame.setCursor(Qt.CursorShape.PointingHandCursor)

        return frame

    def set_month_mode(self, month_mode: bool) -> None:
        self._month_mode = month_mode
        self.tabella.setProperty("compact", month_mode)
        self.tabella.style().unpolish(self.tabella)
        self.tabella.style().polish(self.tabella)
        self.btn_vista_mese.setChecked(month_mode)
        self.btn_vista_settimana.setChecked(not month_mode)
        header = self.tabella.horizontalHeader()
        if month_mode:
            header.setMinimumSectionSize(20)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tabella.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            labels = ["Giorno", "Spec."] + [
                f"Op. {index + 1}" for index in range(self.current_max_ops)
            ]
        else:
            header.setMinimumSectionSize(80)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tabella.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
            labels = ["Giorno", "Specializzandi"] + [
                f"Op. {index + 1}" for index in range(self.current_max_ops)
            ]
        self.tabella.setVerticalHeaderLabels(labels)
        self.adatta_righe_operazioni(self.current_max_ops)
        self.tabella.viewport().update()
        header.viewport().update()

    def crea_widget_vuoto(self, is_oggi: bool = False, on_click=None) -> QFrame:
        frame = QFrame()
        if on_click:
            frame.setObjectName("SlotVuotoClickable")
            frame.setCursor(Qt.CursorShape.PointingHandCursor)
            vl = QVBoxLayout(frame)
            vl.setContentsMargins(0, 0, 0, 0)
            lbl = QLabel("+")
            lbl.setObjectName("LblSlotVuoto")
            lbl.setAlignment(Qt.AlignmentFlag.AlignCenter)
            lbl.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            vl.addWidget(lbl)
            frame.mousePressEvent = lambda e: on_click()
        else:
            frame.setObjectName("CellaVuotaOggi" if is_oggi else "CellaVuota")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        return frame

    def aggiorna_badge(self, modalita, stato, versione="Previsto"):
        colori_modalita = {
            "STORICO":        ("#334155", "#e2e8f0"),
            "CONSULTAZIONE":  ("#14532d", "#dcfce7"),
            "PIANIFICAZIONE": ("#1e3a8a", "#dbeafe"),
        }
        colori_stato = {
            "BOZZA":       ("#92400e", "#fef3c7"),
            "CONVALIDATO": ("#14532d", "#dcfce7"),
        }

        fg_m, bg_m = colori_modalita.get(modalita, ("#334155", "#e2e8f0"))
        self.lbl_modalita.setText(f"  {modalita} · {versione.upper()}  ")
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
        style_path = os.path.join(PROJECT_ROOT, "asset", "styles", "sale_operatorie.qss")
        register_icon_path()  # la freccia del menu Versione usa url(icons:...)
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "tabella"):
            self.tabella.viewport().update()
            self.tabella.horizontalHeader().viewport().update()
