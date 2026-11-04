import os
from src.data_paths import PROJECT_ROOT
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QPushButton,
    QTableWidget, QTableWidgetItem, QHeaderView, QScroller,
    QStackedWidget, QLabel, QSizePolicy,
    QGraphicsOpacityEffect, QFrame, QApplication,
)
from PySide6.QtCore import QByteArray, QMimeData, Qt, Signal
from PySide6.QtGui import QPixmap, QColor, QFont, QDrag, QPainter

from src.calendar_presentation import ROOM_COLORS, person_initials
from src.calendar_versions import CalendarVersion
from src.views.components.calendar_toolbar import (
    BarraStrumenti, SceltaSegmentata, StatoPeriodo, etichetta_info, pulsante_esporta_pdf,
    riga_periodo, segmentato,
)
from src.views.components.colored_header_view import ColoredHeaderView
from src.views.components.modal_dialog import register_icon_path
from src.views.components.mode_card import CardModalita
from src.views.components.optimization_summary import RiepilogoOttimizzazione
from src.views.components.section_header import BandaSezione, pagina_scorrevole


_OPERATION_MIME_TYPE = "application/x-mmsd-operation"

# Titolo e significato di ogni stato del settimana, mostrati nella fascia sotto il titolo.
_TESTI_STATO = {
    "BOZZA": ("Settimana in bozza", "non ancora convalidata: si può ancora modificare"),
    "CONVALIDATO": ("Settimana convalidata", "definitiva, in sola lettura"),
    "ASSENTE": ("Effettivo non ancora creato", ""),
    "RIEPILOGO": ("Riepilogo del mese", "sola consultazione: per modificare passa a Settimana"),
}

# Codice, titolo, descrizione (card e banda) e icona SVG della card.
_MODALITA = (
    ("STORICO", "Storico",
     "Consulta le settimane\nconvalidate in passato",
     "modalita-storico.svg"),
    ("CONSULTAZIONE", "Consultazione",
     "Rivedi il piano e convalida\nla settimana corrente",
     "modalita-consultazione.svg"),
    ("PIANIFICAZIONE", "Pianificazione",
     "Gestisci il piano\nper le settimane future",
     "modalita-pianificazione.svg"),
)


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


def etichetta_durata(durata) -> str:
    """Durata per il badge della scheda: «45 min» sotto l'ora, poi «1h», «1h30», «2h05».

    Da un'ora in su il testo non è mai più largo di «90 min»: il badge compare in ogni
    colonna dove compariva già la durata di un intervento di un'ora e mezza.
    """
    if isinstance(durata, bool) or not isinstance(durata, int) or durata < 60:
        return f"{durata} min"
    ore, minuti = divmod(durata, 60)
    return f"{ore}h{minuti:02d}" if minuti else f"{ore}h"


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
    """QTableWidget con supporto drop: sposta tra giorni o scambia nello stesso giorno.

    Le righe sono divise in blocchi per sala: un intervento si scambia solo con uno della
    stessa sala e, spostato in un altro giorno, va in coda alla sua sala. La mappa delle
    righe arriva dal controller con :meth:`imposta_mappa`.
    """

    operazione_spostata  = Signal(int, int, int)  # src_col, src_op_idx, dst_col
    operazione_scambiata = Signal(int, int, int)  # col, src_op_idx, dst_op_idx

    def __init__(self):
        super().__init__()
        self._drag_over_col = -1
        # col -> {"interventi": {riga: (sala, indice)}, "libere": {sala: riga per il drop}}
        self._mappa: dict[int, dict] = {}
        self.setAcceptDrops(True)
        self.viewport().setAcceptDrops(True)

        self._cell_overlay = QFrame(self.viewport())
        self._cell_overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self._cell_overlay.hide()
        self._cell_overlay_mode = ""  # "move" | "swap"

    def imposta_mappa(self, mappa: dict[int, dict]) -> None:
        """Righe di ogni colonna; vuota quando il calendario non si può modificare."""
        self._mappa = mappa

    def _sala_e_riga(self, col: int, op_idx: int) -> tuple[str, int] | None:
        for riga, (sala, indice) in self._mappa.get(col, {}).get("interventi", {}).items():
            if indice == op_idx:
                return sala, riga
        return None

    def azione_drop(
        self, src_col: int, src_idx: int, col: int, riga: int
    ) -> tuple[str, int, int] | None:
        """Che cosa farebbe il rilascio sulla cella ``(riga, col)``.

        ``("scambia", indice di destinazione, riga)`` nello stesso giorno e nella stessa
        sala; ``("sposta", -1, riga libera della sala)`` in un altro giorno; ``None``
        altrimenti (altra sala, stessa cella, sala piena).
        """
        sorgente = self._sala_e_riga(src_col, src_idx)
        if sorgente is None or col not in self._mappa:
            return None
        sala, riga_sorgente = sorgente
        if col == src_col:
            destinazione = self._mappa[col]["interventi"].get(riga)
            if destinazione is None or riga == riga_sorgente or destinazione[0] != sala:
                return None
            return "scambia", destinazione[1], riga
        riga_libera = self._mappa[col]["libere"].get(sala)
        if riga_libera is None:
            return None
        return "sposta", -1, riga_libera

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

        if self._sala_e_riga(src_col, src_op_idx) is None:
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
        azione = self.azione_drop(src_col, src_op_idx, col, self.rowAt(cursor_y))
        if azione is None:
            self._cell_overlay.hide()
            return
        tipo, _indice, riga = azione
        self._mostra_overlay(riga, col, "swap" if tipo == "scambia" else "move")

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
        azione = self.azione_drop(src_col, src_idx, dst_col, self.rowAt(pos.y()))
        if azione is not None:
            tipo, dst_idx, _riga = azione
            if tipo == "scambia":
                self.operazione_scambiata.emit(dst_col, src_idx, dst_idx)
            else:
                self.operazione_spostata.emit(src_col, src_idx, dst_col)
            accepted = True

        if accepted:
            event.setDropAction(Qt.DropAction.MoveAction)
            event.accept()
        else:
            event.ignore()


class ViewSaleOperatorie(QWidget):
    ACTION_HEIGHT = 52

    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self._month_mode = False
        # Blocchi di righe (sala, righe intervento) e, per sala, la posizione nella
        # tabella: (riga dello specializzando, prima riga intervento, numero di righe).
        self._blocchi: list[tuple[str, int]] = [(sala, 2) for sala in ROOM_COLORS]
        self.righe_sala: dict[str, tuple[int, int, int]] = {}

        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Fuori dai margini della pagina calendario, così occupa tutta la larghezza.
        self.banda = BandaSezione(
            "Sale Operatorie",
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

        card = {
            codice: CardModalita(codice, titolo, descrizione, icona)
            for codice, titolo, descrizione, icona in _MODALITA
        }
        self.btn_storico = card["STORICO"]
        self.btn_consultazione = card["CONSULTAZIONE"]
        self.btn_pianificazione = card["PIANIFICAZIONE"]

        cards_layout.addWidget(self.btn_storico)
        cards_layout.addWidget(self.btn_consultazione)
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
        self.btn_mese_anno.setEnabled(False)
        self.btn_mese_anno.setFixedHeight(46)

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
        self.lbl_versione_status = self.stato_periodo.lbl_dettaglio  # messaggi del controller
        layout.addWidget(self.stato_periodo)

        # Esito dell'ultima pianificazione automatica (nascosto se la settimana non ne ha).
        self.riepilogo_ottimizzazione = RiepilogoOttimizzazione()
        layout.addWidget(self.riepilogo_ottimizzazione)

        # Stessa barra dello Scadenzario: filtri a sinistra, azioni a destra, note sotto.
        barra = self.barra_filtri = BarraStrumenti()

        # Pulsanti e non menu a tendina: la versione su cui si lavora deve vedersi subito.
        self.scelta_versione = SceltaSegmentata()
        self.scelta_versione.setProperty("evidenza", True)
        self.scelta_versione.addItem("Previsto", CalendarVersion.PREVISTO)
        self.scelta_versione.addItem("Effettivo", CalendarVersion.EFFETTIVO)
        self.scelta_versione.setAccessibleName("Versione del calendario sale operatorie")
        barra.aggiungi_gruppo("Versione", self.scelta_versione)

        self.scelta_sala = SceltaSegmentata()
        self.scelta_sala.addItem("Tutte le sale", None)
        self.scelta_sala.addItem("OR-1", "OR-1")
        self.scelta_sala.addItem("OR-2", "OR-2")
        self.scelta_sala.setAccessibleName("Sala operatoria da visualizzare")
        barra.aggiungi_gruppo("Sala", self.scelta_sala)

        self.btn_vista_settimana = QPushButton("Settimana")
        self.btn_vista_mese = QPushButton("Intero mese")
        self.gruppo_visualizzazione = segmentato(self.btn_vista_settimana, self.btn_vista_mese)
        barra.aggiungi_gruppo("Visualizzazione", self.gruppo_visualizzazione)
        self.btn_vista_settimana.setChecked(True)

        self.btn_esporta_pdf = pulsante_esporta_pdf("#6f42c1")
        barra.aggiungi_azione(self.btn_esporta_pdf)

        self.lbl_dettaglio_cella = etichetta_info(
            "La vista mensile usa le iniziali; fai click per aprire i dettagli."
        )
        barra.aggiungi_info(self.lbl_dettaglio_cella, 1)
        # Le Sale si consultano solo per settimana: la scelta «Settimana / Intero mese» e
        # la nota sulla vista mensile non si mostrano. Pulsanti, segnali e vista mensile
        # restano nel codice (imposta_visualizzazione("MESE") funziona ancora).
        barra.imposta_gruppo_visibile(self.gruppo_visualizzazione, False)
        barra.mostra_riga_info(False)
        layout.addWidget(barra)

        self.tabella = TabellaOperatorie()

        self.tabella.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.tabella.horizontalHeader().setSectionsClickable(False)
        self.tabella.horizontalHeader().setHighlightSections(False)

        # Intestazioni di riga colorate per sala, come nello Scadenzario mensile.
        self._intestazioni_righe = ColoredHeaderView(
            Qt.Orientation.Vertical, {}, self.tabella, font_size=9
        )
        self.tabella.setVerticalHeader(self._intestazioni_righe)
        self.tabella.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Fixed)
        self.tabella.verticalHeader().setSectionsClickable(False)
        self.tabella.verticalHeader().setHighlightSections(False)
        self.imposta_blocchi(self._blocchi)

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


    def imposta_blocchi(self, blocchi: list[tuple[str, int]]) -> None:
        """Righe della tabella: «Giorno», poi un blocco per sala.

        Ogni blocco ha la riga dello specializzando di turno in quella sala e ``righe``
        righe per gli interventi, con i colori della sala (:data:`ROOM_COLORS`).
        Le posizioni finiscono in :attr:`righe_sala`.
        """
        self._blocchi = [(sala, max(1, righe)) for sala, righe in blocchi]
        self.righe_sala = {}
        etichette = ["Giorno"]
        colori = {0: "#f8fafc"}
        riga = 1
        for sala, righe in self._blocchi:
            tinte = ROOM_COLORS[sala]
            self.righe_sala[sala] = (riga, riga + 1, righe)
            etichette.append(sala if self._month_mode else f"Sala {sala}")
            colori[riga] = tinte["intestazione"]
            for numero in range(1, righe + 1):
                etichette.append(f"Op. {numero}")
                colori[riga + numero] = tinte["etichetta"]
            riga += 1 + righe
        self.tabella.setRowCount(riga)
        self.tabella.setVerticalHeaderLabels(etichette)
        self._intestazioni_righe.set_color_map(colori)
        self.tabella.setRowHeight(0, 34 if self._month_mode else 46)
        for intestazione, prima, righe in self.righe_sala.values():
            self.tabella.setRowHeight(intestazione, 30 if self._month_mode else 40)
            for numero in range(righe):
                self.tabella.setRowHeight(prima + numero, 38 if self._month_mode else 82)
        self._adatta_altezza_tabella()

    def _adatta_altezza_tabella(self):
        """La tabella è alta esattamente quanto tutte le sue righe.

        Niente barra di scorrimento verticale nel calendario e niente spazio bianco sotto
        l'ultima riga: se lo schermo è basso scorre la pagina intera.
        """
        altezza = (
            self.tabella.horizontalHeader().sizeHint().height()
            + sum(self.tabella.rowHeight(riga) for riga in range(self.tabella.rowCount()))
            + 2 * self.tabella.frameWidth()
        )
        self.tabella.setFixedHeight(altezza)

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

    def crea_item_cella(self, valore, is_inattivo, is_oggi=False, compact=False, sala=None):
        """Cella dello specializzando di turno, con il colore della sala.

        ``is_oggi`` resta per compatibilità: il giorno corrente si vede già
        nell'intestazione, e il giallo su celle senza pazienti dava fastidio.
        """
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
            item.setBackground(QColor(Qt.GlobalColor.transparent))
            item.setForeground(QColor(Qt.GlobalColor.transparent))
            item.setFont(QFont("Segoe UI", 10, QFont.Weight.Normal))
        else:
            sfondo = ROOM_COLORS[sala]["etichetta"] if sala in ROOM_COLORS else None
            item.setBackground(QColor(sfondo) if sfondo else QColor(Qt.GlobalColor.transparent))
            item.setForeground(QColor("#1e293b"))
            item.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
        return item

    def crea_widget_operazione(self, op: dict, is_oggi: bool = False, on_click=None,
                               draggable: bool = False, col: int = -1,
                               op_idx: int = -1,
                               compact: bool = False,
                               sala: str | None = None) -> DraggableOperationFrame:
        frame = DraggableOperationFrame()
        frame.setObjectName("CellaOperazioneOggi" if is_oggi else "CellaOperazione")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        frame.setProperty("sala", sala or "")  # bordo sinistro nel colore della sala

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
            badge_room.setProperty("sala", room_id)
            badge_room.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            ora_row.addWidget(badge_room)
        badge_dur = QLabel(etichetta_durata(op.get("durata", "?")))
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
        else:
            header.setMinimumSectionSize(80)
            header.setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
            self.tabella.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.imposta_blocchi(self._blocchi)
        self.tabella.viewport().update()
        header.viewport().update()

    def crea_widget_vuoto(self, is_oggi: bool = False, on_click=None, sala=None) -> QFrame:
        """Cella senza intervento: con il colore della sala, anche nel giorno corrente.

        ``is_oggi`` resta per compatibilità: il giorno corrente è già evidenziato
        nell'intestazione, il giallo sulle celle vuote confondeva.
        """
        frame = QFrame()
        frame.setProperty("sala", sala or "")  # sfondo nel colore della sala
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
            frame.setObjectName("CellaVuota")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        return frame

    def aggiorna_badge(self, modalita, stato, versione="Previsto"):
        """Aggiorna la banda della modalità e la fascia dello stato della settimana.

        La versione si legge nei pulsanti Versione del pannello dei filtri.
        """
        self.banda.imposta_modalita(modalita)
        self.stato_periodo.imposta_stato(stato)
        # In Pianificazione esiste solo il Previsto: la scelta della versione non compare.
        self.barra_filtri.imposta_gruppo_visibile(
            self.scelta_versione, modalita != "PIANIFICAZIONE"
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
