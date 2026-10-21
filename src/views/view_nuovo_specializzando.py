from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit

from src.views.components import messages
from src.views.components.modal_dialog import ModalDialog


class DialogNuovoSpecializzando(ModalDialog):
    """
    Dialog per aggiungere o modificare uno specializzando.
    Se spec_dati è fornito, si apre in modalità modifica con i campi pre-compilati.
    """
    def __init__(self, parent=None, spec_dati=None):
        self._spec_dati  = spec_dati
        self._edit_mode  = spec_dati is not None
        super().__init__(
            "Modifica Specializzando" if self._edit_mode else "Nuovo Specializzando",
            (
                "Modifica i dati anagrafici dello specializzando."
                if self._edit_mode else
                "Compila i dati anagrafici per aggiungere uno specializzando al sistema."
            ),
            section="libretto",
            parent=parent,
        )
        self.resize(520, 0)
        self.setSizeGripEnabled(False)
        self.setup_ui()
        if self._edit_mode:
            self._precompila()

    def setup_ui(self):
        layout = self.body
        layout.setSpacing(0)

        _campi = [
            ("MATRICOLA *",       "input_matricola", False, None),
            ("NOME *",            "input_nome",      False, None),
            ("COGNOME *",         "input_cognome",   False, None),
            (
                "LIVELLO FORMATIVO",
                "combo_livello",
                True,
                ["Junior", "Intermediate", "Senior"],
            ),
            ("SEDE ATTUALE",      "combo_stato",     True,  ["Molinette", "Altra Sede", "Storico"]),
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
                widget.setPlaceholderText(label_text.replace(" *", "").capitalize())

            widget.setFixedHeight(44)
            layout.addWidget(widget)
            layout.addSpacing(12)
            setattr(self, attr_name, widget)

        self.btn_annulla = self.make_button("Annulla", "secondary")
        self.btn_annulla.clicked.connect(self.reject)

        salva_text = "Salva Modifiche" if self._edit_mode else "Salva Specializzando"
        self.btn_salva = self.make_button(salva_text, "primary")
        self.btn_salva.setDefault(True)
        self.btn_salva.clicked.connect(self.valida_e_salva)

        self.add_footer(self.btn_annulla, self.btn_salva)

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
            messages.show_message(
                self,
                "Campi Incompleti",
                "Attenzione: Nome, Cognome e Matricola sono campi obbligatori.",
                section="libretto",
                kind="warning",
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
