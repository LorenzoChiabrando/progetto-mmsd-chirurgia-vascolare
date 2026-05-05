from PySide6.QtWidgets import QStyledItemDelegate, QComboBox, QTableWidget
from PySide6.QtCore import Qt, QTimer


class ComboBoxDelegate(QStyledItemDelegate):
    """Delegate semplice con lista statica (usato per Tipo Guardia)."""

    def __init__(self, items, parent=None):
        super().__init__(parent)
        self.items = items

    def createEditor(self, parent, option, index):
        editor = QComboBox(parent)
        editor.addItem("-")
        editor.addItems(self.items)
        editor.setMaxVisibleItems(5)
        editor.activated.connect(lambda: self.commit_and_close(editor))
        return editor

    def setEditorData(self, editor: QComboBox, index):
        cell_text = index.model().data(index, Qt.ItemDataRole.EditRole)
        if not cell_text or cell_text == "-":
            editor.setCurrentIndex(0)
        else:
            i = editor.findText(cell_text)
            editor.setCurrentIndex(i if i >= 0 else 0)
        QTimer.singleShot(50, editor.showPopup)

    def setModelData(self, editor: QComboBox, model, index):
        text = editor.currentText()
        model.setData(index, "" if text == "-" else text, Qt.ItemDataRole.EditRole)

    def commit_and_close(self, editor: QComboBox):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)


class SmartComboBoxDelegate(QStyledItemDelegate):
    """
    Delegate per specializzandi: al momento dell'apertura filtra dinamicamente
    la lista escludendo chi è già assegnato in un'altra riga della stessa
    colonna (stesso giorno). Selezionare "-" libera lo slot.
    """

    def __init__(self, items: list, table: QTableWidget, parent=None):
        super().__init__(parent)
        self.items = items
        self._items_set = set(items)   # lookup O(1)
        self.table = table

    def _item_effettivo(self, r, col):
        """
        Restituisce l'item che copre visivamente la cella (r, col),
        tenendo conto degli span di colonna (es. Giro Visite).
        """
        item = self.table.item(r, col)
        if item is not None:
            return item
        # Cerca a sinistra una cella con span che include col
        for c in range(col - 1, -1, -1):
            if self.table.columnSpan(r, c) + c > col:
                return self.table.item(r, c)
        return None

    def createEditor(self, parent, option, index):
        riga = index.row()
        colonna = index.column()

        # Specializzandi già occupati in altre righe della stessa colonna
        # (usa _item_effettivo per gestire le celle con span, es. Giro Visite)
        usati = set()
        for r in range(self.table.rowCount()):
            if r == riga:
                continue
            item = self._item_effettivo(r, colonna)
            if item:
                val = item.text().strip()
                if val and val in self._items_set:
                    usati.add(val)

        # Valore attuale della cella (deve sempre comparire nel combo)
        valore_corrente = ""
        item_corrente = self.table.item(riga, colonna)
        if item_corrente:
            valore_corrente = item_corrente.text().strip()

        disponibili = [s for s in self.items if s not in usati or s == valore_corrente]

        editor = QComboBox(parent)
        editor.addItem("-")
        editor.addItems(disponibili)
        editor.setMaxVisibleItems(6)
        editor.activated.connect(lambda: self.commit_and_close(editor))
        return editor

    def setEditorData(self, editor: QComboBox, index):
        cell_text = index.model().data(index, Qt.ItemDataRole.EditRole)
        if not cell_text or cell_text == "-":
            editor.setCurrentIndex(0)
        else:
            i = editor.findText(cell_text)
            editor.setCurrentIndex(i if i >= 0 else 0)
        QTimer.singleShot(50, editor.showPopup)

    def setModelData(self, editor: QComboBox, model, index):
        text = editor.currentText()
        model.setData(index, "" if text == "-" else text, Qt.ItemDataRole.EditRole)

    def commit_and_close(self, editor: QComboBox):
        self.commitData.emit(editor)
        self.closeEditor.emit(editor, QStyledItemDelegate.EndEditHint.NoHint)
