from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox
from src.views.view_nuovo_paziente import DialogNuovoPaziente
from src.views.dialog_bulk_pazienti import DialogBulkPazienti


class ControllerPazienti:
    def __init__(self, view, model_pazienti, model_sale_operatorie=None):
        self.view = view
        self.model = model_pazienti
        self.model_sale_op = model_sale_operatorie
        self._paz_corrente = None
        self.setup_connections()
        self.aggiorna_lista()

    def setup_connections(self):
        self.view.chk_urg_alta.toggled.connect(self.aggiorna_lista)
        self.view.chk_urg_media.toggled.connect(self.aggiorna_lista)
        self.view.chk_urg_bassa.toggled.connect(self.aggiorna_lista)
        self.view.chk_in_attesa.toggled.connect(self.aggiorna_lista)
        self.view.chk_pianificato.toggled.connect(self.aggiorna_lista)
        self.view.chk_completato.toggled.connect(self.aggiorna_lista)
        self.view.search_bar.textChanged.connect(self.aggiorna_lista)
        self.view.lista_risultati.itemSelectionChanged.connect(self.gestisci_selezione)
        self.view.btn_aggiungi.clicked.connect(self.apri_form_aggiunta)
        self.view.btn_bulk.clicked.connect(self.apri_form_bulk)
        self.view.btn_apri.clicked.connect(self.apri_dettaglio_paziente)
        self.view.btn_indietro.clicked.connect(self.torna_alla_lista)
        self.view.btn_modifica.clicked.connect(self.modifica_paziente)
        self.view.btn_elimina.clicked.connect(self.elimina_paziente)

    def apri_dettaglio_paziente(self):
        selezionati = self.view.lista_risultati.selectedItems()
        if not selezionati:
            return
        paz_id = selezionati[0].data(Qt.ItemDataRole.UserRole)
        paz = self.model.get_paziente_by_id(paz_id)
        if not paz:
            return
        self._paz_corrente = paz
        self.view.imposta_dettaglio(paz)
        self.view.stacked_widget.setCurrentIndex(1)

    def torna_alla_lista(self):
        self._paz_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)
        self.view.lista_risultati.clearSelection()

    def aggiorna_lista(self):
        self.view.lista_risultati.clear()
        tutti = self.model.get_tutti_pazienti()
        testo = self.view.search_bar.text().lower().strip()
        termini = testo.split() if testo else []

        pianificati_ids = (
            self.model_sale_op.get_pazienti_pianificati_ids()
            if self.model_sale_op else set()
        )

        urgenze = []
        if self.view.chk_urg_alta.isChecked():
            urgenze.append("Alta")
        if self.view.chk_urg_media.isChecked():
            urgenze.append("Media")
        if self.view.chk_urg_bassa.isChecked():
            urgenze.append("Bassa")

        stati_filtro = []
        if self.view.chk_in_attesa.isChecked():
            stati_filtro.append("In Attesa")
        if self.view.chk_pianificato.isChecked():
            stati_filtro.append("Pianificato")
        if self.view.chk_completato.isChecked():
            stati_filtro.append("Completato")

        n_attesa = 0
        n_pianificati = 0

        for paz in tutti:
            paz_stato_base = paz.get("stato", "In Attesa")
            if paz_stato_base == "In Attesa" and paz.get("id") in pianificati_ids:
                paz_stato = "Pianificato"
            else:
                paz_stato = paz_stato_base

            if paz_stato == "In Attesa":
                n_attesa += 1
            elif paz_stato == "Pianificato":
                n_pianificati += 1

            if paz.get("urgenza") not in urgenze:
                continue
            if paz_stato not in stati_filtro:
                continue

            interventi = paz.get("interventi", [])
            all_codici_str = " ".join(i.get("codice", "") for i in interventi)
            if termini:
                match_str = (
                    f"{paz.get('nome','')} {paz.get('cognome','')} "
                    f"{paz.get('codice_intervento','')} {all_codici_str}".lower()
                )
                if any(t not in match_str for t in termini):
                    continue

            codici = [i.get("codice", "") for i in interventi if i.get("codice")]
            codice_display = "  ·  ".join(codici) if codici else paz.get("codice_intervento", "N/D")

            item, widget = self.view.crea_item_lista(
                cognome=paz.get("cognome", "").upper(),
                nome=paz.get("nome", ""),
                codice=codice_display,
                urgenza=paz.get("urgenza", ""),
                stato=paz_stato,
            )
            item.setData(Qt.ItemDataRole.UserRole, paz.get("id"))
            self.view.lista_risultati.addItem(item)
            self.view.lista_risultati.setItemWidget(item, widget)

        self.view.btn_apri.setEnabled(False)
        self.view.aggiorna_conteggi(n_attesa, n_pianificati, len(tutti))

    def gestisci_selezione(self):
        lista = self.view.lista_risultati

        for i in range(lista.count()):
            w = lista.itemWidget(lista.item(i))
            if w:
                w.setProperty("selected", False)
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()

        selezionati = lista.selectedItems()
        if selezionati:
            w = lista.itemWidget(selezionati[0])
            if w:
                w.setProperty("selected", True)
                w.style().unpolish(w)
                w.style().polish(w)
                w.update()
            self.view.btn_apri.setEnabled(True)
        else:
            self.view.btn_apri.setEnabled(False)

    def apri_form_aggiunta(self):
        dialog = DialogNuovoPaziente(self.view)
        if dialog.exec():
            self.model.crea_nuovo_paziente(dialog.get_dati())
            self.aggiorna_lista()

    def apri_form_bulk(self):
        dialog = DialogBulkPazienti(self.view)
        if dialog.exec():
            pazienti = dialog.get_pazienti()
            for dati in pazienti:
                self.model.crea_nuovo_paziente(dati)
            if pazienti:
                QMessageBox.information(
                    self.view,
                    "Inserimento completato",
                    f"{len(pazienti)} pazient{'e' if len(pazienti) == 1 else 'i'} "
                    f"aggiunt{'o' if len(pazienti) == 1 else 'i'} alla lista d'attesa."
                )
            self.aggiorna_lista()

    def modifica_paziente(self):
        if not self._paz_corrente:
            return
        dialog = DialogNuovoPaziente(self.view, paziente_dati=self._paz_corrente)
        if dialog.exec():
            aggiornato = self.model.aggiorna_paziente(
                self._paz_corrente["id"], dialog.get_dati()
            )
            if aggiornato:
                self._paz_corrente = aggiornato
                self.view.imposta_dettaglio(aggiornato)
            self.aggiorna_lista()

    def elimina_paziente(self):
        if not self._paz_corrente:
            return
        nome_display = (
            f"{self._paz_corrente.get('cognome','').upper()} "
            f"{self._paz_corrente.get('nome','')}"
        )
        risposta = QMessageBox.question(
            self.view,
            "Conferma Eliminazione",
            f"Vuoi eliminare definitivamente il paziente {nome_display}?\n\n"
            "Questa operazione non è reversibile.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if risposta == QMessageBox.StandardButton.Yes:
            self.model.elimina_paziente(self._paz_corrente["id"])
            self._paz_corrente = None
            self.aggiorna_lista()
            self.torna_alla_lista()
