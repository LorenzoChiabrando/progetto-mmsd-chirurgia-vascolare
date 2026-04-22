import os
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QLineEdit, QComboBox, QPushButton, QMessageBox, QFrame
)
from PySide6.QtCore import Qt


class DialogNuovoSpecializzando(QDialog):
    """
    Dialog per aggiungere o modificare uno specializzando.
    Se spec_dati è fornito, si apre in modalità modifica con i campi pre-compilati.
    """
    def __init__(self, parent=None, spec_dati=None):
        super().__init__(parent)
        self._spec_dati  = spec_dati
        self._edit_mode  = spec_dati is not None

        self.setWindowTitle("Modifica Specializzando" if self._edit_mode else "Nuovo Specializzando")
        self.setMinimumWidth(500)
        self.setSizeGripEnabled(False)
        self.setup_ui()
        if self._edit_mode:
            self._precompila()
        self.load_styles()

    def setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(35, 35, 35, 35)
        layout.setSpacing(0)

        # Titolo
        titolo_text = "Modifica Specializzando" if self._edit_mode else "Nuovo Specializzando"
        lbl_titolo = QLabel(titolo_text)
        lbl_titolo.setObjectName("TitoloDialog")
        layout.addWidget(lbl_titolo)

        sub_text = (
            "Modifica i dati anagrafici dello specializzando."
            if self._edit_mode else
            "Compila i dati anagrafici per aggiungere uno specializzando al sistema."
        )
        lbl_sub = QLabel(sub_text)
        lbl_sub.setObjectName("SottoTitoloDialog")
        lbl_sub.setWordWrap(True)
        layout.addWidget(lbl_sub)

        # Separatore
        sep = QFrame()
        sep.setObjectName("SeparatoreDialog")
        sep.setFixedHeight(1)
        layout.addSpacing(18)
        layout.addWidget(sep)
        layout.addSpacing(18)

        # Campi del form
        _campi = [
            ("Matricola *",       "input_matricola", False, None),
            ("Nome *",            "input_nome",      False, None),
            ("Cognome *",         "input_cognome",   False, None),
            ("Livello Formativo", "combo_livello",   True,  ["Junior", "Senior"]),
            ("Sede Attuale",      "combo_stato",     True,  ["Molinette", "Altra Sede", "Storico"]),
        ]

        for label_text, attr_name, is_combo, items in _campi:
            lbl = QLabel(label_text)
            lbl.setObjectName("LblCampo")
            layout.addWidget(lbl)
            layout.addSpacing(4)

            if is_combo:
                widget = QComboBox()
                widget.setObjectName("ComboDialog")
                widget.addItems(items)
            else:
                widget = QLineEdit()
                widget.setObjectName("InputDialog")
                widget.setPlaceholderText(label_text.replace(" *", ""))

            widget.setFixedHeight(44)
            layout.addWidget(widget)
            layout.addSpacing(12)
            setattr(self, attr_name, widget)

        layout.addSpacing(8)

        # Bottoni
        btn_row = QHBoxLayout()
        btn_row.setSpacing(14)

        self.btn_annulla = QPushButton("Annulla")
        self.btn_annulla.setObjectName("BtnAnnullaDialog")
        self.btn_annulla.setFixedHeight(46)
        self.btn_annulla.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_annulla.clicked.connect(self.reject)

        salva_text = "Salva Modifiche" if self._edit_mode else "Salva Specializzando"
        self.btn_salva = QPushButton(salva_text)
        self.btn_salva.setObjectName("BtnSalvaDialog")
        self.btn_salva.setFixedHeight(46)
        self.btn_salva.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_salva.clicked.connect(self.valida_e_salva)

        btn_row.addWidget(self.btn_annulla)
        btn_row.addWidget(self.btn_salva, stretch=2)
        layout.addLayout(btn_row)

    def _precompila(self):
        """Pre-compila i campi con i dati dello specializzando esistente."""
        self.input_matricola.setText(self._spec_dati.get("matricola", ""))
        self.input_nome.setText(self._spec_dati.get("nome", ""))
        self.input_cognome.setText(self._spec_dati.get("cognome", ""))

        for combo, chiave in [(self.combo_livello, "livello"), (self.combo_stato, "stato")]:
            idx = combo.findText(self._spec_dati.get(chiave, ""))
            if idx >= 0:
                combo.setCurrentIndex(idx)

    def valida_e_salva(self):
        matricola = self.input_matricola.text().strip()
        nome      = self.input_nome.text().strip()
        cognome   = self.input_cognome.text().strip()

        if not matricola or not nome or not cognome:
            QMessageBox.warning(
                self, "Campi Incompleti",
                "Attenzione: Nome, Cognome e Matricola sono campi obbligatori."
            )
            return
        self.accept()

    def get_dati(self):
        return {
            "matricola": self.input_matricola.text().strip(),
            "nome":      self.input_nome.text().strip(),
            "cognome":   self.input_cognome.text().strip(),
            "livello":   self.combo_livello.currentText(),
            "stato":     self.combo_stato.currentText(),
        }

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "libretto.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
