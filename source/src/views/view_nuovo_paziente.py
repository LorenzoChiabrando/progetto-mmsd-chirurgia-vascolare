from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QComboBox, QPushButton, QTextEdit,
    QSpinBox, QAbstractSpinBox,
)
from PySide6.QtCore import Qt

from src.patient_fields import DEFAULT_INTERVENTION_MINUTES, UNCLASSIFIED, normalize_diagnosis
from src.views.components import messages
from src.views.components.modal_dialog import ModalDialog


class DialogNuovoPaziente(ModalDialog):
    def __init__(self, parent=None, paziente_dati=None):
        self._paz_dati = paziente_dati
        self._edit_mode = paziente_dati is not None
        self._custom_durations = self._edit_mode
        super().__init__(
            "Modifica Paziente" if self._edit_mode else "Aggiungi Paziente",
            (
                "Modifica le informazioni del paziente." if self._edit_mode
                else "Usa gli stessi dati del CSV. Solo Nome e Cognome sono obbligatori."
            ),
            section="pazienti",
            scrollable=True,
            extra_styles=("pazienti.qss",),
            parent=parent,
        )
        self.setWindowTitle("Modifica Paziente" if self._edit_mode else "Nuovo Paziente")
        self.setMinimumWidth(620)
        self.setMinimumHeight(600)
        self.resize(660, 720)
        self.setSizeGripEnabled(True)
        self._interventi_rows = []
        self.setup_ui()
        if self._edit_mode:
            self._precompila()
        else:
            self._aggiungi_riga_intervento()
        self._mostra_dati_aggiuntivi(self._edit_mode)

    def setup_ui(self):
        layout = self.body
        layout.setSpacing(14)

        nome_cogn = QHBoxLayout()
        nome_cogn.setSpacing(12)
        nome_cogn.addWidget(self._campo("NOME *", "input_nome", "Es. Giovanni"))
        nome_cogn.addWidget(self._campo("COGNOME *", "input_cognome", "Es. Ferretti"))
        layout.addLayout(nome_cogn)

        diagnosi_row = QHBoxLayout()
        diagnosi_row.setSpacing(12)
        diagnosi_row.addWidget(
            self._campo("CODICE ICD-9-CM", "input_codice_diagnosi", "Se disponibile")
        )
        diagnosi_row.addWidget(
            self._campo(
                "DIAGNOSI ICD9 / DESCRIZIONE",
                "input_descrizione_diagnosi",
                "Es. Stenosi carotidea sintomatica",
            ),
            2,
        )
        layout.addLayout(diagnosi_row)
        self.input_descrizione_diagnosi.setToolTip(
            "Puoi incollare Diagnosi ICD9 dal CSV, anche con il codice fra parentesi. "
            "Il codice separato e la descrizione non sono obbligatori."
        )

        grp_int = QVBoxLayout()
        grp_int.setSpacing(6)

        lbl_int_hdr = QLabel("INTERVENTI")
        lbl_int_hdr.setObjectName("LblCampo")
        grp_int.addWidget(lbl_int_hdr)

        col_hdr = QHBoxLayout()
        col_hdr.setContentsMargins(0, 0, 0, 0)
        col_hdr.setSpacing(8)
        for txt, w, stretch in [
            ("CODICE INTERVENTO", 135, 0),
            ("INTERVENTO / PROCEDURA ICD9", 0, 1),
            ("DURATA [minuti]", 120, 0),
        ]:
            lbl = QLabel(txt)
            lbl.setObjectName("LblCampoSmall")
            if w:
                lbl.setFixedWidth(w)
            if txt == "DURATA [minuti]":
                self._duration_header = lbl
            col_hdr.addWidget(lbl, stretch=stretch)
        col_hdr.addSpacing(36)  # space for − button
        grp_int.addLayout(col_hdr)

        self._interventi_widget = QWidget()
        self._interventi_layout = QVBoxLayout(self._interventi_widget)
        self._interventi_layout.setContentsMargins(0, 0, 0, 0)
        self._interventi_layout.setSpacing(6)
        grp_int.addWidget(self._interventi_widget)

        self.btn_aggiungi_int = QPushButton("+ Aggiungi intervento")
        self.btn_aggiungi_int.setObjectName("BtnAggiungiIntervento")
        self.btn_aggiungi_int.setFixedHeight(34)
        self.btn_aggiungi_int.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_aggiungi_int.clicked.connect(lambda: self._aggiungi_riga_intervento())
        grp_int.addWidget(self.btn_aggiungi_int)

        layout.addLayout(grp_int)

        grp_urg = QVBoxLayout()
        grp_urg.setSpacing(4)
        lbl_urg = QLabel("PRIORITÀ / URGENZA")
        lbl_urg.setObjectName("LblCampo")
        self.combo_urgenza = QComboBox()
        self.combo_urgenza.setObjectName("ComboDialog")
        self.combo_urgenza.addItems([UNCLASSIFIED, "Alta", "Media", "Bassa"])
        self.combo_urgenza.setToolTip("CSV: classe A = Alta, B = Media, C/D = Bassa")
        self.combo_urgenza.setFixedHeight(44)
        grp_urg.addWidget(lbl_urg)
        grp_urg.addWidget(self.combo_urgenza)
        layout.addLayout(grp_urg)

        self.lbl_durata = QLabel()
        self.lbl_durata.setObjectName("SottoTitoloDialog")
        self.lbl_durata.setWordWrap(True)
        layout.addWidget(self.lbl_durata)

        self.btn_dati_aggiuntivi = QPushButton("Mostra dati aggiuntivi (facoltativi)")
        self.btn_dati_aggiuntivi.setObjectName("BtnAggiungiIntervento")
        self.btn_dati_aggiuntivi.setCheckable(True)
        self.btn_dati_aggiuntivi.setChecked(self._edit_mode)
        self.btn_dati_aggiuntivi.setFixedHeight(34)
        self.btn_dati_aggiuntivi.toggled.connect(self._mostra_dati_aggiuntivi)
        layout.addWidget(self.btn_dati_aggiuntivi)

        self.dati_aggiuntivi = QWidget()
        extra_layout = QVBoxLayout(self.dati_aggiuntivi)
        extra_layout.setContentsMargins(0, 0, 0, 0)
        extra_layout.setSpacing(14)
        layout.addWidget(self.dati_aggiuntivi)

        lbl_extra = QLabel(
            "Tipo chirurgia e complessità non sono presenti nel CSV TrackCare. "
            "Puoi completarli in seguito; la complessità serve prima della pianificazione."
        )
        lbl_extra.setObjectName("SottoTitoloDialog")
        lbl_extra.setWordWrap(True)
        extra_layout.addWidget(lbl_extra)

        tipo_cpx = QHBoxLayout()
        tipo_cpx.setSpacing(12)

        grp_tipo = QVBoxLayout()
        grp_tipo.setSpacing(4)
        lbl_tipo = QLabel("TIPO CHIRURGIA")
        lbl_tipo.setObjectName("LblCampo")
        self.combo_tipo = QComboBox()
        self.combo_tipo.setObjectName("ComboDialog")
        self.combo_tipo.addItems([UNCLASSIFIED, "Aperta", "Endovascolare"])
        self.combo_tipo.setFixedHeight(44)
        grp_tipo.addWidget(lbl_tipo)
        grp_tipo.addWidget(self.combo_tipo)

        grp_cpx = QVBoxLayout()
        grp_cpx.setSpacing(4)
        lbl_cpx = QLabel("COMPLESSITÀ")
        lbl_cpx.setObjectName("LblCampo")
        self.combo_complessita = QComboBox()
        self.combo_complessita.setObjectName("ComboDialog")
        self.combo_complessita.addItems([UNCLASSIFIED, "Alta", "Media", "Bassa"])
        self.combo_complessita.setFixedHeight(44)
        grp_cpx.addWidget(lbl_cpx)
        grp_cpx.addWidget(self.combo_complessita)

        tipo_cpx.addLayout(grp_tipo)
        tipo_cpx.addLayout(grp_cpx)
        extra_layout.addLayout(tipo_cpx)

        grp_sta = QVBoxLayout()
        grp_sta.setSpacing(4)
        lbl_sta = QLabel("STATO")
        lbl_sta.setObjectName("LblCampo")
        self.combo_stato = QComboBox()
        self.combo_stato.setObjectName("ComboDialog")
        self.combo_stato.addItems(["In Attesa", "Completato"])
        if self._paz_dati and self._paz_dati.get("stato") == "Pianificato":
            self.combo_stato.addItem("Pianificato")
        self.combo_stato.setFixedHeight(44)
        grp_sta.addWidget(lbl_sta)
        grp_sta.addWidget(self.combo_stato)

        extra_layout.addLayout(grp_sta)

        grp_note = QVBoxLayout()
        grp_note.setSpacing(4)
        lbl_note = QLabel("NOTE CLINICHE (opzionale)")
        lbl_note.setObjectName("LblCampo")
        self.input_note = QTextEdit()
        self.input_note.setObjectName("NoteDialog")
        self.input_note.setPlaceholderText("Preparazione, allergie, controindicazioni, urgenze...")
        self.input_note.setFixedHeight(72)
        grp_note.addWidget(lbl_note)
        grp_note.addWidget(self.input_note)
        extra_layout.addLayout(grp_note)

        layout.addStretch(1)

        self.btn_annulla = self.make_button("Annulla", "secondary")
        self.btn_annulla.clicked.connect(self.reject)

        self.btn_salva = self.make_button(
            "Salva Modifiche" if self._edit_mode else "Salva Paziente", "primary"
        )
        self.btn_salva.setDefault(True)
        self.btn_salva.clicked.connect(self._valida_e_salva)

        self.add_footer(self.btn_annulla, self.btn_salva)

    def _campo(self, etichetta, attr_name, placeholder):
        grp = QWidget()
        grp_layout = QVBoxLayout(grp)
        grp_layout.setContentsMargins(0, 0, 0, 0)
        grp_layout.setSpacing(4)
        lbl = QLabel(etichetta)
        lbl.setObjectName("LblCampo")
        inp = QLineEdit()
        inp.setObjectName("InputDialog")
        inp.setPlaceholderText(placeholder)
        inp.setFixedHeight(44)
        setattr(self, attr_name, inp)
        grp_layout.addWidget(lbl)
        grp_layout.addWidget(inp)
        return grp

    def _mostra_dati_aggiuntivi(self, visible: bool) -> None:
        self.dati_aggiuntivi.setVisible(visible)
        self._duration_header.setVisible(visible)
        self.btn_dati_aggiuntivi.setText(
            "Nascondi dati aggiuntivi" if visible else "Mostra dati aggiuntivi (facoltativi)"
        )
        for row in self._interventi_rows:
            row["input_durata"].setVisible(visible)

    def _aggiorna_durate(self) -> None:
        count = len(self._interventi_rows)
        if count and not self._custom_durations:
            minutes, remainder = divmod(max(DEFAULT_INTERVENTION_MINUTES, count), count)
            for index, row in enumerate(self._interventi_rows):
                widget = row["input_durata"]
                blocked = widget.blockSignals(True)
                widget.setValue(minutes + (index < remainder))
                widget.blockSignals(blocked)
        total = sum(row["input_durata"].value() for row in self._interventi_rows)
        self.lbl_durata.setText(
            f"Durata totale: {total} minuti." if self._custom_durations
            else f"Durata provvisoria: {total} minuti totali. "
            "Puoi modificarla nei dati aggiuntivi."
        )

    def _durata_modificata(self) -> None:
        self._custom_durations = True
        self._aggiorna_durate()

    def _aggiungi_riga_intervento(
        self, codice="", descrizione="", durata=DEFAULT_INTERVENTION_MINUTES
    ):
        row_frame = QFrame()
        row_frame.setObjectName("InterventiRow")
        row_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        hl = QHBoxLayout(row_frame)
        hl.setContentsMargins(0, 0, 0, 0)
        hl.setSpacing(8)

        inp_codice = QLineEdit()
        inp_codice.setObjectName("InputDialog")
        inp_codice.setPlaceholderText("Es. 38.12")
        inp_codice.setText(codice)
        inp_codice.setFixedHeight(38)
        inp_codice.setFixedWidth(135)

        inp_desc = QLineEdit()
        inp_desc.setObjectName("InputDialog")
        inp_desc.setPlaceholderText("Es. Endoarterectomia carotidea")
        inp_desc.setText(descrizione)
        inp_desc.setFixedHeight(38)

        input_dur = QSpinBox()
        input_dur.setObjectName("InputDialog")
        input_dur.setRange(1, 10080)
        input_dur.setValue(max(1, int(durata)))
        input_dur.setButtonSymbols(QAbstractSpinBox.ButtonSymbols.NoButtons)
        input_dur.setAlignment(Qt.AlignmentFlag.AlignCenter)
        input_dur.setFixedHeight(38)
        input_dur.setFixedWidth(120)
        input_dur.setToolTip("Durata dell'intervento espressa in minuti")
        input_dur.setVisible(self.btn_dati_aggiuntivi.isChecked())
        input_dur.valueChanged.connect(self._durata_modificata)

        btn_rm = QPushButton("−")
        btn_rm.setObjectName("BtnRimuoviIntervento")
        btn_rm.setFixedSize(32, 38)
        btn_rm.setCursor(Qt.CursorShape.PointingHandCursor)

        hl.addWidget(inp_codice)
        hl.addWidget(inp_desc, 1)
        hl.addWidget(input_dur)
        hl.addWidget(btn_rm)

        row_data = {
            "frame": row_frame,
            "inp_codice": inp_codice,
            "inp_desc": inp_desc,
            "input_durata": input_dur,
            "btn_rm": btn_rm,
        }
        btn_rm.clicked.connect(lambda: self._rimuovi_riga_intervento(row_data))

        self._interventi_rows.append(row_data)
        self._interventi_layout.addWidget(row_frame)
        self._aggiorna_btn_rimuovi()
        self._aggiorna_durate()

    def _rimuovi_riga_intervento(self, row_data):
        if len(self._interventi_rows) <= 1:
            return
        self._interventi_rows.remove(row_data)
        row_data["frame"].setParent(None)
        row_data["frame"].deleteLater()
        self._aggiorna_btn_rimuovi()
        self._aggiorna_durate()

    def _aggiorna_btn_rimuovi(self):
        solo = len(self._interventi_rows) == 1
        for row in self._interventi_rows:
            row["btn_rm"].setEnabled(not solo)

    def _precompila(self):
        while self._interventi_rows:
            rd = self._interventi_rows.pop()
            rd["frame"].setParent(None)
            rd["frame"].deleteLater()

        interventi = self._paz_dati.get("interventi")
        if not interventi:
            interventi = [{
                "codice": self._paz_dati.get("codice_intervento", ""),
                "descrizione": self._paz_dati.get("descrizione_intervento", ""),
                "durata": self._paz_dati.get("durata_intervento", 90),
            }]
        for inv in interventi:
            self._aggiungi_riga_intervento(
                inv.get("codice", ""),
                inv.get("descrizione", ""),
                inv.get("durata", 90),
            )

        self.input_nome.setText(self._paz_dati.get("nome", ""))
        self.input_cognome.setText(self._paz_dati.get("cognome", ""))
        codice_diagnosi, descrizione_diagnosi, _ = normalize_diagnosis(
            self._paz_dati.get("codice_diagnosi", ""),
            self._paz_dati.get("descrizione_diagnosi", self._paz_dati.get("diagnosi", "")),
        )
        self.input_codice_diagnosi.setText(codice_diagnosi)
        self.input_descrizione_diagnosi.setText(descrizione_diagnosi)

        for combo, field in [
            (self.combo_tipo, "tipo_chirurgia"),
            (self.combo_complessita, "complessita"),
            (self.combo_urgenza, "urgenza"),
            (self.combo_stato, "stato"),
        ]:
            idx = combo.findText(self._paz_dati.get(field, ""))
            if idx >= 0:
                combo.setCurrentIndex(idx)

        self.input_note.setPlainText(self._paz_dati.get("note", ""))

    def _valida_e_salva(self):
        nome = self.input_nome.text().strip()
        cognome = self.input_cognome.text().strip()
        if not nome or not cognome:
            messages.show_message(
                self,
                "Campi Incompleti",
                "Nome e Cognome sono obbligatori, come nell'inserimento da CSV.",
                section="pazienti",
                kind="warning",
            )
            return
        self.accept()

    def get_dati(self):
        interventi = []
        for row in self._interventi_rows:
            codice = row["inp_codice"].text().strip()
            desc = row["inp_desc"].text().strip()
            durata = row["input_durata"].value()
            interventi.append({"codice": codice, "descrizione": desc, "durata": durata})

        durata_totale = sum(i["durata"] for i in interventi) if interventi else 90
        primo = interventi[0] if interventi else {}

        codice_diagnosi, descrizione_diagnosi, diagnosi_legacy = normalize_diagnosis(
            self.input_codice_diagnosi.text(), self.input_descrizione_diagnosi.text()
        )

        return {
            "nome": self.input_nome.text().strip(),
            "cognome": self.input_cognome.text().strip(),
            "codice_diagnosi": codice_diagnosi,
            "descrizione_diagnosi": descrizione_diagnosi,
            "diagnosi": diagnosi_legacy,
            "interventi": interventi,
            "codice_intervento": primo.get("codice", ""),
            "descrizione_intervento": primo.get("descrizione", ""),
            "durata_intervento": durata_totale,
            "tipo_chirurgia": self.combo_tipo.currentText(),
            "complessita": self.combo_complessita.currentText(),
            "urgenza": self.combo_urgenza.currentText(),
            "stato": self.combo_stato.currentText(),
            "note": self.input_note.toPlainText().strip(),
        }
