from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QSpinBox, QVBoxLayout

from src.views.components.modal_dialog import ModalDialog


class DialogMeseAnno(ModalDialog):
    """Dialog per la selezione di mese e anno del calendario."""

    def __init__(self, mesi_ita, mese_corrente, anno_corrente, parent=None, section="scadenzario"):
        super().__init__(
            "Vai al mese",
            "Scegli il mese e l'anno da visualizzare.",
            section=section,
            parent=parent,
        )
        self.resize(460, 0)
        self._setup_ui(mesi_ita, mese_corrente, anno_corrente)

    def _setup_ui(self, mesi_ita, mese_corrente, anno_corrente):
        row = QHBoxLayout()
        row.setSpacing(12)

        self.combo_mesi = QComboBox()
        self.combo_mesi.setObjectName("ComboDialog")
        self.combo_mesi.addItems(mesi_ita)
        self.combo_mesi.setCurrentIndex(mese_corrente - 1)
        self.combo_mesi.setFixedHeight(44)

        self.spin_anno = QSpinBox()
        self.spin_anno.setObjectName("InputDialog")
        self.spin_anno.setRange(2020, 2050)
        self.spin_anno.setValue(anno_corrente)
        self.spin_anno.setFixedHeight(44)

        row.addLayout(self._campo("MESE", self.combo_mesi), 2)
        row.addLayout(self._campo("ANNO", self.spin_anno), 1)
        self.body.addLayout(row)

        btn_cancel = self.make_button("Annulla", "secondary")
        btn_cancel.clicked.connect(self.reject)
        btn_ok = self.make_button("Vai", "primary")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self.accept)
        self.add_footer(btn_cancel, btn_ok)

    @staticmethod
    def _campo(etichetta, widget):
        group = QVBoxLayout()
        group.setSpacing(4)
        label = QLabel(etichetta)
        label.setObjectName("LblCampo")
        group.addWidget(label)
        group.addWidget(widget)
        return group

    def get_selezione(self):
        """Restituisce (mese, anno) selezionati dall'utente."""
        return self.combo_mesi.currentIndex() + 1, self.spin_anno.value()
