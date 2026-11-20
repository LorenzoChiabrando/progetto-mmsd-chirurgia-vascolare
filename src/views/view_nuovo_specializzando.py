from PySide6.QtWidgets import QComboBox, QLabel, QLineEdit, QWidget, QVBoxLayout

from src.resident_sites import ESTERO, SEDI, sede_di, stato_da_sede
from src.views.components import messages
from src.views.components.modal_dialog import ModalDialog


_ALTRA_SEDE_NON_SPECIFICATA = "Altra sede (da specificare)"


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
            ("SEDE ATTUALE",      "combo_sede",      True,  list(SEDI)),
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

        # Solo per l'estero: la sede precisa, che si vede nella scheda e non nell'elenco.
        self.box_sede_estero = QWidget()
        box = QVBoxLayout(self.box_sede_estero)
        box.setContentsMargins(0, 0, 0, 12)
        box.setSpacing(4)
        lbl_estero = QLabel("SEDE ALL'ESTERO")
        lbl_estero.setObjectName("LblCampo")
        self.input_sede_estero = QLineEdit()
        self.input_sede_estero.setObjectName("InputDialog")
        self.input_sede_estero.setPlaceholderText("Es. Karolinska University Hospital, Stoccolma")
        self.input_sede_estero.setFixedHeight(44)
        box.addWidget(lbl_estero)
        box.addWidget(self.input_sede_estero)
        layout.addWidget(self.box_sede_estero)
        self.combo_sede.currentTextChanged.connect(self._aggiorna_sede_estero)
        self._aggiorna_sede_estero(self.combo_sede.currentText())

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

        idx = self.combo_livello.findText(self._spec_dati.get("livello", ""))
        if idx >= 0:
            self.combo_livello.setCurrentIndex(idx)
        sede = sede_di(self._spec_dati)
        if not sede:
            # Libretto precedente con «Altra Sede» senza struttura: resta così finché
            # non se ne sceglie una.
            self.combo_sede.insertItem(0, _ALTRA_SEDE_NON_SPECIFICATA)
            sede = _ALTRA_SEDE_NON_SPECIFICATA
        self.combo_sede.setCurrentIndex(max(0, self.combo_sede.findText(sede)))
        self.input_sede_estero.setText(self._spec_dati.get("sede_estero", ""))

    def _aggiorna_sede_estero(self, sede: str) -> None:
        self.box_sede_estero.setVisible(sede == ESTERO)
        self.adjustSize()

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
            **self._dati_sede(),
        }

    def _dati_sede(self) -> dict:
        """Sede scelta, stato che ne deriva e testo dell'estero (vuoto se non è l'estero)."""
        sede = self.combo_sede.currentText()
        if sede == _ALTRA_SEDE_NON_SPECIFICATA:
            return {"sede": "", "stato": "Altra Sede", "sede_estero": ""}
        return {
            "sede": sede,
            "stato": stato_da_sede(sede),
            "sede_estero": self.input_sede_estero.text().strip() if sede == ESTERO else "",
        }
