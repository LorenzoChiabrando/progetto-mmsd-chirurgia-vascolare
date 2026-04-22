from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QComboBox, QSpinBox, QPushButton
)


class DialogMeseAnno(QDialog):
    """Dialog per la selezione di mese e anno. Usato da Scadenzario e Sale Operatorie."""

    def __init__(self, mesi_ita, mese_corrente, anno_corrente, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Vai a...")
        self.setFixedSize(300, 120)
        self.setStyleSheet("""
            QComboBox, QSpinBox { font-size: 16px; padding: 5px; }
            QPushButton {
                background-color: #0d6efd; color: white; font-weight: bold;
                border-radius: 5px; padding: 8px; font-size: 14px;
            }
            QPushButton:hover { background-color: #0b5ed7; }
        """)
        self._setup_ui(mesi_ita, mese_corrente, anno_corrente)

    def _setup_ui(self, mesi_ita, mese_corrente, anno_corrente):
        layout = QVBoxLayout(self)

        h_layout = QHBoxLayout()
        self.combo_mesi = QComboBox()
        self.combo_mesi.addItems(mesi_ita)
        self.combo_mesi.setCurrentIndex(mese_corrente - 1)

        self.spin_anno = QSpinBox()
        self.spin_anno.setRange(2020, 2050)
        self.spin_anno.setValue(anno_corrente)

        h_layout.addWidget(self.combo_mesi)
        h_layout.addWidget(self.spin_anno)
        layout.addLayout(h_layout)

        btn_layout = QHBoxLayout()
        btn_cancel = QPushButton("Annulla")
        btn_cancel.setStyleSheet("background-color: #6c757d;")
        btn_cancel.clicked.connect(self.reject)

        btn_ok = QPushButton("Conferma")
        btn_ok.clicked.connect(self.accept)

        btn_layout.addWidget(btn_cancel)
        btn_layout.addWidget(btn_ok)
        layout.addLayout(btn_layout)

    def get_selezione(self):
        """Restituisce (mese, anno) selezionati dall'utente."""
        return self.combo_mesi.currentIndex() + 1, self.spin_anno.value()
