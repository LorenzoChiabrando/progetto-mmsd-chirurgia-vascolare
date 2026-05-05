import datetime
import random
import os as _os
from src.app_paths import get_asset_dir
from PySide6.QtWidgets import (
    QTableWidget, QDialog, QVBoxLayout, QHBoxLayout,
    QLabel, QFrame, QPushButton, QListWidget, QListWidgetItem,
)
from PySide6.QtCore import Qt, QSize

MESI_ITA = ["Gen", "Feb", "Mar", "Apr", "Mag", "Giu",
            "Lug", "Ago", "Set", "Ott", "Nov", "Dic"]

GIORNI_ITA = ["LUN", "MAR", "MER", "GIO", "VEN"]

CHIRURGHI_MOCK = [
    "Prof. Rinaldi F.", "Dr. Mauro M.", "Dr. Ferrini A.",
    "Dr. Giordano S.", "Dr. Bianchi L.",
]


def _get_lunedi(data: datetime.date) -> datetime.date:
    return data - datetime.timedelta(days=data.weekday())


def _finestra_giorno(data: datetime.date) -> tuple:
    """Ritorna (ora_inizio_str, ora_fine_str, minuti_tot) per il giorno."""
    return ("08:00", "18:00", 600)


def _str_to_min(s: str) -> int:
    h, m = map(int, s.split(":"))
    return h * 60 + m


def _min_to_str(m: int) -> str:
    return f"{m // 60:02d}:{m % 60:02d}"


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

        self._settimane_convalidate: list[datetime.date] = []
        self._idx_storico: int = 0
        self._stato_corrente: str = "BOZZA"

        self._connect_signals()

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
        self.view.tabella.operazione_spostata.connect(self._sposta_operazione)
        self.view.tabella.operazione_scambiata.connect(self._scambia_operazioni)

    def apri_vista(self, modalita):
        self.modalita_corrente = modalita

        if modalita == "STORICO":
            self._settimane_convalidate = self.model.get_settimane_convalidate()
            if not self._settimane_convalidate:
                self._avviso(
                    "Nessuna settimana convalidata",
                    "Non ci sono ancora settimane convalidate nello storico.\n"
                    "Convalida una settimana dalla sezione Consultazione.",
                )
                return
            self._idx_storico = len(self._settimane_convalidate) - 1
            self.settimana_display = self._settimane_convalidate[self._idx_storico]
        elif modalita == "CONSULTAZIONE":
            self.settimana_display = self.settimana_corrente

        elif modalita == "PIANIFICAZIONE":
            self.settimana_display = self.settimana_corrente + datetime.timedelta(weeks=1)

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

    def _label_settimana(self) -> str:
        lun = self.settimana_display
        ven = lun + datetime.timedelta(days=4)
        ml = MESI_ITA[lun.month - 1]
        mv = MESI_ITA[ven.month - 1]
        if lun.month == ven.month:
            return f"{lun.day}–{ven.day} {ml} {lun.year}"
        return f"{lun.day} {ml} – {ven.day} {mv} {lun.year}"

    def _load_style(self):
        path = str(get_asset_dir() / "styles" / "pazienti.qss")
        return open(path, encoding="utf-8").read() if _os.path.exists(path) else ""

    def _avviso(self, titolo: str, messaggio: str, tipo: str = "info", parent=None):
        """Dialog informativo/warning coerente con lo stile app."""
        accent = "#d97706" if tipo == "warning" else "#0369a1"
        dlg = QDialog(parent or self.view)
        dlg.setWindowTitle(titolo)
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.setStyleSheet(self._load_style() + "\nQDialog { background-color: #ffffff; }")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        bar = QFrame()
        bar.setFixedHeight(5)
        bar.setStyleSheet(f"background-color:{accent}; border:none;")
        root.addWidget(bar)
        inner = QVBoxLayout()
        inner.setContentsMargins(30, 22, 30, 22)
        inner.setSpacing(10)
        root.addLayout(inner)
        lbl_t = QLabel(titolo)
        lbl_t.setObjectName("TitoloDialog")
        lbl_t.setStyleSheet(f"color:{accent};")
        inner.addWidget(lbl_t)
        lbl_m = QLabel(messaggio)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet("color:#334155; font-size:14px;")
        inner.addWidget(lbl_m)
        inner.addSpacing(6)
        btn = QPushButton("OK")
        btn.setObjectName("BtnSalvaDialog")
        btn.setFixedHeight(44)
        btn.setCursor(Qt.CursorShape.PointingHandCursor)
        btn.clicked.connect(dlg.accept)
        inner.addWidget(btn)
        dlg.exec()

    def _conferma(self, titolo: str, messaggio: str,
                  testo_si: str = "Conferma", parent=None) -> bool:
        """Dialog Yes/No coerente con lo stile app. Ritorna True se confermato."""
        dlg = QDialog(parent or self.view)
        dlg.setWindowTitle(titolo)
        dlg.setModal(True)
        dlg.setMinimumWidth(420)
        dlg.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dlg.setStyleSheet(self._load_style() + "\nQDialog { background-color: #ffffff; }")

        root = QVBoxLayout(dlg)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)
        bar = QFrame()
        bar.setFixedHeight(5)
        bar.setStyleSheet("background-color:#0369a1; border:none;")
        root.addWidget(bar)
        inner = QVBoxLayout()
        inner.setContentsMargins(30, 22, 30, 22)
        inner.setSpacing(10)
        root.addLayout(inner)
        lbl_t = QLabel(titolo)
        lbl_t.setObjectName("TitoloDialog")
        inner.addWidget(lbl_t)
        lbl_m = QLabel(messaggio)
        lbl_m.setWordWrap(True)
        lbl_m.setStyleSheet("color:#334155; font-size:14px;")
        inner.addWidget(lbl_m)
        inner.addSpacing(6)
        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_no = QPushButton("Annulla")
        btn_no.setObjectName("BtnAnnullaDialog")
        btn_no.setFixedHeight(44)
        btn_no.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_no.clicked.connect(dlg.reject)
        btn_si = QPushButton(testo_si)
        btn_si.setObjectName("BtnSalvaDialog")
        btn_si.setFixedHeight(44)
        btn_si.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_si.clicked.connect(dlg.accept)
        btn_row.addWidget(btn_no)
        btn_row.addWidget(btn_si)
        inner.addLayout(btn_row)
        return dlg.exec() == QDialog.DialogCode.Accepted

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
            next_week = self.settimana_corrente + datetime.timedelta(weeks=1)
            if self.settimana_display <= next_week:
                self.view.btn_prev.setVisible(False)

        show_pianifica = (
            self.modalita_corrente in ("PIANIFICAZIONE", "CONSULTAZIONE")
            and stato != "CONVALIDATO"
        )
        self.view.btn_pianifica.setVisible(show_pianifica)
        self.view.btn_pulisci.setVisible(show_pianifica)

        show_convalida = (
            self.modalita_corrente == "CONSULTAZIONE"
            and stato == "BOZZA"
        )
        self.view.btn_convalida.setVisible(show_convalida)

    def aggiorna_tabella(self):
        self.view.tabella.blockSignals(True)
        stato = self.model.get_stato_settimana(self.settimana_display)
        self._stato_corrente = stato
        self._gestisci_navigazione(stato)
        self.view.btn_mese_anno.setText(self._label_settimana())
        self.view.tabella.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.view.aggiorna_badge(self.modalita_corrente, stato)
        self.view.tabella.setColumnCount(5)
        self.view.tabella.setHorizontalHeaderLabels(["Lunedì", "Martedì", "Mercoledì", "Giovedì", "Venerdì"])

        can_edit = (
            self.modalita_corrente in ("PIANIFICAZIONE", "CONSULTAZIONE")
            and stato != "CONVALIDATO"
        )

        max_ops_sett = 0
        for col in range(5):
            data_str = (self.settimana_display + datetime.timedelta(days=col)).strftime("%Y-%m-%d")
            max_ops_sett = max(max_ops_sett, len(self.model.get_operazioni(data_str)))
        self.view.adatta_righe_operazioni(max_ops_sett)

        drop_targets: dict = {}
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            is_oggi = (data_col == self.oggi)

            giorno_label = f"{GIORNI_ITA[col]}  {data_col.day} {MESI_ITA[data_col.month - 1]}"
            self.view.tabella.setItem(0, col, self.view.crea_item_giorno(giorno_label, False, is_oggi))

            spec_val = self.model.get_specializzandi(data_str)
            item_spec = self.view.crea_item_cella(spec_val, False, is_oggi)
            item_spec.setFlags(item_spec.flags() & ~Qt.ItemFlag.ItemIsEditable)
            self.view.tabella.setItem(1, col, item_spec)

            operazioni = self.model.get_operazioni(data_str)
            drop_targets[col] = 2 + len(operazioni)
            for op_idx in range(self.view.current_max_ops):
                row = op_idx + 2
                if op_idx < len(operazioni):
                    op = operazioni[op_idx]
                    ha_paziente = bool(op.get("nome_paziente"))
                    on_click = (lambda r=row, c=col: self._on_cella_cliccata(r, c)) if ha_paziente else None
                    widget = self.view.crea_widget_operazione(
                        op, is_oggi, on_click,
                        draggable=can_edit and ha_paziente,
                        col=col, op_idx=op_idx,
                    )
                    self.view.tabella.setCellWidget(row, col, widget)
                else:
                    on_click_vuoto = None
                    if can_edit and op_idx == len(operazioni):
                        on_click_vuoto = (lambda r=row, c=col: self._on_slot_vuoto_cliccato(r, c))
                    self.view.tabella.setCellWidget(row, col, self.view.crea_widget_vuoto(is_oggi, on_click_vuoto))

        self.view.tabella.set_drop_targets(drop_targets if can_edit else {})
        self.view.tabella.blockSignals(False)

    def _ha_piano_esistente(self) -> bool:
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            ops = self.model.get_operazioni(data_str)
            if any(op.get("nome_paziente") for op in ops):
                return True
        return False

    def _assegna_pazienti(self):
        if not self.model_paz:
            return
        gia_pianificati = self.model.get_pazienti_pianificati_ids(exclude_lun_date=self.settimana_display)
        tutti_attesa = self.model_paz.get_pazienti_in_attesa()
        pazienti = [p for p in tutti_attesa if p.get("id") not in gia_pianificati]
        if not pazienti:
            return

        alta  = [p for p in pazienti if p.get("urgenza") == "Alta"]
        media = [p for p in pazienti if p.get("urgenza") == "Media"]
        bassa = [p for p in pazienti if p.get("urgenza") == "Bassa"]
        random.shuffle(alta); random.shuffle(media); random.shuffle(bassa)
        pool = alta + media + bassa

        assegnati: set = set()
        paz_idx = 0
        chirurghi_base = CHIRURGHI_MOCK[:]

        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            ora_i_str, ora_f_str, _ = _finestra_giorno(data_col)
            min_corrente = _str_to_min(ora_i_str)
            min_fine     = _str_to_min(ora_f_str)

            ore_random = random.choice([2, 2, 4, 4, 4, 6, 6, 6, 8, 10])
            min_stop = min(min_corrente + ore_random * 60, min_fine)

            chirurghi = chirurghi_base[:]
            random.shuffle(chirurghi)
            operazioni = []

            while True:
                paziente = None
                for i in range(len(pool)):
                    c = pool[(paz_idx + i) % len(pool)]
                    if c.get("id") not in assegnati:
                        paziente = c
                        paz_idx = (paz_idx + i + 1) % max(len(pool), 1)
                        break
                if paziente is None:
                    break
                durata = paziente.get("durata_intervento", 90)
                if min_corrente + durata > min_stop:
                    break
                chirurgo = chirurghi[len(operazioni) % len(chirurghi)]
                interventi_paz = paziente.get("interventi") or [{
                    "codice": paziente.get("codice_intervento", ""),
                    "descrizione": paziente.get("descrizione_intervento", ""),
                    "durata": durata,
                }]
                op = {
                    "nome_paziente":    f"{paziente.get('cognome','')} {paziente.get('nome','')}",
                    "id_paziente":      paziente.get("id", ""),
                    "diagnosi":         paziente.get("diagnosi", ""),
                    "intervento":       interventi_paz[0].get("descrizione", "") if interventi_paz else "",
                    "codice_intervento":interventi_paz[0].get("codice", "") if interventi_paz else "",
                    "interventi":       interventi_paz,
                    "chirurgo":         chirurgo,
                    "complessita":      paziente.get("complessita", ""),
                    "tipo_chirurgia":   paziente.get("tipo_chirurgia", ""),
                    "durata":           durata,
                    "ora_inizio":       _min_to_str(min_corrente),
                    "ora_fine":         _min_to_str(min_corrente + durata),
                }
                operazioni.append(op)
                assegnati.add(paziente.get("id", ""))
                min_corrente += durata

            self.model.set_operazioni(data_str, operazioni)

    def pianifica_settimana(self):
        """
        Legge dal scadenzario i turni 'Sala Op. I/II' per ogni giorno
        lavorativo, popola il piano degli specializzandi e assegna
        casualmente i pazienti in attesa in operazioni sequenziali.
        Se esiste già un piano, chiede conferma prima di sovrascriverlo.
        """
        if not self.model_scad:
            self._avviso("Errore", "Dati scadenzario non disponibili.", tipo="warning")
            return

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
            self._avviso(
                "Impossibile pianificare",
                "Compilare prima lo scadenzario mensile per tutti i giorni.\n\n"
                "Specializzandi mancanti:\n" + "\n".join(giorni_mancanti),
                tipo="warning",
            )
            return

        if self._ha_piano_esistente():
            if not self._conferma(
                "Ripianifica settimana",
                f"La settimana {self._label_settimana()} ha già un piano.\n\n"
                "Vuoi rigenerarlo sovrascrivendo i dati attuali?",
                testo_si="Rigenera",
            ):
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

        self._assegna_pazienti()

        self.aggiorna_tabella()

        if trovati > 0:
            self._avviso(
                "Pianificazione completata",
                f"Piano generato: specializzandi trovati per {trovati}/5 giorni.\n"
                "Pazienti liberi in attesa assegnati in operazioni sequenziali.",
            )
        else:
            self._avviso(
                "Nessun dato specializzandi",
                "Nessuno specializzando trovato in 'Sala Op. I/II' per questa\n"
                "settimana nello scadenzario. Inserisci prima i turni.\n\n"
                "I pazienti sono stati comunque assegnati alle operazioni.",
                tipo="warning",
            )

    def pulisci_settimana(self):
        if not self._conferma(
            "Pulisci piano",
            f"Vuoi eliminare tutte le assegnazioni di pazienti\n"
            f"per la settimana {self._label_settimana()}?\n\n"
            "Gli specializzandi rimarranno invariati.",
            testo_si="Pulisci",
        ):
            return

        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            self.model.set_operazioni(data_str, [])

        self.aggiorna_tabella()

    def convalida_settimana(self):
        if not self._conferma(
            "Convalida settimana",
            f"Confermi la convalida definitiva della settimana\n"
            f"{self._label_settimana()}?\n\n"
            "L'operazione non sarà reversibile.",
            testo_si="Convalida",
        ):
            return

        self.model.set_stato_settimana(self.settimana_display, "CONVALIDATO")
        self._registra_in_libretti()
        self._segna_pazienti_completati()
        self.aggiorna_tabella()

        self._avviso(
            "Convalida effettuata",
            f"La settimana {self._label_settimana()} è stata convalidata.\n"
            "Le attività operative sono state registrate nei libretti.",
        )

    def _segna_pazienti_completati(self):
        """Segna come Completato ogni paziente che ha un'operazione nella settimana appena convalidata."""
        if not self.model_paz:
            return
        for col in range(5):
            data_col = self.settimana_display + datetime.timedelta(days=col)
            data_str = data_col.strftime("%Y-%m-%d")
            for op in self.model.get_operazioni(data_str):
                paz_id = op.get("id_paziente", "")
                if paz_id:
                    self.model_paz.aggiorna_stato_paziente(paz_id, "Completato")

    def _registra_in_libretti(self):
        """
        Dopo la convalida, legge le operazioni della settimana e scrive un record
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
            for op in self.model.get_operazioni(data_str):
                if not op.get("nome_paziente"):
                    continue
                complessita = op.get("complessita", "")
                tipo_chirurgia = op.get("tipo_chirurgia", "")
                if (not complessita or not tipo_chirurgia) and self.model_paz:
                    paz = self.model_paz.get_paziente_by_id(op.get("id_paziente", ""))
                    if paz:
                        complessita = complessita or paz.get("complessita", "")
                        tipo_chirurgia = tipo_chirurgia or paz.get("tipo_chirurgia", "")
                base_att = {
                    "data": data_str,
                    "slot": op.get("ora_inizio", "08:00"),
                    "nome_paziente": op.get("nome_paziente", ""),
                    "id_paziente": op.get("id_paziente", ""),
                    "diagnosi": op.get("diagnosi", ""),
                    "intervento": op.get("intervento", ""),
                    "codice_intervento": op.get("codice_intervento", ""),
                    "interventi": op.get("interventi", []),
                    "chirurgo": op.get("chirurgo", ""),
                    "complessita": complessita,
                    "tipo_chirurgia": tipo_chirurgia,
                    "ora_inizio": op.get("ora_inizio", "08:00"),
                    "ora_fine": op.get("ora_fine", "18:00"),
                    "durata": op.get("durata", 90),
                }
                for ruolo, nome_spec in [("OR I", or1), ("OR II", or2)]:
                    if not nome_spec:
                        continue
                    att = {**base_att, "ruolo": ruolo}
                    attivita_per_spec.setdefault(nome_spec, []).append(att)
        if attivita_per_spec:
            self.model_lib.registra_attivita_settimana(attivita_per_spec)

    def _ricalcola_orari(self, operazioni: list):
        """Ricalcola ora_inizio / ora_fine di ogni operazione sequenzialmente dal 08:00."""
        min_corrente = _str_to_min("08:00")
        for op in operazioni:
            durata = op.get("durata", 0)
            op["ora_inizio"] = _min_to_str(min_corrente)
            op["ora_fine"] = _min_to_str(min_corrente + durata)
            min_corrente += durata

    def _scambia_operazioni(self, col: int, src_idx: int, dst_idx: int):
        """Swap di due operazioni nello stesso giorno, con conferma modal."""
        if (self.modalita_corrente not in ("PIANIFICAZIONE", "CONSULTAZIONE")
                or self._stato_corrente == "CONVALIDATO"):
            return

        data_col = self.settimana_display + datetime.timedelta(days=col)
        data_str = data_col.strftime("%Y-%m-%d")
        operazioni = self.model.get_operazioni(data_str)

        if src_idx >= len(operazioni) or dst_idx >= len(operazioni):
            return

        nome_src = operazioni[src_idx].get("nome_paziente", "—")
        nome_dst = operazioni[dst_idx].get("nome_paziente", "—")
        giorno = GIORNI_ITA[col]
        mese = MESI_ITA[data_col.month - 1]

        if not self._conferma(
            "Scambia operazioni",
            f"Vuoi scambiare l'ordine di queste due operazioni\n"
            f"del {giorno} {data_col.day} {mese}?\n\n"
            f"  • {nome_src}\n"
            f"  • {nome_dst}\n\n"
            "Gli orari verranno ricalcolati automaticamente.",
            testo_si="Scambia",
        ):
            self.aggiorna_tabella()
            return

        operazioni[src_idx], operazioni[dst_idx] = operazioni[dst_idx], operazioni[src_idx]
        self._ricalcola_orari(operazioni)
        self.model.set_operazioni(data_str, operazioni)
        self.aggiorna_tabella()

    def _sposta_operazione(self, src_col: int, src_op_idx: int, dst_col: int):
        """Sposta un'operazione da un giorno a un altro (in coda) e salva il JSON."""
        if (self.modalita_corrente not in ("PIANIFICAZIONE", "CONSULTAZIONE")
                or self._stato_corrente == "CONVALIDATO"):
            return

        src_date = self.settimana_display + datetime.timedelta(days=src_col)
        dst_date = self.settimana_display + datetime.timedelta(days=dst_col)
        src_str = src_date.strftime("%Y-%m-%d")
        dst_str = dst_date.strftime("%Y-%m-%d")

        src_ops = self.model.get_operazioni(src_str)
        dst_ops = self.model.get_operazioni(dst_str)

        if src_op_idx >= len(src_ops):
            return

        op = src_ops.pop(src_op_idx)
        dst_ops.append(op)

        self._ricalcola_orari(src_ops)
        self._ricalcola_orari(dst_ops)

        self.model.set_operazioni(src_str, src_ops)
        self.model.set_operazioni(dst_str, dst_ops)

        self.aggiorna_tabella()

    def _rimuovi_paziente_da_slot(self, dialog, data_str: str, op_idx: int):
        if not self._conferma(
            "Rimuovi paziente",
            "Vuoi rimuovere questo paziente dal piano?\n\nIl paziente tornerà in lista d'attesa.",
            testo_si="Rimuovi",
            parent=dialog,
        ):
            return
        operazioni = self.model.get_operazioni(data_str)
        if op_idx < len(operazioni):
            operazioni.pop(op_idx)
            self._ricalcola_orari(operazioni)
            self.model.set_operazioni(data_str, operazioni)
            self.aggiorna_tabella()
        dialog.accept()

    def _mostra_dialog_inserimento_manuale(self, data_str: str, data_col, ora_inizio_min: int):
        import random as _rnd

        if not self.model_paz:
            self._avviso("Errore", "Dati pazienti non disponibili.", tipo="warning")
            return

        gia_pianificati = self.model.get_pazienti_pianificati_ids()
        disponibili = [
            p for p in self.model_paz.get_pazienti_in_attesa()
            if p.get("id") not in gia_pianificati
        ]
        if not disponibili:
            self._avviso(
                "Nessun paziente disponibile",
                "Non ci sono pazienti in lista d'attesa da inserire.",
            )
            return

        dialog = QDialog(self.view)
        giorno_nome = GIORNI_ITA[data_col.weekday()]
        mese_nome   = MESI_ITA[data_col.month - 1]
        dialog.setWindowTitle(f"Inserimento manuale — {giorno_nome} {data_col.day} {mese_nome}")
        dialog.setModal(True)
        dialog.setMinimumWidth(560)
        dialog.setMinimumHeight(540)
        dialog.setSizeGripEnabled(True)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)

        dialog.setStyleSheet(self._load_style() + "\nQDialog { background-color: #f8fafc; }")

        root = QVBoxLayout(dialog)
        root.setContentsMargins(28, 24, 28, 24)
        root.setSpacing(12)

        lbl_titolo = QLabel("Inserimento manuale")
        lbl_titolo.setObjectName("TitoloDialog")
        root.addWidget(lbl_titolo)

        lbl_sub = QLabel(
            f"Seleziona un paziente da aggiungere — "
            f"{giorno_nome} {data_col.day} {mese_nome} {data_col.year}"
        )
        lbl_sub.setObjectName("SottoTitoloDialog")
        root.addWidget(lbl_sub)

        sep = QFrame()
        sep.setObjectName("SeparatoreDialog")
        sep.setFixedHeight(1)
        root.addWidget(sep)

        lbl_lista = QLabel("PAZIENTI IN LISTA D'ATTESA")
        lbl_lista.setObjectName("LblCampo")
        root.addWidget(lbl_lista)

        lista_widget = QListWidget()
        lista_widget.setObjectName("ListaRisultati")
        lista_widget.setSpacing(4)
        root.addWidget(lista_widget, 1)

        _COLORI_URG = {
            "Alta":  ("#fee2e2", "#dc2626"),
            "Media": ("#fef9c3", "#d97706"),
            "Bassa": ("#dcfce7", "#15803d"),
        }
        for paz in disponibili:
            interventi = paz.get("interventi", [])
            codici = [i.get("codice", "") for i in interventi if i.get("codice")]
            cod_text = "  ·  ".join(codici) if codici else paz.get("codice_intervento", "N/D")
            durata = paz.get("durata_intervento", 90)
            urg = paz.get("urgenza", "")
            bg_u, fg_u = _COLORI_URG.get(urg, ("#f1f5f9", "#475569"))

            item_frame = QFrame()
            item_frame.setObjectName("ItemCard")
            item_frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
            row_lay = QHBoxLayout(item_frame)
            row_lay.setContentsMargins(14, 10, 14, 10)
            row_lay.setSpacing(12)

            badge_u = QLabel(urg or "–")
            badge_u.setAlignment(Qt.AlignmentFlag.AlignCenter)
            badge_u.setFixedWidth(56)
            badge_u.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            badge_u.setStyleSheet(
                f"background-color:{bg_u}; color:{fg_u}; font-weight:bold; "
                f"font-size:11px; padding:3px 6px; border-radius:10px; border:1px solid {fg_u}50;"
            )

            txt = QVBoxLayout()
            txt.setSpacing(2)
            lbl_np = QLabel(f"{paz.get('cognome','').upper()} {paz.get('nome','')}")
            lbl_np.setObjectName("ItemNome")
            lbl_np.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            lbl_cp = QLabel(f"{cod_text}  ·  {durata} min")
            lbl_cp.setObjectName("ItemMatricola")
            lbl_cp.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
            txt.addWidget(lbl_np)
            txt.addWidget(lbl_cp)

            row_lay.addWidget(badge_u)
            row_lay.addLayout(txt, 1)

            item = QListWidgetItem()
            item.setSizeHint(QSize(0, 62))
            item.setData(Qt.ItemDataRole.UserRole, paz.get("id"))
            lista_widget.addItem(item)
            lista_widget.setItemWidget(item, item_frame)

        lbl_timing = QLabel("Seleziona un paziente per vedere l'orario proposto")
        lbl_timing.setObjectName("SottoTitoloDialog")
        lbl_timing.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_timing.setFixedHeight(38)
        root.addWidget(lbl_timing)

        sep2 = QFrame()
        sep2.setObjectName("SeparatoreDialog")
        sep2.setFixedHeight(1)
        root.addWidget(sep2)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)
        btn_annulla = QPushButton("Annulla")
        btn_annulla.setObjectName("BtnAnnullaDialog")
        btn_annulla.setFixedHeight(44)
        btn_annulla.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_annulla.clicked.connect(dialog.reject)
        btn_inserisci = QPushButton("Inserisci")
        btn_inserisci.setObjectName("BtnSalvaDialog")
        btn_inserisci.setFixedHeight(44)
        btn_inserisci.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_inserisci.setEnabled(False)
        btn_row.addWidget(btn_annulla)
        btn_row.addWidget(btn_inserisci)
        root.addLayout(btn_row)

        min_fine_giornata = _str_to_min("18:00")
        paz_sel = [None]

        def _on_selezione():
            for i in range(lista_widget.count()):
                w = lista_widget.itemWidget(lista_widget.item(i))
                if w:
                    w.setProperty("selected", False)
                    w.style().unpolish(w)
                    w.style().polish(w)
                    w.update()

            items = lista_widget.selectedItems()
            if not items:
                lbl_timing.setText("Seleziona un paziente per vedere l'orario proposto")
                lbl_timing.setStyleSheet("")
                btn_inserisci.setEnabled(False)
                paz_sel[0] = None
                return

            sel_widget = lista_widget.itemWidget(items[0])
            if sel_widget:
                sel_widget.setProperty("selected", True)
                sel_widget.style().unpolish(sel_widget)
                sel_widget.style().polish(sel_widget)
                sel_widget.update()

            paz_id = items[0].data(Qt.ItemDataRole.UserRole)
            paz = next((p for p in disponibili if p.get("id") == paz_id), None)
            if not paz:
                return
            paz_sel[0] = paz
            durata = paz.get("durata_intervento", 90)
            ora_fine_min = ora_inizio_min + durata
            ora_i = _min_to_str(ora_inizio_min)
            ora_f = _min_to_str(ora_fine_min)
            if ora_fine_min <= min_fine_giornata:
                lbl_timing.setText(f"✓  {ora_i} – {ora_f}  ({durata} min)")
                lbl_timing.setStyleSheet(
                    "color:#16a34a; font-weight:bold; font-size:14px;"
                )
                btn_inserisci.setEnabled(True)
            else:
                eccedenza = ora_fine_min - min_fine_giornata
                lbl_timing.setText(f"✗  Sfora di {eccedenza} min oltre le 18:00")
                lbl_timing.setStyleSheet(
                    "color:#dc2626; font-weight:bold; font-size:14px;"
                )
                btn_inserisci.setEnabled(False)

        lista_widget.itemSelectionChanged.connect(_on_selezione)

        def _on_inserisci():
            paz = paz_sel[0]
            if paz:
                self._inserisci_paziente_manuale(dialog, paz, data_str, ora_inizio_min)

        btn_inserisci.clicked.connect(_on_inserisci)
        dialog.exec()

    def _inserisci_paziente_manuale(self, dialog, paz: dict, data_str: str, ora_inizio_min: int):
        import random as _rnd
        durata = paz.get("durata_intervento", 90)
        ora_fine_min = ora_inizio_min + durata
        if ora_fine_min > _str_to_min("18:00"):
            self._avviso("Errore", "L'operazione sfora le 18:00.", tipo="warning", parent=dialog)
            return
        interventi_paz = paz.get("interventi") or [{
            "codice":       paz.get("codice_intervento", ""),
            "descrizione":  paz.get("descrizione_intervento", ""),
            "durata":       durata,
        }]
        chirurgo = _rnd.choice(CHIRURGHI_MOCK)
        op = {
            "nome_paziente":    f"{paz.get('cognome','')} {paz.get('nome','')}",
            "id_paziente":      paz.get("id", ""),
            "diagnosi":         paz.get("diagnosi", ""),
            "intervento":       interventi_paz[0].get("descrizione", "") if interventi_paz else "",
            "codice_intervento":interventi_paz[0].get("codice", "") if interventi_paz else "",
            "interventi":       interventi_paz,
            "chirurgo":         chirurgo,
            "complessita":      paz.get("complessita", ""),
            "tipo_chirurgia":   paz.get("tipo_chirurgia", ""),
            "durata":           durata,
            "ora_inizio":       _min_to_str(ora_inizio_min),
            "ora_fine":         _min_to_str(ora_fine_min),
        }
        operazioni = self.model.get_operazioni(data_str)
        operazioni.append(op)
        self.model.set_operazioni(data_str, operazioni)
        self.aggiorna_tabella()
        dialog.accept()

    def salva_modifica_cella(self, riga, colonna):
        pass

    def _on_cella_cliccata(self, riga, colonna):
        """Apre il popup con i dettagli del paziente se la cella contiene un'assegnazione."""
        if riga < 2:
            return
        op_idx = riga - 2
        data_col = self.settimana_display + datetime.timedelta(days=colonna)
        data_str = data_col.strftime("%Y-%m-%d")
        operazioni = self.model.get_operazioni(data_str)
        if op_idx >= len(operazioni):
            return
        op = operazioni[op_idx]
        if not op.get("nome_paziente"):
            return
        paz_full = None
        if self.model_paz and op.get("id_paziente"):
            paz_full = self.model_paz.get_paziente_by_id(op["id_paziente"])
        self._mostra_popup_paziente(op, paz_full, data_str=data_str, op_idx=op_idx)

    def _on_slot_vuoto_cliccato(self, riga, colonna):
        """Apre il dialog di inserimento manuale per il primo slot libero del giorno."""
        data_col = self.settimana_display + datetime.timedelta(days=colonna)
        data_str = data_col.strftime("%Y-%m-%d")
        operazioni = self.model.get_operazioni(data_str)
        ora_inizio_min = (
            _str_to_min(operazioni[-1]["ora_fine"]) if operazioni else _str_to_min("08:00")
        )
        self._mostra_dialog_inserimento_manuale(data_str, data_col, ora_inizio_min)

    def _mostra_popup_paziente(self, slot: dict, paz_full: dict | None,
                               data_str: str = None, op_idx: int = None):
        dialog = QDialog(self.view)
        dialog.setWindowTitle("Dettagli Paziente")
        dialog.setModal(True)
        dialog.setMinimumWidth(500)
        dialog.setSizeGripEnabled(False)
        dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        dialog.setStyleSheet(self._load_style() + "\nQDialog { background-color: #f8fafc; }")

        root = QVBoxLayout(dialog)
        root.setContentsMargins(30, 30, 30, 30)
        root.setSpacing(16)

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

        ora_i = slot.get("ora_inizio", "")
        ora_f = slot.get("ora_fine", "")
        durata = slot.get("durata", "")
        if ora_i and ora_f:
            _riga("Orario", f"{ora_i} – {ora_f}  ({durata} min)" if durata else f"{ora_i} – {ora_f}")

        _riga("Diagnosi", slot.get("diagnosi", ""))
        interventi_list = slot.get("interventi", [])
        if interventi_list:
            for idx_i, inv in enumerate(interventi_list, 1):
                cod_i = inv.get("codice", "")
                desc_i = inv.get("descrizione", "")
                dur_i = inv.get("durata", "")
                label_i = f"Intervento {idx_i}" if len(interventi_list) > 1 else "Intervento"
                val_i = f"[{cod_i}]  {desc_i}" if cod_i else desc_i
                if dur_i:
                    val_i += f"  ({dur_i} min)"
                _riga(label_i, val_i)
        else:
            cod = slot.get("codice_intervento", "")
            inter = slot.get("intervento", "")
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

        sep_btn = QFrame()
        sep_btn.setObjectName("SeparatoreDialog")
        sep_btn.setFixedHeight(1)
        root.addWidget(sep_btn)

        btn_row = QHBoxLayout()
        btn_row.setSpacing(12)

        if (self.modalita_corrente in ("PIANIFICAZIONE", "CONSULTAZIONE")
                and self._stato_corrente != "CONVALIDATO"
                and data_str is not None and op_idx is not None):
            btn_rimuovi = QPushButton("Rimuovi dal piano")
            btn_rimuovi.setObjectName("BtnElimina")
            btn_rimuovi.setFixedHeight(44)
            btn_rimuovi.setCursor(Qt.CursorShape.PointingHandCursor)
            btn_rimuovi.clicked.connect(
                lambda: self._rimuovi_paziente_da_slot(dialog, data_str, op_idx)
            )
            btn_row.addWidget(btn_rimuovi)

        btn_chiudi = QPushButton("Chiudi")
        btn_chiudi.setObjectName("BtnAnnullaDialog")
        btn_chiudi.setFixedHeight(44)
        btn_chiudi.setCursor(Qt.CursorShape.PointingHandCursor)
        btn_chiudi.clicked.connect(dialog.accept)
        btn_row.addWidget(btn_chiudi)

        root.addLayout(btn_row)

        dialog.exec()
