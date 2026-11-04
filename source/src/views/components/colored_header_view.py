from PySide6.QtWidgets import QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont


class ColoredHeaderView(QHeaderView):
    """
    QHeaderView verticale con colori per sezione impostabili programmaticamente,
    senza interferenze dal QSS del tema Fusion.
    """

    def __init__(self, orientation, color_map: dict, parent=None, *, font_size: int = 12):
        """
        color_map: {section_index: hex_color_string}; font_size in punti.
        """
        super().__init__(orientation, parent)
        self._color_map = color_map
        self._font_size = font_size

    def set_color_map(self, color_map: dict) -> None:
        """Sostituisce i colori, per le tabelle che cambiano righe (es. blocchi per sala)."""
        self._color_map = dict(color_map)
        self.viewport().update()

    def paintSection(self, painter, rect, logical_index):
        painter.save()
        painter.setClipRect(rect)

        bg = QColor(self._color_map.get(logical_index, "#f8fafc"))
        painter.fillRect(rect, bg)

        painter.setPen(QColor("#cbd5e1"))
        painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        if logical_index == 0:
            painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())

        text = self.model().headerData(
            logical_index, self.orientation(), Qt.ItemDataRole.DisplayRole
        )
        if text:
            painter.setPen(QColor("#334155"))
            painter.setFont(QFont("Segoe UI", self._font_size, QFont.Weight.Bold))
            painter.drawText(
                rect.adjusted(14, 0, -6, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(text),
            )

        painter.restore()
