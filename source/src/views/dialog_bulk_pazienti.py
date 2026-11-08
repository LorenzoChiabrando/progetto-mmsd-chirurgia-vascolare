import os
from copy import deepcopy
from PySide6.QtWidgets import (
    QHBoxLayout, QLabel, QTableWidget, QTableWidgetItem, QHeaderView,
    QFileDialog, QComboBox, QScroller, QLineEdit,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor, QIntValidator

from src.importers.patient_csv import (
    PatientCsvError, build_csv_interventions, read_patient_csv,
)
from src.views.components import messages
from src.views.components.modal_dialog import ModalDialog

_HEADERS = [
    "Nome", "Cognome", "Cod. diagnosi", "Descrizione diagnosi",
    "Cod. ICD-9", "Desc. intervento", "Tipo chir.", "Complessità",
    "Urgenza", "Durata [minuti]",
]

_COL_NOME = 0
_COL_COGNOME = 1
_COL_DIAG_CODICE = 2
_COL_DIAG_DESCRIZIONE = 3
_COL_CODICE = 4
_COL_INTERVENTO = 5
_COL_TIPO = 6
_COL_CPX = 7
_COL_URG = 8
_COL_DUR = 9

_COMBO_DEFS = {
    _COL_TIPO: (["Da classificare", "Aperta", "Endovascolare"], "Da classificare"),
    _COL_CPX: (["Da classificare", "Alta", "Media", "Bassa"], "Da classificare"),
    _COL_URG: (["Da classificare", "Alta", "Media", "Bassa"], "Da classificare"),
}

_BG_OK  = QColor("#ffffff")
_BG_ERR = QColor("#fef2f2")
_FG_ERR = QColor("#b91c1c")
_FG_OK  = QColor("#1e293b")


_SOTTOTITOLO = (
    "Seleziona un CSV dello Scadenziario o un'esportazione TrackCare. "
    "Separatore, codifica e intestazioni vengono riconosciuti automaticamente. "
    "La diagnosi viene divisa in <b>codice ICD-9-CM</b> e <b>descrizione</b>. "
    "La durata opzionale può essere <i>90</i> oppure <i>60;90</i> per più interventi. "
    "Usa il punto e virgola (<b>;</b>) per separare più codici, descrizioni e durate nello stesso paziente. "
    "I dati non disponibili in TrackCare restano visibili come <b>Da classificare</b>."
)


class DialogBulkPazienti(ModalDialog):
    def __init__(self, parent=None):
        self._interventi_per_riga: dict[int, list] = {}
        self._cell_changed_connected = False
        self._import_context = ""
        super().__init__(
            "Importa Pazienti da CSV",
            _SOTTOTITOLO,
            section="pazienti",
            extra_styles=("pazienti.qss",),
            parent=parent,
        )
        self.setMinimumWidth(1060)
        self.setMinimumHeight(560)
        self.setSizeGripEnabled(True)
        self.setup_ui()

    def setup_ui(self):
        layout = self.body
        layout.setSpacing(14)

        file_row = QHBoxLayout()
        self.lbl_file = QLabel("Nessun file selezionato")
        self.lbl_file.setObjectName("LblFileCSV")
        self.lbl_file.setFixedHeight(32)

        self.btn_sfoglia = self.make_button("Sfoglia…", "secondary")
        self.btn_sfoglia.clicked.connect(self._scegli_file)

        file_row.addWidget(self.lbl_file, stretch=1)
        file_row.addWidget(self.btn_sfoglia)
        layout.addLayout(file_row)

        self.lbl_stato = QLabel("")
        self.lbl_stato.setObjectName("LblStatoCSV")
        self.lbl_stato.setWordWrap(True)
        layout.addWidget(self.lbl_stato)

        self.tabella = QTableWidget(0, len(_HEADERS))
        self.tabella.setObjectName("TabellaBulk")
        self.tabella.setHorizontalHeaderLabels(_HEADERS)

        hh = self.tabella.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        hh.setMinimumSectionSize(70)
        for col, w in [
            (_COL_NOME,       120),
            (_COL_COGNOME,    120),
            (_COL_DIAG_CODICE, 100),
            (_COL_DIAG_DESCRIZIONE, 220),
            (_COL_CODICE,      80),
            (_COL_INTERVENTO, 200),
            (_COL_TIPO,       110),
            (_COL_CPX,        100),
            (_COL_URG,         85),
            (_COL_DUR,         90),
        ]:
            self.tabella.setColumnWidth(col, w)

        self.tabella.setHorizontalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setVerticalScrollMode(QTableWidget.ScrollMode.ScrollPerPixel)
        self.tabella.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOn)
        self.tabella.verticalHeader().setDefaultSectionSize(40)
        self.tabella.verticalHeader().setVisible(False)
        self.tabella.setAlternatingRowColors(False)
        self.tabella.setShowGrid(True)
        self.tabella.setWordWrap(False)
        self.tabella.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        QScroller.grabGesture(
            self.tabella.viewport(), QScroller.ScrollerGestureType.LeftMouseButtonGesture
        )

        # Evita cellChanged durante il caricamento iniziale.
        layout.addWidget(self.tabella)

        self.btn_annulla = self.make_button("Annulla", "secondary")
        self.btn_annulla.clicked.connect(self.reject)

        self.btn_importa = self.make_button("Importa Pazienti", "primary")
        self.btn_importa.setEnabled(False)
        self.btn_importa.clicked.connect(self._conferma_importazione)

        self.add_footer(self.btn_annulla, self.btn_importa)

    def _scegli_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Seleziona file CSV", "", "File CSV (*.csv)"
        )
        if not path:
            return
        self.lbl_file.setText(os.path.basename(path))
        self._carica_csv(path)

    def _carica_csv(self, path: str):
        self.tabella.blockSignals(True)
        self.tabella.setRowCount(0)
        self._interventi_per_riga.clear()
        self._import_context = ""
        self.tabella.blockSignals(False)
        self._aggiorna_stato()
        try:
            result = read_patient_csv(path)
        except PatientCsvError as error:
            messages.show_message(
                self, "Errore lettura file", str(error), section="pazienti", kind="error"
            )
            return

        if not result.rows:
            self.lbl_stato.setText("Il file è vuoto.")
            self.btn_importa.setEnabled(False)
            return

        self.tabella.blockSignals(True)
        self.tabella.setRowCount(0)
        self._interventi_per_riga.clear()
        self._import_context = f"Formato {result.source_format}."
        if result.warnings:
            self._import_context += " " + " ".join(result.warnings)

        for row in result.rows:
            self._inserisci_riga(row)

        self.tabella.blockSignals(False)

        if not self._cell_changed_connected:
            self.tabella.cellChanged.connect(self._on_cella_cambiata)
            self._cell_changed_connected = True

        self._aggiorna_stato()
        if result.warnings:
            self.lbl_stato.setStyleSheet(
                "font-size:13px; font-weight:bold; color:#b45309;"
            )

    def _inserisci_riga(self, r: dict):
        row = self.tabella.rowCount()
        self.tabella.insertRow(row)

        text_fields = {
            _COL_NOME: "nome",
            _COL_COGNOME: "cognome",
            _COL_DIAG_CODICE: "codice_diagnosi",
            _COL_DIAG_DESCRIZIONE: "descrizione_diagnosi",
        }
        for col, field in text_fields.items():
            item = QTableWidgetItem(r.get(field, ""))
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
                if col == _COL_DIAG_DESCRIZIONE else Qt.AlignmentFlag.AlignCenter
            )
            self.tabella.setItem(row, col, item)

        cod_text = r.get("codice_intervento", "")
        desc_text = r.get("descrizione_intervento", "")
        duration_text = r.get("durata_intervento", "90")
        try:
            interventions = build_csv_interventions(cod_text, desc_text, duration_text)
        except PatientCsvError:
            pass
        else:
            self._interventi_per_riga[row] = interventions
            duration_text = str(sum(item["durata"] for item in interventions))

        item_cod = QTableWidgetItem(cod_text)
        item_cod.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
        if ";" in cod_text:
            item_cod.setToolTip(cod_text.replace(";", "\n"))
        self.tabella.setItem(row, _COL_CODICE, item_cod)

        item_desc = QTableWidgetItem(desc_text)
        item_desc.setTextAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        if desc_text:
            item_desc.setToolTip(desc_text.replace(" ; ", "\n"))
        self.tabella.setItem(row, _COL_INTERVENTO, item_desc)

        for col, (opzioni, default) in _COMBO_DEFS.items():
            combo = self._crea_combo(opzioni)
            field = {
                _COL_TIPO: "tipo_chirurgia",
                _COL_CPX: "complessita",
                _COL_URG: "urgenza",
            }[col]
            val = r.get(field, "").strip()
            idx = combo.findText(val)
            combo.setCurrentIndex(idx if idx >= 0 else combo.findText(default))
            combo.currentIndexChanged.connect(
                lambda _idx, c=col, rw=row: self._valida_riga(rw)
            )
            self.tabella.setCellWidget(row, col, combo)

        duration_input = QLineEdit(duration_text)
        duration_input.setObjectName("InputDialog")
        duration_input.setValidator(QIntValidator(1, 10080, duration_input))
        duration_input.textChanged.connect(
            lambda text, rw=row: self._on_durata_totale_cambiata(rw, text)
        )
        self.tabella.setCellWidget(row, _COL_DUR, duration_input)

        self._valida_riga(row)

    def _crea_combo(self, opzioni: list) -> QComboBox:
        combo = QComboBox()
        combo.setObjectName("ComboDialog")
        combo.addItems(opzioni)
        return combo

    def _on_durata_totale_cambiata(self, row: int, text: str):
        """Mantiene coerenti durata totale e dettagli multi-intervento."""
        try:
            interventions = build_csv_interventions(
                self.tabella.item(row, _COL_CODICE).text(),
                self.tabella.item(row, _COL_INTERVENTO).text(), text,
            )
        except PatientCsvError:
            self._interventi_per_riga.pop(row, None)
        else:
            self._interventi_per_riga[row] = interventions
        self._valida_riga(row)

    def _riga_valida(self, row: int) -> bool:
        for column in (_COL_NOME, _COL_COGNOME):
            item = self.tabella.item(row, column)
            if not item or not item.text().strip():
                return False
        duration = self.tabella.cellWidget(row, _COL_DUR)
        if duration is None or not duration.hasAcceptableInput():
            return False
        try:
            build_csv_interventions(
                self.tabella.item(row, _COL_CODICE).text(),
                self.tabella.item(row, _COL_INTERVENTO).text(), duration.text(),
            )
        except PatientCsvError:
            return False
        return True

    def _valida_riga(self, row: int):
        previous_signals = self.tabella.blockSignals(True)
        errori_col = set()

        nome_item = self.tabella.item(row, _COL_NOME)
        cogn_item = self.tabella.item(row, _COL_COGNOME)
        if not (nome_item and nome_item.text().strip()):
            errori_col.add(_COL_NOME)
        if not (cogn_item and cogn_item.text().strip()):
            errori_col.add(_COL_COGNOME)

        for col in [
            _COL_NOME,
            _COL_COGNOME,
            _COL_DIAG_CODICE,
            _COL_DIAG_DESCRIZIONE,
            _COL_CODICE,
            _COL_INTERVENTO,
        ]:
            item = self.tabella.item(row, col)
            if not item:
                continue
            if col in errori_col:
                item.setBackground(_BG_ERR)
                item.setForeground(_FG_ERR)
            else:
                item.setBackground(_BG_OK)
                item.setForeground(_FG_OK)

        self.tabella.blockSignals(previous_signals)
        duration = self.tabella.cellWidget(row, _COL_DUR)
        if duration is not None:
            duration.setStyleSheet("" if self._riga_valida(row) else "background: #fef2f2;")
        self._aggiorna_stato()

    def _on_cella_cambiata(self, row: int, col: int):
        if col in (_COL_CODICE, _COL_INTERVENTO):
            self._interventi_per_riga.pop(row, None)
        self._valida_riga(row)

    def _conta_righe_valide(self) -> int:
        return sum(self._riga_valida(row) for row in range(self.tabella.rowCount()))

    def _aggiorna_stato(self):
        totale = self.tabella.rowCount()
        if totale == 0:
            self.lbl_stato.setText("")
            self.btn_importa.setEnabled(False)
            return

        valide = self._conta_righe_valide()
        n_err  = totale - valide

        if n_err == 0:
            self.lbl_stato.setStyleSheet("font-size:13px; font-weight:bold; color:#15803d;")
            message = f"{totale} righe pronte per l'importazione"
        else:
            self.lbl_stato.setStyleSheet("font-size:13px; font-weight:bold; color:#b45309;")
            message = (
                f"{valide} righe valide, {n_err} con nome, cognome o durata non validi "
                "(in rosso). Correggi le righe prima di importare."
            )

        if self._import_context:
            message += f"\n{self._import_context}"
        self.lbl_stato.setText(message)

        self.btn_importa.setEnabled(valide > 0 and n_err == 0)

    def _conferma_importazione(self):
        if self._conta_righe_valide() != self.tabella.rowCount():
            messages.show_message(
                self,
                "Dati incompleti",
                "Correggi le righe evidenziate.",
                section="pazienti",
                kind="warning",
            )
            return
        pazienti = self.get_pazienti()
        if not pazienti:
            messages.show_message(
                self,
                "Nessun paziente valido",
                "Nessuna riga ha nome e cognome compilati.",
                section="pazienti",
                kind="warning",
            )
            return
        self.accept()

    def get_pazienti(self) -> list[dict]:
        pazienti = []
        for row in range(self.tabella.rowCount()):
            nome_item = self.tabella.item(row, _COL_NOME)
            cogn_item = self.tabella.item(row, _COL_COGNOME)
            nome    = nome_item.text().strip() if nome_item else ""
            cognome = cogn_item.text().strip() if cogn_item else ""
            if not self._riga_valida(row):
                continue

            def _txt(col, _row=row):
                it = self.tabella.item(_row, col)
                return it.text().strip() if it else ""

            def _combo(col, _row=row):
                w = self.tabella.cellWidget(_row, col)
                return w.currentText() if w else ""

            durata = int(self.tabella.cellWidget(row, _COL_DUR).text())

            # Ricostruisce dalle celle se l'anteprima è stata modificata.
            interventi = deepcopy(self._interventi_per_riga.get(row))
            if not interventi:
                interventi = build_csv_interventions(
                    _txt(_COL_CODICE), _txt(_COL_INTERVENTO), str(durata)
                )

            primo = interventi[0] if interventi else {}

            pazienti.append({
                "nome":                   nome,
                "cognome":                cognome,
                "codice_diagnosi":        _txt(_COL_DIAG_CODICE),
                "descrizione_diagnosi":   _txt(_COL_DIAG_DESCRIZIONE),
                "diagnosi":               _txt(_COL_DIAG_DESCRIZIONE),
                "codice_intervento":      primo.get("codice", ""),
                "descrizione_intervento": primo.get("descrizione", ""),
                "interventi":             interventi,
                "durata_intervento":      durata,
                "tipo_chirurgia":         _combo(_COL_TIPO),
                "complessita":            _combo(_COL_CPX),
                "urgenza":                _combo(_COL_URG),
                "stato":                  "In Attesa",
                "note":                   "",
            })
        return pazienti
