import datetime
import random
from PySide6.QtWidgets import (
    QTableWidget, QMessageBox, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QColor

# ── Costanti ──────────────────────────────────────────────────────────────────

SLOT_LABELS = ["8.00-10.00", "10.00-12.00", "14.00-16.00", "16.00-18.00"]

MESI_ITA = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
            "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

GIORNI_ITA = ["LUN", "MAR", "MER", "GIO", "VEN"]

CHIRURGHI_MOCK = [
    "Prof. Rinaldi F.", "Dr. Mauro M.", "Dr. Ferrini A.",
    "Dr. Giordano S.", "Dr. Bianchi L.",
]


# ── Helpers ───────────────────────────────────────────────────────────────────

def _get_lunedi(data: datetime.date) -> datetime.date:
    return data - datetime.timedelta(days=data.weekday())


def _slots_attivi(data: datetime.date) -> list:
    """
    Restituisce i label degli slot orari attivi per un giorno della settimana.
    Schema da documento di progetto:
      Lunedì  (0): solo mattina  08:00–14:00
      Martedì (1): intera giornata 08:00–19:00
      Mercoledì (2): solo mattina 08:00–14:00
      Giovedì (3): intera giornata 08:00–19:00
      Venerdì (4): alterna per settimana ISO (dispari → intera giornata)
    """
    wd = data.weekday()
    if wd in (0, 2):
        return ["8.00-10.00", "10.00-12.00"]
    elif wd in (1, 3):
        return SLOT_LABELS
    elif wd == 4:
        iso_week = data.isocalendar()[1]
        return SLOT_LABELS if iso_week % 2 == 1 else ["8.00-10.00", "10.00-12.00"]
    return []


# ── Controller ────────────────────────────────────────────────────────────────

class ControllerSaleOperatorie:
    """
    Tre modalità:
      STORICO       – lettura settimane passate convalidate
      CONSULTAZIONE – revisione e convalida del piano settimanale
      PIANIFICAZIONE – generazione e modifica del piano
    """

    def __init__(self, view, model, model_scadenzario=None,
                 model_pazienti=None, model_libretto=None):
        self.view = view
        self.model = model
        self.model_scad = model_scadenzario
        self.model_paz = model_pazienti
        self.model_lib = model_libretto
        self.modalita_corrente = None

        self.oggi = datetime.date.today()
        self.settimana_corrente = _get_lunedi(self.oggi)
        self.settimana_display = self.settimana_corrente

        # STORICO: lista ordinata di date (lunedì convalidati) + indice corrente
        self._settimane_convalidate: list[datetime.date] = []
        self._idx_storico: int = 0

        self._connect_signals()

    # ── Segnali ───────────────────────────────────────────────────────────────

    def _connect_signals(self):
        self.view.btn_storico.clicked.connect(
            lambda: self.apri_vista("STORICO"))
        self.view.btn_consultazione.clicked.connect(
            lambda: self.apri_vista("CONSULTAZIONE"))
        self.view.btn_pianificazione.clicked.connect(
            lambda: self.apri_vista("PIANIFICAZIONE"))
        self.view.btn_indietro.clicked.connect(self.torna_alla_dashboard)
        self.view.btn_prev.clicked.connect(self.settimana_precedente)
        self.view.btn_next.clicked.connect(self.settimana_successiva)
        self.view.btn_pianifica.clicked.connect(self.pianifica_settimana)
        self.view.btn_pulisci.clicked.connect(self.pulisci_settimana)
        self.view.btn_convalida.clicked.connect(self.convalida_settimana)
        self.view.tabella.cellChanged.connect(self.salva_modifica_cella)
        self.view.tabella.cellClicked.connect(self._on_cella_cliccata)

    # ── Navigazione ───────────────────────────────────────────────────────────

    def apri_vista(self, modalita):
        self.modalita_corrente = modalita

        if modalita == "STORICO":
            self._settimane_convalidate = self.model.get_settimane_convalidate()
            if not self._settimane_convalidate:
                QMessageBox.information(
                    self.view,
                    "Nessuna settimana convalidata",
                    "Non ci sono ancora settimane convalidate nello storico.\n"
                    "Convalida una settimana dalla sezione Consultazione.",
                )
                return
            # Parte dall'ultima (più recente)
            self._idx_storico = len(self._settimane_convalidate) - 1
            self.settimana_display = self._settimane_convalidate[self._idx_storico]
        else:
            self.settimana_display = self.settimana_corrente

        self.view.stacked_widget.setCurrentIndex(1)
        self.aggiorna_tabella()

    def torna_alla_dashboard(self):
        self.modalita_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)

    def settimana_precedente(self):
        if self.modalita_corrente == "STORICO":
            self._idx_storico -= 1
            self.settimana_display = self._settimane_convalidate[self._idx_storico]
        else:
            self.settimana_display -= datetime.timedelta(weeks=1)
        self.aggiorna_tabella()

    def settimana_successiva(self):
        if self.modalita_corrente == "STORICO":
            self._idx_storico += 1
            self.settimana_display = self._settimane_convalidate[self._idx_storico]
        else:
            self.settimana_display += datetime.timedelta(weeks=1)
        self.aggiorna_tabella()

    # ── Helpers UI ────────────────────────────────────────────────────────────

    def _label_settimana(self) -> str:
        lun = self.settimana_display
        ven = lun + datetime.timedelta(days=4)
        ml = MESI_ITA[lun.month - 1]
        mv = MESI_ITA[ven.month - 1]
        if lun.month == ven.month:
            return f"{lun.day}–{ven.day} {ml} {lun.year}"
        return f"{lun.day} {ml} – {ven.day} {mv} {lun.year}"

    def _gestisci_navigazione(self, stato: str):
        self.view.btn_prev.setVisible(True)
        self.view.btn_next.setVisible(True)

        if self.modalita_corrente == "STORICO":
            self.view.btn_prev.setVisible(self._idx_storico > 0)
            self.view.btn_next.setVisible(
                self._idx_storico < len(self._settimane_convalidate) - 1
            )

        elif self.modalita_corrente == "CONSULTAZIONE":
            self.view.btn_prev.setVisible(False)
            self.view.btn_next.setVisible(False)

        elif self.modalita_corrente == "PIANIFICAZIONE":
            if self.settimana_display <= self.settimana_corrente:
                self.view.btn_prev.setVisible(False)

        # Bottoni PIANIFICA / PULISCI: visibili solo in PIANIFICAZIONE se non convalidato
        show_pianifica = (
            self.modalita_corrente == "PIANIFICAZIONE"
            and stato != "CONVALIDATO"
        )
        self.view.btn_pianifica.setVisible(show_pianifica)
        self.view.btn_pulisci.setVisible(show_pianifica)

        # Bottone CONVALIDA: visibile solo in CONSULTAZIONE se BOZZA
        show_convalida = (
            self.modalita_corrente == "CONSULTAZIONE"
            and stato == "BOZZA"
        )
        self.view.btn_convalida.setVisible(show_convalida)

    # ── Aggiornamento tabella ─────────────────────────────────────────────────

    def aggiorna_tabella(self):
        self.view.tabella.blockSignals(True)

        stato = self.model.get_stato_settimana(self.settimana_display)
        self._gestisci_navigazione(stato)
        self.view.btn_mese_anno.setText(self._label_settimana())

        # Tutte le celle sono sempre in sola lettura; il click apre il popup dettagli
        self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)

        self.view.aggiorna_badge(self.modalita_corrente, stato)

        self.view.tabella.setColumnCount(5)
        self.view.tabella.setHorizontalHeaderLabels(
            ["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])

        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            is_oggi = (data_col == self.oggi)
            giorno_label = (
                f"{GIORNI_ITA[col]}  "
                f"{data_col.day} {MESI_ITA[data_col.month - 1]}"
            )

            # Riga 0: intestazione giorno
            self.view.tabella.setItem(
                0, col, self.view.crea_item_giorno(giorno_label, False, is_oggi))

            # Riga 1: Specializzandi (OR I + OR II) – sempre non editabile
            spec_val = self.model.get_specializzandi(data_str)
            item_spec = self.view.crea_item_cella(spec_val, False, is_oggi)
            item_spec.setFlags(item_spec.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.view.tabella.setItem(1, col, item_spec)

            # Righe 2-5: slot orari
            slots_attivi = _slots_attivi(data_col)
            for idx, slot_label in enumerate(SLOT_LABELS):
                riga = idx + 2
                if slot_label not in slots_attivi:
                    item = self.view.crea_item_cella("", True, is_oggi)
                else:
                    val = self.model.get_slot(data_str, slot_label)
                    item = self.view.crea_item_cella(val, False, is_oggi)
                self.view.tabella.setItem(riga, col, item)

        self.view.tabella.blockSignals(False)

    # ── Pianificazione ────────────────────────────────────────────────────────

    def _ha_piano_esistente(self) -> bool:
        """Controlla se almeno uno slot attivo della settimana ha già un paziente assegnato."""
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            for slot_label in _slots_attivi(data_col):
                slot = self.model.get_slot_raw(data_str, slot_label)
                if slot and isinstance(slot, dict) and slot.get("nome_paziente"):
                    return True
        return False

    def _assegna_pazienti(self):
        """
        Assegna casualmente i pazienti 'In Attesa' agli slot orari attivi
        della settimana corrente. L'ordine è randomizzato ma rispetta la
        priorità urgenza (Alta → Media → Bassa) come punto di partenza.
        Un chirurgo mock viene assegnato a ogni slot.
        """
        if not self.model_paz:
            return

        pazienti = self.model_paz.get_pazienti_in_attesa()
        if not pazienti:
            return

        # Raccoglie tutti gli slot attivi della settimana in ordine
        slots_settimana = []
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            for slot_label in _slots_attivi(data_col):
                slots_settimana.append((data_str, slot_label))

        # Mescola i pazienti all'interno di ogni gruppo di urgenza
        alta = [p for p in pazienti if p.get("urgenza") == "Alta"]
        media = [p for p in pazienti if p.get("urgenza") == "Media"]
        bassa = [p for p in pazienti if p.get("urgenza") == "Bassa"]
        random.shuffle(alta)
        random.shuffle(media)
        random.shuffle(bassa)
        pazienti_ordinati = alta + media + bassa

        chirurghi = CHIRURGHI_MOCK[:]
        random.shuffle(chirurghi)

        for i, (data_str, slot_label) in enumerate(slots_settimana):
            paziente = pazienti_ordinati[i % len(pazienti_ordinati)]
            chirurgo = chirurghi[i % len(chirurghi)]
            nome_paz = f"{paziente.get('cognome', '')} {paziente.get('nome', '')}"
            slot_dict = {
                "nome_paziente": nome_paz,
                "id_paziente": paziente.get("id", ""),
                "diagnosi": paziente.get("diagnosi", ""),
                "intervento": paziente.get("descrizione_intervento", ""),
                "codice_intervento": paziente.get("codice_intervento", ""),
                "chirurgo": chirurgo,
                "complessita": paziente.get("complessita", ""),
                "tipo_chirurgia": paziente.get("tipo_chirurgia", ""),
            }
            self.model.set_slot_data(data_str, slot_label, slot_dict)

    def pianifica_settimana(self):
        """
        Legge dal scadenzario i turni 'Sala Op. I/II' per ogni giorno
        lavorativo, popola il piano degli specializzandi e assegna
        casualmente i pazienti in attesa agli slot orari.
        Se esiste già un piano, chiede conferma prima di sovrascriverlo.
        """
        if not self.model_scad:
            QMessageBox.warning(self.view, "Errore",
                "Dati scadenzario non disponibili.")
            return

        # Verifica che tutti i giorni abbiano entrambi gli specializzandi nello scadenzario
        giorni_mancanti = []
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            scad_data = self.model_scad.load_mese(data_col.year, data_col.month)
            turno = scad_data.get("turni", {}).get(data_str, {})
            or1 = turno.get("Sala Op. I", "").strip()
            or2 = turno.get("Sala Op. II", "").strip()
            if not or1 or not or2:
                etichetta = (
                    f"{GIORNI_ITA[col]} {data_col.day} {MESI_ITA[data_col.month - 1]}"
                )
                mancanti = []
                if not or1:
                    mancanti.append("Sala Op. I")
                if not or2:
                    mancanti.append("Sala Op. II")
                giorni_mancanti.append(f"  • {etichetta}: manca {', '.join(mancanti)}")

        if giorni_mancanti:
            QMessageBox.warning(
                self.view,
                "Impossibile pianificare",
                "Compilare prima lo scadenzario mensile per tutti i giorni.\n\n"
                "Specializzandi mancanti:\n"
                + "\n".join(giorni_mancanti),
            )
            return

        if self._ha_piano_esistente():
            risposta = QMessageBox.question(
                self.view,
                "Ripianifica settimana",
                f"La settimana {self._label_settimana()} ha già un piano.\n\n"
                "Vuoi rigenerarlo sovrascrivendo i dati attuali?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            )
            if risposta != QMessageBox.StandardButton.Yes:
                return

        trovati = 0
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")

            scad_data = self.model_scad.load_mese(data_col.year, data_col.month)
            turno = scad_data.get("turni", {}).get(data_str, {})

            or1 = turno.get("Sala Op. I", "")
            or2 = turno.get("Sala Op. II", "")
            if or1 or or2:
                trovati += 1

            self.model.set_specializzandi(data_str, or1, or2)

        # Assegnazione pazienti agli slot orari
        self._assegna_pazienti()

        self.aggiorna_tabella()

        if trovati > 0:
            n_paz = len(self.model_paz.get_pazienti_in_attesa()) if self.model_paz else 0
            QMessageBox.information(
                self.view,
                "Pianificazione completata",
                f"Piano generato: specializzandi trovati per {trovati}/5 giorni.\n"
                f"Pazienti in lista d'attesa assegnati agli slot disponibili."
            )
        else:
            QMessageBox.warning(
                self.view,
                "Nessun dato specializzandi",
                "Nessuno specializzando trovato in 'Sala Op. I/II' per questa\n"
                "settimana nello scadenzario. Inserisci prima i turni.\n\n"
                "I pazienti sono stati comunque assegnati agli slot."
            )

    # ── Pulizia piano ─────────────────────────────────────────────────────────

    def pulisci_settimana(self):
        risposta = QMessageBox.question(
            self.view,
            "Pulisci piano",
            f"Vuoi eliminare tutte le assegnazioni di pazienti\n"
            f"per la settimana {self._label_settimana()}?\n\n"
            "Gli specializzandi rimarranno invariati.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if risposta != QMessageBox.StandardButton.Yes:
            return

        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            for slot_label in _slots_attivi(data_col):
                self.model.set_slot_data(data_str, slot_label, {})

        self.aggiorna_tabella()

    # ── Convalida ─────────────────────────────────────────────────────────────

    def convalida_settimana(self):
        risposta = QMessageBox.question(
            self.view,
            "Convalida settimana",
            f"Confermi la convalida definitiva della settimana\n"
            f"{self._label_settimana()}?\n\n"
            "L'operazione non sarà reversibile.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if risposta != QMessageBox.StandardButton.Yes:
            return

        self.model.set_stato_settimana(self.settimana_display, "CONVALIDATO")
        self._registra_in_libretti()
        self.aggiorna_tabella()

        QMessageBox.information(
            self.view,
            "Convalida effettuata",
            f"La settimana {self._label_settimana()} è stata convalidata.\n"
            "Le attività operative sono state registrate nei libretti."
        )

    def _registra_in_libretti(self):
        """
        Dopo la convalida, legge gli slot della settimana e scrive un record
        nel libretto di ogni specializzando (OR I e OR II) per ogni intervento.
        """
        if not self.model_lib:
            return

        attivita_per_spec: dict[str, list] = {}

        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")

            dati_mese = self.model.load_mese(data_col.year, data_col.month)
            turno = dati_mese.get("turni", {}).get(data_str, {})
            spec_giorno = turno.get("specializzandi", {})
            or1 = spec_giorno.get("OR I", "")
            or2 = spec_giorno.get("OR II", "")

            for slot_label in _slots_attivi(data_col):
                slot = self.model.get_slot_raw(data_str, slot_label)
                if not slot or not isinstance(slot, dict) or not slot.get("nome_paziente"):
                    continue

                # Complessità e tipo_chirurgia: preferisce i dati già nello slot,
                # altrimenti li recupera dal model pazienti
                complessita = slot.get("complessita", "")
                tipo_chirurgia = slot.get("tipo_chirurgia", "")
                if (not complessita or not tipo_chirurgia) and self.model_paz:
                    paz = self.model_paz.get_paziente_by_id(slot.get("id_paziente", ""))
                    if paz:
                        complessita = complessita or paz.get("complessita", "")
                        tipo_chirurgia = tipo_chirurgia or paz.get("tipo_chirurgia", "")

                base_att = {
                    "data": data_str,
                    "slot": slot_label,
                    "nome_paziente": slot.get("nome_paziente", ""),
                    "id_paziente": slot.get("id_paziente", ""),
                    "diagnosi": slot.get("diagnosi", ""),
                    "intervento": slot.get("intervento", ""),
                    "codice_intervento": slot.get("codice_intervento", ""),
                    "chirurgo": slot.get("chirurgo", ""),
                    "complessita": complessita,
                    "tipo_chirurgia": tipo_chirurgia,
                }

                for ruolo, nome_spec in [("OR I", or1), ("OR II", or2)]:
                    if not nome_spec:
                        continue
                    att = {**base_att, "ruolo": ruolo}
                    attivita_per_spec.setdefault(nome_spec, []).append(att)

        if attivita_per_spec:
            self.model_lib.registra_attivita_settimana(attivita_per_spec)

    # ── Salvataggio celle ─────────────────────────────────────────────────────

    def salva_modifica_cella(self, riga, colonna):
        if riga <= 1:
            return
        if self.modalita_corrente != "PIANIFICAZIONE":
            return

        stato = self.model.get_stato_settimana(self.settimana_display)
        if stato == "CONVALIDATO":
            return

        data_col = self.settimana_display + datetime.timedelta(days=colonna)
        data_str = data_col.strftime("%Y-%m-%d")

        slot_label = SLOT_LABELS[riga - 2]
        if slot_label not in _slots_attivi(data_col):
            return

        item = self.view.tabella.item(riga, colonna)
        nuovo_valore = item.text() if item else ""
        self.model.set_valore_cella(data_str, slot_label, nuovo_valore)

    # ── Popup dettagli paziente ───────────────────────────────────────────────

    def _on_cella_cliccata(self, riga, colonna):
        """Apre il popup con i dettagli del paziente se la cella contiene un'assegnazione."""
        if riga < 2:
            return

        data_col = self.settimana_display + datetime.timedelta(days=colonna)
        data_str = data_col.strftime("%Y-%m-%d")
        slot_label = SLOT_LABELS[riga - 2]

        if slot_label not in _slots_attivi(data_col):
            return

        slot = self.model.get_slot_raw(data_str, slot_label)
        if not slot or not slot.get("nome_paziente"):
            return

        # Arricchisce con dati anagrafici dal model pazienti se disponibile
        paz_full = None
        if self.model_paz and slot.get("id_paziente"):
            paz_full = self.model_paz.get_paziente_by_id(slot["id_paziente"])

        self._mostra_popup_paziente(slot, paz_full)

    def _mostra_popup_paziente(self, slot: dict, paz_full: dict | None):
        import os
        dialog = QDialog(self.view)
        dialog.setWindowTitle("Dettagli Paziente")
        dialog.setModal(True)
        dialog.setMinimumWidth(500)
        dialog.setSizeGripEnabled(False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        # Carica lo stesso stylesheet dei dialog paziente
        style_path = os.path.join("asset", "styles", "pazienti.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                dialog.setStyleSheet(f.read())
        # Forza lo sfondo chiaro sul QDialog (la regola DialogNuovoPaziente non si propaga)
        dialog.setStyleSheet(
            dialog.styleSheet() +
            "\nQDialog { background-color: #f8fafc; }"
        )

        root = QVBoxLayout(dialog)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(16)

        # ── Titolo ───────────────────────────────────────────────────────────
        lbl_titolo = QLabel(slot.get("nome_paziente", "—"))
        lbl_titolo.setObjectName("TitoloDialog")
        lbl_titolo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(lbl_titolo)

        id_paz = slot.get("id_paziente", "")
        lbl_sub = QLabel(id_paz if id_paz else "Scheda paziente")
        lbl_sub.setObjectName("SottoTitoloDialog")
        lbl_sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        root.addWidget(lbl_sub)

        sep = QFrame()
        sep.setObjectName("SeparatoreDialog")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        # ── Campi ────────────────────────────────────────────────────────────
        def _riga(etichetta: str, valore: str):
            row = QHBoxLayout()
            row.setSpacing(12)
            lbl_k = QLabel(etichetta.upper())
            lbl_k.setObjectName("LblCampo")
            lbl_k.setFixedWidth(150)
            lbl_v = QLabel(valore or "—")
            lbl_v.setWordWrap(True)
            lbl_v.setStyleSheet("color: #1e293b; font-size: 14px;")
            row.addWidget(lbl_k)
            row.addWidget(lbl_v, 1)
            root.addLayout(row)

        cod = slot.get("codice_intervento", "")
        inter = slot.get("intervento", "")
        _riga("Diagnosi", slot.get("diagnosi", ""))
        _riga("Intervento", f"[{cod}]  {inter}" if cod else inter)

        if paz_full:
            _riga("Tipo chirurgia", paz_full.get("tipo_chirurgia", ""))
            _riga("Complessità", paz_full.get("complessita", ""))

            urgenza = paz_full.get("urgenza", "")
            colori_urg = {"Alta": "#dc2626", "Media": "#d97706", "Bassa": "#16a34a"}
            lbl_urg_row = QHBoxLayout()
            lbl_urg_row.setSpacing(12)
            lbl_urg_k = QLabel("URGENZA")
            lbl_urg_k.setObjectName("LblCampo")
            lbl_urg_k.setFixedWidth(150)
            lbl_urg_v = QLabel(urgenza or "—")
            lbl_urg_v.setStyleSheet(
                f"color: {colori_urg.get(urgenza, '#334155')}; "
                "font-size: 14px; font-weight: bold;"
            )
            lbl_urg_row.addWidget(lbl_urg_k)
            lbl_urg_row.addWidget(lbl_urg_v, 1)
            root.addLayout(lbl_urg_row)

        _riga("Chirurgo", slot.get("chirurgo", ""))

        if paz_full:
            _riga("Inserito il", paz_full.get("data_inserimento", ""))
            note = paz_full.get("note", "").strip()
            if note:
                _riga("Note cliniche", note)

        # ── Pulsante chiudi ───────────────────────────────────────────────────
        btn_chiudi = QPushButton("Chiudi")
        btn_chiudi.setObjectName("BtnAnnullaDialog")
        btn_chiudi.setFixedHeight(44)
        btn_chiudi.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_chiudi.clicked.connect(dialog.accept)
        root.addWidget(btn_chiudi)

        dialog.exec()
