from datetime import date as _date, timedelta as _td

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListWidgetItem, QMessageBox
from src.views.view_nuovo_specializzando import DialogNuovoSpecializzando

_SLOT_TO_ORE = {
    "8.00-10.00":  ("08:00", "10:00"),
    "10.00-12.00": ("10:00", "12:00"),
    "14.00-16.00": ("14:00", "16:00"),
    "16.00-18.00": ("16:00", "18:00"),
}

_ROW_SEDE = {
    "Sala Op. I":   "Sala Operatoria",
    "Sala Op. II":  "Sala Operatoria",
    "Reparto I":    "Reparto",
    "Reparto II":   "Reparto",
    "Day Hospital": "Day Hospital",
    "Day Surgery":  "Day Surgery",
    "Giro Visite":  "Reparto",
}
_ROW_ATTIVITA = {
    "Sala Op. I":   "Intervento Chirurgico",
    "Sala Op. II":  "Intervento Chirurgico",
    "Reparto I":    "Attività di Reparto",
    "Reparto II":   "Attività di Reparto",
    "Day Hospital": "Day Hospital",
    "Day Surgery":  "Day Surgery",
    "Giro Visite":  "Giro Visite",
}


class ControllerLibretto:
    def __init__(self, view, model_libretto, model_scadenzario=None, model_sale_operatorie=None):
        self.view = view
        self.model = model_libretto
        self.model_scad = model_scadenzario
        self.model_sale_op = model_sale_operatorie

        self._spec_corrente = None
        self._categoria_corrente = "completate"
        self._cache_completate: list = []
        self._cache_pianificate: list = []

        self.setup_connections()
        self.aggiorna_lista()

    def setup_connections(self):
        self.view.chk_attiva_molinette.toggled.connect(self.aggiorna_lista)
        self.view.chk_attiva_altre.toggled.connect(self.aggiorna_lista)
        self.view.chk_storico.toggled.connect(self.aggiorna_lista)
        self.view.search_bar.textChanged.connect(self.aggiorna_lista)
        self.view.lista_risultati.itemSelectionChanged.connect(self.gestisci_selezione)
        self.view.btn_aggiungi.clicked.connect(self.apri_form_aggiunta)
        self.view.btn_apri.clicked.connect(self.apri_dettaglio_libretto)
        self.view.btn_indietro.clicked.connect(self.torna_ad_anagrafica)
        self.view.btn_modifica.clicked.connect(self.modifica_specializzando)
        self.view.btn_elimina.clicked.connect(self.elimina_specializzando)
        self.view.btn_tab_completate.clicked.connect(
            lambda: self._cambia_tab("completate"))
        self.view.btn_tab_pianificate.clicked.connect(
            lambda: self._cambia_tab("pianificate"))
        self.view.lista_attivita.itemClicked.connect(self._on_att_cliccata)
        self.view.btn_indietro_att.clicked.connect(self.torna_a_dettaglio_libretto)

    def apri_dettaglio_libretto(self):
        selezionati = self.view.lista_risultati.selectedItems()
        if not selezionati:
            return
        medico_id = selezionati[0].data(Qt.ItemDataRole.UserRole)
        spec = self.model.get_specializzando_by_id(medico_id)
        if not spec:
            return
        self._spec_corrente = spec
        self.view.imposta_dettaglio(spec)
        self._categoria_corrente = "completate"
        self._aggiorna_cache(spec)
        self._aggiorna_score()
        self._aggiorna_tab_ui()
        self._popola_lista_attivita("completate")
        self.view.stacked_widget.setCurrentIndex(1)

    def torna_ad_anagrafica(self):
        self._spec_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)
        self.view.lista_risultati.clearSelection()

    def torna_a_dettaglio_libretto(self):
        self.view.stacked_widget.setCurrentIndex(1)

    def _cambia_tab(self, categoria: str):
        if categoria == self._categoria_corrente:
            return
        self._categoria_corrente = categoria
        self._aggiorna_tab_ui()
        self._popola_lista_attivita(categoria)

    def _aggiorna_tab_ui(self):
        is_c = self._categoria_corrente == "completate"
        self.view.btn_tab_completate.setChecked(is_c)
        self.view.btn_tab_pianificate.setChecked(not is_c)

    def _aggiorna_cache(self, spec):
        self._cache_completate = self._get_completate(spec)
        self._cache_pianificate = self._get_pianificate(spec)

    def _get_completate(self, spec: dict) -> list:
        """
        Completate = OR convalidate dal libretto (attivita array)
                   + attività non-OR confermate manualmente (attivita_extra).
        Non include attività passate automaticamente: serve conferma esplicita.
        """
        spec_id = spec["id"]
        result  = []

        for att in self.model.get_attivita(spec_id):
            slot  = att.get("slot", "")
            # Preferisce ora_inizio/ora_fine diretti (nuovo formato); fallback su mappa legacy
            ora_i = att.get("ora_inizio") or _SLOT_TO_ORE.get(slot, ("08:00", "18:00"))[0]
            ora_f = att.get("ora_fine")   or _SLOT_TO_ORE.get(slot, ("08:00", "18:00"))[1]
            ruolo = att.get("ruolo", "")
            attiv_label = (
                "Intervento Chirurgico (I op.)"  if ruolo == "OR I"  else
                "Intervento Chirurgico (II op.)" if ruolo == "OR II" else
                "Intervento Chirurgico"
            )
            result.append({
                **att,
                "tipo":       "completata",
                "ora_inizio": ora_i,
                "ora_fine":   ora_f,
                "sede":       "Sala Operatoria",
                "attivita":   attiv_label,
                "intervento": att.get("intervento", ""),
                "note":       att.get("note", ""),
            })

        for extra in self.model.get_attivita_extra(spec_id):
            result.append({**extra, "tipo": "completata"})

        return result

    def _get_pianificate(self, spec: dict) -> list:
        """
        Pianificate = TUTTE le righe scadenzario (passate e future) non ancora confermate.
        Un'attività è confermata quando appare in attivita_extra o attivita array (OR).
        """
        if not self.model_scad:
            return []

        spec_id   = spec["id"]
        nome_form = f"{spec.get('cognome','')} {spec.get('nome','')[:1]}."

        confirmed_keys: set[tuple] = {
            (e["data"], e["sede"], e["attivita"])
            for e in self.model.get_attivita_extra(spec_id)
        }
        date_con_or: set[str] = {
            att.get("data", "") for att in self.model.get_attivita(spec_id)
        }

        result = []

        for anno, mese in self.model_scad.get_mesi_disponibili():
            dati = self.model_scad.load_mese(anno, mese)

            for lun_str, assegnato in dati.get("giro_visite", {}).items():
                if not self._nome_match(assegnato, nome_form):
                    continue
                try:
                    lun_date = _date.fromisoformat(lun_str)
                except ValueError:
                    continue
                # Il giro visite copre tutta la settimana lun–ven
                for offset in range(5):
                    data_str = (lun_date + _td(days=offset)).isoformat()
                    if ("Reparto", "Giro Visite") in {(k[1], k[2]) for k in confirmed_keys if k[0] == data_str}:
                        continue
                    result.append({
                        "data":       data_str,
                        "tipo":       "pianificata",
                        "ora_inizio": "08:00",
                        "ora_fine":   "18:00",
                        "sede":       "Reparto",
                        "attivita":   "Giro Visite",
                        "intervento": "",
                        "ruolo":      "Giro Visite",
                        "note":       "",
                    })

            for data_str, turno in dati.get("turni", {}).items():
                try:
                    _date.fromisoformat(data_str)
                except ValueError:
                    continue
                for row_name, valore in turno.items():
                    if row_name == "Tipo Guardia":
                        continue
                    if not isinstance(valore, str):
                        continue
                    if not self._nome_match(valore, nome_form):
                        continue
                    # OR rows confirmed via attivita array → skip
                    if row_name in ("Sala Op. I", "Sala Op. II") and data_str in date_con_or:
                        continue
                    sede  = _ROW_SEDE.get(row_name, row_name)
                    attiv = _ROW_ATTIVITA.get(row_name, row_name)
                    if (data_str, sede, attiv) in confirmed_keys:
                        continue
                    entry = {
                        "data":       data_str,
                        "tipo":       "pianificata",
                        "ora_inizio": "08:00",
                        "ora_fine":   "18:00",
                        "sede":       sede,
                        "attivita":   attiv,
                        "intervento": "",
                        "ruolo":      row_name,
                        "note":       "",
                    }
                    if row_name in ("Sala Op. I", "Sala Op. II") and self.model_sale_op:
                        slots = []
                        for op in self.model_sale_op.get_operazioni(data_str):
                            if op.get("nome_paziente") or op.get("intervento"):
                                slots.append({
                                    "label": f"{op.get('ora_inizio','?')}–{op.get('ora_fine','?')}",
                                    **op
                                })
                        entry["or_pianificata"] = True
                        entry["slots"] = slots
                    result.append(entry)

        result.sort(key=lambda a: (a["data"], a.get("sede", "")))
        return result

    @staticmethod
    def _nome_match(nome_in_scad: str, nome_form: str) -> bool:
        return nome_in_scad.strip().lower() == nome_form.strip().lower()

    def _popola_lista_attivita(self, categoria: str):
        lista = self.view.lista_attivita
        lista.blockSignals(True)
        lista.clear()

        attivita = (
            self._cache_completate
            if categoria == "completate"
            else self._cache_pianificate
        )

        if not attivita:
            item_vuoto = QListWidgetItem(
                "Nessuna attività presente." if categoria == "completate"
                else "Nessuna attività pianificata nel calendario."
            )
            item_vuoto.setFlags(Qt.ItemFlag.NoItemFlags)
            item_vuoto.setData(Qt.ItemDataRole.UserRole, None)
            lista.addItem(item_vuoto)
            self.view.lbl_n_attivita.setText("0 giorni")
            lista.blockSignals(False)
            return

        if categoria == "completate":
            sorted_att = sorted(attivita, key=lambda a: a.get("data", ""), reverse=True)
        else:
            sorted_att = sorted(attivita, key=lambda a: a.get("data", ""))

        giorni: dict[str, list] = {}
        for att in sorted_att:
            giorni.setdefault(att.get("data", ""), []).append(att)

        hdr_item, hdr_widget = self.view.crea_header_giorni()
        lista.addItem(hdr_item)
        lista.setItemWidget(hdr_item, hdr_widget)

        for data_str, gruppo in giorni.items():
            meta = self.model.get_meta_giorno(self._spec_corrente["id"], data_str)
            g_item, g_widget = self.view.crea_item_giorno(data_str, gruppo, meta)
            lista.addItem(g_item)
            lista.setItemWidget(g_item, g_widget)

        n = len(giorni)
        self.view.lbl_n_attivita.setText(f"{n} {'giorni' if n != 1 else 'giorno'}")
        lista.blockSignals(False)

    def _aggiorna_score(self):
        n_int, score = self.model.calcola_training_score(self._spec_corrente["id"])
        self.view.val_score.setText(
            f"{score:.0f} pt  ·  {n_int} int." if n_int > 0 else "–"
        )

    def _on_att_cliccata(self, item: QListWidgetItem):
        data = item.data(Qt.ItemDataRole.UserRole)
        if data is None:
            return
        self.apri_dettaglio_giorno(data["data"], data["attivita"])

    def apri_dettaglio_giorno(self, data_str: str, attivita: list):
        spec_id = self._spec_corrente["id"]
        extra_dict = {
            (e["data"], e["sede"], e["attivita"]): e
            for e in self.model.get_attivita_extra(spec_id)
        }
        meta = self.model.get_meta_giorno(spec_id, data_str)

        def _on_save(att_data):
            self.model.salva_attivita_extra(spec_id, att_data)
            self._aggiorna_cache(self._spec_corrente)
            self._popola_lista_attivita(self._categoria_corrente)

        def _on_save_meta(meta_data):
            self.model.salva_meta_giorno(spec_id, data_str, meta_data)
            self._popola_lista_attivita(self._categoria_corrente)

        self.view.popola_dettaglio_giorno(
            data_str, attivita, extra_dict,
            on_save=_on_save,
            meta=meta, on_save_meta=_on_save_meta,
        )
        self.view.stacked_widget.setCurrentIndex(2)

    def aggiorna_lista(self):
        self.view.lista_risultati.clear()
        tutti = self.model.get_tutti_specializzandi()
        testo = self.view.search_bar.text().lower().strip()
        termini = testo.split() if testo else []

        stati = []
        if self.view.chk_attiva_molinette.isChecked():
            stati.append("Molinette")
        if self.view.chk_attiva_altre.isChecked():
            stati.append("Altra Sede")
        if self.view.chk_storico.isChecked():
            stati.append("Storico")

        for spec in tutti:
            if spec.get("stato") not in stati:
                continue
            if termini:
                match_str = (
                    f"{spec.get('nome','')} {spec.get('cognome','')} "
                    f"{spec.get('matricola','')}".lower()
                )
                if any(t not in match_str for t in termini):
                    continue

            item, widget = self.view.crea_item_lista(
                cognome=spec.get("cognome", "").upper(),
                nome=spec.get("nome", ""),
                matricola=spec.get("matricola", "N/D"),
                livello=spec.get("livello", ""),
                stato=spec.get("stato", ""),
            )
            item.setData(Qt.ItemDataRole.UserRole, spec.get("id"))
            self.view.lista_risultati.addItem(item)
            self.view.lista_risultati.setItemWidget(item, widget)

        self.view.btn_apri.setEnabled(False)

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
        dialog = DialogNuovoSpecializzando(self.view)
        if dialog.exec():
            self.model.crea_nuovo_specializzando(dialog.get_dati())
            self.aggiorna_lista()

    def modifica_specializzando(self):
        if not self._spec_corrente:
            return
        dialog = DialogNuovoSpecializzando(self.view, spec_dati=self._spec_corrente)
        if dialog.exec():
            spec_aggiornato = self.model.aggiorna_specializzando(
                self._spec_corrente["id"], dialog.get_dati()
            )
            if spec_aggiornato:
                self._spec_corrente = spec_aggiornato
                self.view.imposta_dettaglio(spec_aggiornato)
            self.aggiorna_lista()

    def elimina_specializzando(self):
        if not self._spec_corrente:
            return
        nome_display = (
            f"{self._spec_corrente.get('cognome','').upper()} "
            f"{self._spec_corrente.get('nome','')}"
        )
        risposta = QMessageBox.question(
            self.view,
            "Conferma Eliminazione",
            f"Vuoi eliminare definitivamente il libretto di {nome_display}?\n\n"
            "Questa operazione non è reversibile.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if risposta == QMessageBox.StandardButton.Yes:
            self.model.elimina_specializzando(self._spec_corrente["id"])
            self._spec_corrente = None
            self.aggiorna_lista()
            self.torna_ad_anagrafica()
