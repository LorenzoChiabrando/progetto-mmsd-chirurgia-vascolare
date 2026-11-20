"""Giorno corrente nei calendari: numero (o nome) del giorno in arancione nell'intestazione
e bordo scuro attorno alla sua colonna, senza colorare le celle.

Il giallo usato prima per la colonna si confondeva con il Giro Visite e spariva sotto le
celle già colorate; lo stesso criterio vale per Scadenzario e Sale Operatorie.
"""

from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QHeaderView, QTableView, QWidget

TODAY_HEADER_BACKGROUND = QColor("#f59e0b")
TODAY_HEADER_TEXT = QColor("#ffffff")
TODAY_BORDER = QColor("#1e293b")
TODAY_BORDER_WIDTH = 3


class IntestazioneGiorni(QHeaderView):
    """Intestazione orizzontale con la sezione del giorno corrente in arancione.

    Le altre sezioni restano disegnate dal foglio di stile.
    """

    def __init__(self, parent=None, *, font_px: int = 15) -> None:
        super().__init__(Qt.Orientation.Horizontal, parent)
        self._evidenziata: int | None = None
        self._font_px = font_px

    def imposta_evidenziata(self, sezione: int | None) -> None:
        if sezione != self._evidenziata:
            self._evidenziata = sezione
            self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
        if logical_index != self._evidenziata:
            super().paintSection(painter, rect, logical_index)
            return
        painter.save()
        painter.fillRect(rect, TODAY_HEADER_BACKGROUND)
        painter.setPen(QColor("#d97706"))
        painter.drawLine(rect.topRight(), rect.bottomRight())
        painter.drawLine(rect.bottomLeft(), rect.bottomRight())
        font = QFont(self.font())
        font.setPixelSize(self._font_px)
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(TODAY_HEADER_TEXT)
        testo = self.model().headerData(
            logical_index, self.orientation(), Qt.ItemDataRole.DisplayRole
        )
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, str(testo or ""))
        painter.restore()


class BordoColonna(QWidget):
    """Bordo attorno a una colonna della tabella, sopra celle e widget delle celle.

    Sta nel viewport della tabella, ne copre tutta l'area e lascia passare il mouse.
    Va richiamato :meth:`imposta_colonna` dopo aver riempito la tabella: porta il bordo
    sopra i widget delle celle appena creati.
    """

    def __init__(self, tabella: QTableView) -> None:
        super().__init__(tabella.viewport())
        self._tabella = tabella
        self._colonna: int | None = None
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAttribute(Qt.WidgetAttribute.WA_NoSystemBackground, True)
        self._osservatore = _Ridimensionamento(self._aggiorna, tabella.viewport())
        tabella.viewport().installEventFilter(self._osservatore)
        tabella.horizontalScrollBar().valueChanged.connect(self._aggiorna)
        tabella.verticalScrollBar().valueChanged.connect(self._aggiorna)
        tabella.horizontalHeader().sectionResized.connect(self._aggiorna)
        tabella.verticalHeader().sectionResized.connect(self._aggiorna)
        self.hide()

    def imposta_colonna(self, colonna: int | None) -> None:
        self._colonna = colonna
        self._aggiorna()

    def _aggiorna(self, *_args) -> None:
        self.setGeometry(self._tabella.viewport().rect())
        self.setVisible(self._colonna is not None)
        self.raise_()
        self.update()

    def paintEvent(self, _event) -> None:
        tabella, colonna = self._tabella, self._colonna
        modello = tabella.model()
        if colonna is None or modello is None or not 0 <= colonna < modello.columnCount():
            return
        righe = modello.rowCount()
        if not righe:
            return
        x = tabella.columnViewportPosition(colonna)
        alto = tabella.rowViewportPosition(0)
        basso = tabella.rowViewportPosition(righe - 1) + tabella.rowHeight(righe - 1)
        mezzo = TODAY_BORDER_WIDTH / 2
        painter = QPainter(self)
        penna = QPen(TODAY_BORDER, TODAY_BORDER_WIDTH)
        penna.setJoinStyle(Qt.PenJoinStyle.MiterJoin)
        painter.setPen(penna)
        painter.drawRect(QRectF(
            x + mezzo, alto + mezzo,
            tabella.columnWidth(colonna) - TODAY_BORDER_WIDTH,
            basso - alto - TODAY_BORDER_WIDTH,
        ))


class _Ridimensionamento(QObject):
    """Richiama ``callback`` quando il viewport cambia dimensione."""

    def __init__(self, callback, parent) -> None:
        super().__init__(parent)
        self._callback = callback

    def eventFilter(self, obj, event) -> bool:
        if event.type() == QEvent.Type.Resize:
            self._callback()
        return False
