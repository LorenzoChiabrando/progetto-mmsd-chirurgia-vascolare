from datetime import date as _date

from PySide6.QtCore import Qt, QDate
from PySide6.QtGui import QColor, QFont
from PySide6.QtWidgets import QListWidgetItem, QMessageBox, QTableWidgetItem
from src.views.view_nuovo_specializzando import DialogNuovoSpecializzando


class ControllerLibretto:
    def __init__(self, view, model_libretto):
        self.view = view
        self.model = model_libretto
        self._spec_corrente = None
        self._attivita_correnti: list = []   # cache piena per i filtri
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
        # Filtri tabella attività
        self.view.filtro_da.dateChanged.connect(self._applica_filtri)
        self.view.filtro_a.dateChanged.connect(self._applica_filtri)
        self.view.filtro_cpx.currentTextChanged.connect(self._applica_filtri)
        self.view.btn_azzera_filtri.clicked.connect(self._azzera_filtri)

    # ─── Navigazione ──────────────────────────────────────────────────────────

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
        self._popola_tabella_attivita(spec["id"])
        self.view.stacked_widget.setCurrentIndex(1)

    def _popola_tabella_attivita(self, spec_id: str):
        """Carica le attività, aggiorna il training score e imposta il range date iniziale."""
        n_int, score = self.model.calcola_training_score(spec_id)
        self._attivita_correnti = self.model.get_attivita(spec_id)

        # Badge training score
        self.view.val_score.setText(
            f"{score:.0f} pt  ·  {n_int} int." if n_int > 0 else "–"
        )

        # Imposta range date dai dati reali (senza scatenare i filtri)
        self.view.filtro_da.blockSignals(True)
        self.view.filtro_a.blockSignals(True)
        self.view.filtro_cpx.blockSignals(True)

        if self._attivita_correnti:
            date_list = []
            for a in self._attivita_correnti:
                try:
                    date_list.append(_date.fromisoformat(a["data"]))
                except (ValueError, KeyError):
                    pass
            if date_list:
                mn = min(date_list)
                self.view.filtro_da.setDate(QDate(mn.year, mn.month, mn.day))
        self.view.filtro_a.setDate(QDate.currentDate())
        self.view.filtro_cpx.setCurrentIndex(0)   # "Tutte"

        self.view.filtro_da.blockSignals(False)
        self.view.filtro_a.blockSignals(False)
        self.view.filtro_cpx.blockSignals(False)

        self._applica_filtri()

    def _applica_filtri(self):
        """Filtra _attivita_correnti per data e complessità e ripopola la tabella."""
        if not self._attivita_correnti and self.view.tabella_libretto.rowCount() == 0:
            return   # nessun libretto aperto ancora

        da_qt = self.view.filtro_da.date()
        a_qt  = self.view.filtro_a.date()
        da = _date(da_qt.year(), da_qt.month(), da_qt.day())
        a  = _date(a_qt.year(),  a_qt.month(),  a_qt.day())
        cpx_sel = self.view.filtro_cpx.currentText()

        filtrate = []
        for att in self._attivita_correnti:
            try:
                d = _date.fromisoformat(att["data"])
            except (ValueError, KeyError):
                continue
            if not (da <= d <= a):
                continue
            if cpx_sel != "Tutte" and att.get("complessita") != cpx_sel:
                continue
            filtrate.append(att)

        # Aggiorna contatore
        tot = len(self._attivita_correnti)
        vis = len(filtrate)
        self.view.lbl_risultati_filtro.setText(
            f"{tot} interventi" if vis == tot else f"{vis} / {tot} interventi"
        )

        # Popola tabella (più recente in cima)
        _colori_cpx = {
            "Alta":  ("#fef2f2", "#dc2626"),
            "Media": ("#fff7ed", "#d97706"),
            "Bassa": ("#f0fdf4", "#16a34a"),
        }
        _colori_ruolo = {
            "OR I":  ("#ede9fe", "#5b21b6"),
            "OR II": ("#dbeafe", "#1d4ed8"),
        }

        table = self.view.tabella_libretto
        table.setRowCount(0)

        for att in reversed(filtrate):
            row = table.rowCount()
            table.insertRow(row)

            try:
                d = _date.fromisoformat(att.get("data", ""))
                data_fmt = d.strftime("%d/%m/%Y")
            except ValueError:
                data_fmt = att.get("data", "")

            cod   = att.get("codice_intervento", "")
            interv = att.get("intervento", "")
            ruolo = att.get("ruolo", "")
            cpx   = att.get("complessita", "")

            valori = [
                data_fmt,
                f"[{cod}]  {interv}" if cod else interv,
                "Sala Operatoria",
                ruolo,
                cpx,
            ]

            for col_idx, testo in enumerate(valori):
                item = QTableWidgetItem(testo)
                item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)

                if col_idx == 3 and ruolo in _colori_ruolo:
                    bg, fg = _colori_ruolo[ruolo]
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                    item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

                if col_idx == 4 and cpx in _colori_cpx:
                    bg, fg = _colori_cpx[cpx]
                    item.setBackground(QColor(bg))
                    item.setForeground(QColor(fg))
                    item.setFont(QFont("Segoe UI", 11, QFont.Weight.Bold))

                table.setItem(row, col_idx, item)

    def _azzera_filtri(self):
        """Ripristina i filtri ai valori iniziali basandosi sui dati del libretto corrente."""
        self.view.filtro_cpx.setCurrentIndex(0)
        if self._attivita_correnti:
            date_list = []
            for a in self._attivita_correnti:
                try:
                    date_list.append(_date.fromisoformat(a["data"]))
                except (ValueError, KeyError):
                    pass
            if date_list:
                mn = min(date_list)
                self.view.filtro_da.setDate(QDate(mn.year, mn.month, mn.day))
        self.view.filtro_a.setDate(QDate.currentDate())

    def torna_ad_anagrafica(self):
        self._spec_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)
        self.view.lista_risultati.clearSelection()

    # ─── Lista ────────────────────────────────────────────────────────────────

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

    # ─── Aggiunta ─────────────────────────────────────────────────────────────

    def apri_form_aggiunta(self):
        dialog = DialogNuovoSpecializzando(self.view)
        if dialog.exec():
            self.model.crea_nuovo_specializzando(dialog.get_dati())
            self.aggiorna_lista()

    # ─── Modifica ─────────────────────────────────────────────────────────────

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

    # ─── Eliminazione ─────────────────────────────────────────────────────────

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
