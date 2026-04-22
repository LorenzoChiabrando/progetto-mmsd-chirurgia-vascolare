from PySide6.QtWidgets import QHeaderView
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QFont


class ColoredHeaderView(QHeaderView):
    """
    QHeaderView verticale con colori per sezione impostabili programmaticamente,
    senza interferenze dal QSS del tema Fusion.
    """

    def __init__(self, orientation, color_map: dict, parent=None):
        """
        color_map: {section_index: hex_color_string}
        """
        super().__init__(orientation, parent)
        self._color_map = color_map

    def paintSection(self, painter, rect, logical_index):
        painter.save()
        painter.setClipRect(rect)

        # Sfondo per sezione
        bg = QColor(self._color_map.get(logical_index, "#f8fafc"))
        painter.fillRect(rect, bg)

        # Bordi
        painter.setPen(QColor("#cbd5e1"))
        painter.drawLine(rect.right(), rect.top(), rect.right(), rect.bottom())
        painter.drawLine(rect.left(), rect.bottom(), rect.right(), rect.bottom())
        if logical_index == 0:
            painter.drawLine(rect.left(), rect.top(), rect.right(), rect.top())

        # Testo
        text = self.model().headerData(
            logical_index, self.orientation(), Qt.ItemDataRole.DisplayRole
        )
        if text:
            painter.setPen(QColor("#334155"))
            painter.setFont(QFont("Segoe UI", 12, QFont.Weight.Bold))
            painter.drawText(
                rect.adjusted(14, 0, -6, 0),
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft,
                str(text),
            )

        painter.restore()
