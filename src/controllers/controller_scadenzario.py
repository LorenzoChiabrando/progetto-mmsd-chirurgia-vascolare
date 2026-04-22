import calendar
import datetime
from PySide6.QtWidgets import QTableWidget, QMessageBox
from PySide6.QtCore import Qt

from src.views.components.combo_delegate import ComboBoxDelegate, SmartComboBoxDelegate
from src.views.dialog_mese_anno import DialogMeseAnno


class ControllerScadenzario:
    def __init__(self, view, model, model_sale_operatorie=None):
        self.view = view
        self.model = model
        self.model_sale_op = model_sale_operatorie
        self.modalita_corrente = None

        self.mesi_ita = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                         "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        self.giorni_ita = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

        self.oggi = datetime.date.today()
        self.real_anno = self.oggi.year
        self.real_mese = self.oggi.month

        self.anno_corrente = self.real_anno
        self.mese_corrente = self.real_mese

        self.setup_delegates()

        self.view.btn_storico.clicked.connect(lambda: self.apri_calendario("STORICO"))
        self.view.btn_corrente.clicked.connect(lambda: self.apri_calendario("CORRENTE"))
        self.view.btn_pianificazione.clicked.connect(lambda: self.apri_calendario("PIANIFICAZIONE"))
        self.view.btn_indietro.clicked.connect(self.torna_alla_dashboard)

        self.view.btn_convalida.clicked.connect(self.convalida_mese)

        self.view.btn_prev.clicked.connect(self.mese_precedente)
        self.view.btn_next.clicked.connect(self.mese_successivo)
        self.view.btn_mese_anno.clicked.connect(self.scegli_mese_anno)

        self.view.tabella.cellChanged.connect(self.salva_modifica_cella)

        self.aggiorna_tabella()

    def get_max_history_date(self):
        """
        Calcola dinamicamente fino a che mese si può spingere lo Storico.
        Se il mese corrente è già CONVALIDATO, rientra nello storico.
        Altrimenti, lo storico si ferma rigorosamente al mese precedente.
        """
        if self.model.get_stato_mese(self.real_anno, self.real_mese) == "CONVALIDATO":
            return datetime.date(self.real_anno, self.real_mese, 1)
        else:
            if self.real_mese == 1:
                return datetime.date(self.real_anno - 1, 12, 1)
            else:
                return datetime.date(self.real_anno, self.real_mese - 1, 1)

    def convalida_mese(self):
        risposta = QMessageBox.question(
            self.view,
            "Conferma Convalida",
            "Vuoi convalidare in via definitiva questo mese?\n\nUna volta convalidato, il mese passerà allo Storico e non sarà più modificabile.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        )

        if risposta == QMessageBox.StandardButton.Yes:
            self.model.set_stato_mese(self.anno_corrente, self.mese_corrente, "CONVALIDATO")
            self.aggiorna_tabella()

    def apri_calendario(self, modalita):
        if modalita == "STORICO":
            max_history_date = self.get_max_history_date()

            mesi_disp = self.model.get_mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if not storici_validi:
                QMessageBox.information(
                    self.view,
                    "Nessuno storico",
                    "Non sono presenti dati di mesi passati o convalidati salvati nel sistema."
                )
                return
            else:
                self.anno_corrente, self.mese_corrente = storici_validi[-1]

        elif modalita in ["CORRENTE", "PIANIFICAZIONE"]:
            self.anno_corrente = self.real_anno
            self.mese_corrente = self.real_mese

        self.modalita_corrente = modalita
        self.view.stacked_widget.setCurrentIndex(1)
        self.aggiorna_tabella()

    def gestisci_navigazione(self):
        view_date = datetime.date(self.anno_corrente, self.mese_corrente, 1)
        real_date = datetime.date(self.real_anno, self.real_mese, 1)

        self.view.btn_prev.setVisible(True)
        self.view.btn_next.setVisible(True)
        self.view.btn_mese_anno.setEnabled(True)

        if self.modalita_corrente == "CORRENTE":
            self.view.btn_prev.setVisible(False)
            self.view.btn_next.setVisible(False)
            self.view.btn_mese_anno.setEnabled(False)

        elif self.modalita_corrente == "PIANIFICAZIONE":
            if view_date <= real_date:
                self.view.btn_prev.setVisible(False)

        elif self.modalita_corrente == "STORICO":
            max_history_date = self.get_max_history_date()

            if view_date >= max_history_date:
                self.view.btn_next.setVisible(False)

            mesi_disp = self.model.get_mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if storici_validi:
                min_y, min_m = storici_validi[0]
                min_history_date = datetime.date(min_y, min_m, 1)
                if view_date <= min_history_date:
                    self.view.btn_prev.setVisible(False)
            else:
                self.view.btn_prev.setVisible(False)

    def torna_alla_dashboard(self):
        self.modalita_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)

    def setup_delegates(self):
        tipi_guardia = ["118", "PI", "L"]
        delegate_tipo = ComboBoxDelegate(tipi_guardia, self.view.tabella)
        self.view.tabella.setItemDelegateForRow(1, delegate_tipo)

        specializzandi_attivi = self.model.get_specializzandi_attivi()
        # SmartComboBoxDelegate: esclude dinamicamente chi è già assegnato
        # nella stessa colonna (stesso giorno) in qualsiasi altra riga
        delegate_spec = SmartComboBoxDelegate(specializzandi_attivi, self.view.tabella)

        for riga in range(2, len(self.view.row_labels)):
            self.view.tabella.setItemDelegateForRow(riga, delegate_spec)

    def aggiorna_tabella(self):
        self.view.tabella.blockSignals(True)

        self.gestisci_navigazione()

        stato_json = self.model.get_stato_mese(self.anno_corrente, self.mese_corrente)

        if self.modalita_corrente == "STORICO":
            self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.view.btn_convalida.setVisible(False)

        elif self.modalita_corrente == "PIANIFICAZIONE":
            if stato_json == "CONVALIDATO":
                self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            else:
                self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.AllEditTriggers)
            self.view.btn_convalida.setVisible(False)

        elif self.modalita_corrente == "CORRENTE":
            self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
            self.view.btn_convalida.setVisible(stato_json != "CONVALIDATO")

        self.view.aggiorna_badge_modalita(self.modalita_corrente, stato_json)

        nome_mese = self.mesi_ita[self.mese_corrente - 1].upper()
        self.view.btn_mese_anno.setText(f"{nome_mese} {self.anno_corrente}")

        _, num_giorni = calendar.monthrange(self.anno_corrente, self.mese_corrente)

        self.view.tabella.setColumnCount(num_giorni)
        self.view.tabella.setHorizontalHeaderLabels([str(i) for i in range(1, num_giorni + 1)])

        oggi = datetime.date.today()

        # Reset eventuali span precedenti sulla riga Giro Visite
        # setSpan(r,c,1,1) rimuove uno span esistente, ma se non c'è span Qt stampa un warning:
        # chiamiamo setSpan solo quando columnSpan > 1 (cioè c'è davvero uno span da rimuovere)
        riga_gv = self.view.row_labels.index("Giro Visite")
        for col in range(num_giorni):
            if self.view.tabella.columnSpan(riga_gv, col) > 1:
                self.view.tabella.setSpan(riga_gv, col, 1, 1)

        for giorno in range(1, num_giorni + 1):
            data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
            data_str = data_corrente.strftime("%Y-%m-%d")

            giorno_settimana = data_corrente.weekday()
            is_festivo = giorno_settimana in (5, 6)
            is_oggi = (data_corrente == oggi)
            nome_giorno = self.giorni_ita[giorno_settimana].upper()

            self.view.tabella.setItem(0, giorno - 1, self.view.crea_item_giorno(nome_giorno, is_festivo, is_oggi))

            for riga in range(1, len(self.view.row_labels)):
                nome_riga = self.view.row_labels[riga]
                if nome_riga == "Giro Visite":
                    continue  # gestita separatamente con setSpan
                valore = "-" if is_festivo else self.model.get_valore_cella(data_str, nome_riga)
                self.view.tabella.setItem(riga, giorno - 1, self.view.crea_item_cella(valore, is_festivo, nome_riga, is_oggi))

        self._applica_giro_visite(num_giorni, oggi)

        self.view.tabella.blockSignals(False)

    def _applica_giro_visite(self, num_giorni: int, oggi: datetime.date):
        """Applica setSpan per la riga Giro Visite, raggruppando i giorni lun-ven in blocchi settimanali."""
        RIGA_GV = self.view.row_labels.index("Giro Visite")
        col = 0
        while col < num_giorni:
            data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, col + 1)
            wd = data_corrente.weekday()

            if wd >= 5:  # sabato/domenica
                item = self.view.crea_item_cella("-", True, "Giro Visite", False)
                self.view.tabella.setItem(RIGA_GV, col, item)
                col += 1
                continue

            # Inizio blocco feriale: trova fino a dove arriva lun-ven
            block_start = col
            while col < num_giorni:
                d = datetime.date(self.anno_corrente, self.mese_corrente, col + 1)
                if d.weekday() >= 5:
                    break
                col += 1
            block_end = col  # esclusivo
            block_len = block_end - block_start

            # Lunedì ISO della settimana (anche se fuori mese)
            start_date = datetime.date(self.anno_corrente, self.mese_corrente, block_start + 1)
            lun_date = start_date - datetime.timedelta(days=start_date.weekday())
            lun_str = lun_date.strftime("%Y-%m-%d")

            valore = self.model.get_giro_visite_settimana(lun_str, self.anno_corrente, self.mese_corrente)

            is_oggi_block = any(
                datetime.date(self.anno_corrente, self.mese_corrente, c + 1) == oggi
                for c in range(block_start, block_end)
            )

            self.view.tabella.setSpan(RIGA_GV, block_start, 1, block_len)
            item = self.view.crea_item_cella(valore, False, "Giro Visite", is_oggi_block)
            self.view.tabella.setItem(RIGA_GV, block_start, item)

    def salva_modifica_cella(self, riga, colonna):
        if riga == 0 or self.modalita_corrente in ["STORICO", "CORRENTE"]:
            return

        if self.model.get_stato_mese(self.anno_corrente, self.mese_corrente) == "CONVALIDATO":
            return

        giorno = colonna + 1
        data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, giorno)
        data_str = data_corrente.strftime("%Y-%m-%d")

        nome_riga = self.view.row_labels[riga]
        item = self.view.tabella.item(riga, colonna)
        nuovo_valore = item.text() if item else ""

        if nome_riga == "Giro Visite":
            lun_date = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            lun_str = lun_date.strftime("%Y-%m-%d")
            self.model.set_giro_visite_settimana(lun_str, self.anno_corrente, self.mese_corrente, nuovo_valore)
            is_oggi = (data_corrente == datetime.date.today())
            self.view.aggiorna_stile_cella(riga, colonna, nuovo_valore, nome_riga, False, is_oggi)
            return

        self.model.set_valore_cella(data_str, nome_riga, nuovo_valore)

        # Sincronizza lo specializzando con le sale operatorie
        if nome_riga in ("Sala Op. I", "Sala Op. II") and self.model_sale_op is not None:
            or1 = self.model.get_valore_cella(data_str, "Sala Op. I")
            or2 = self.model.get_valore_cella(data_str, "Sala Op. II")
            self.model_sale_op.set_specializzandi(data_str, or1, or2)

        # Riapplica lo stile corretto alla cella appena modificata
        is_festivo = data_corrente.weekday() in (5, 6)
        is_oggi = (data_corrente == datetime.date.today())
        self.view.aggiorna_stile_cella(riga, colonna, nuovo_valore, nome_riga, is_festivo, is_oggi)

    def mese_precedente(self):
        if self.mese_corrente == 1:
            self.mese_corrente = 12
            self.anno_corrente -= 1
        else:
            self.mese_corrente -= 1
        self.aggiorna_tabella()

    def mese_successivo(self):
        if self.mese_corrente == 12:
            self.mese_corrente = 1
            self.anno_corrente += 1
        else:
            self.mese_corrente += 1
        self.aggiorna_tabella()

    def scegli_mese_anno(self):
        dialog = DialogMeseAnno(self.mesi_ita, self.mese_corrente, self.anno_corrente, self.view)
        if not dialog.exec():
            return

        selected_mese, selected_anno = dialog.get_selezione()
        selected_date = datetime.date(selected_anno, selected_mese, 1)
        real_date = datetime.date(self.real_anno, self.real_mese, 1)

        if self.modalita_corrente == "PIANIFICAZIONE" and selected_date < real_date:
            self.mese_corrente = self.real_mese
            self.anno_corrente = self.real_anno

        elif self.modalita_corrente == "STORICO":
            max_history_date = self.get_max_history_date()

            mesi_disp = self.model.get_mesi_disponibili()
            storici_validi = [(a, m) for a, m in mesi_disp if datetime.date(a, m, 1) <= max_history_date]

            if not storici_validi:
                self.mese_corrente = max_history_date.month
                self.anno_corrente = max_history_date.year
            else:
                min_y, min_m = storici_validi[0]
                min_history_date = datetime.date(min_y, min_m, 1)

                if selected_date > max_history_date:
                    self.mese_corrente = max_history_date.month
                    self.anno_corrente = max_history_date.year
                elif selected_date < min_history_date:
                    self.mese_corrente = min_m
                    self.anno_corrente = min_y
                else:
                    self.mese_corrente = selected_mese
                    self.anno_corrente = selected_anno
        else:
            self.mese_corrente = selected_mese
            self.anno_corrente = selected_anno

        self.aggiorna_tabella()
