import os
from src.data_paths import PROJECT_ROOT
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QFrame,
    QLineEdit, QPushButton, QGraphicsDropShadowEffect,
    QStackedWidget, QListWidget, QTextEdit
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QColor

from src.views.components.person_list import crea_elemento_elenco
from src.views.components.section_header import TONI_MODALITA, BandaSezione

_COLORI_URGENZA = {
    "Alta":  ("#fee2e2", "#dc2626"),
    "Media": ("#fef9c3", "#d97706"),
    "Bassa": ("#dcfce7", "#15803d"),
}

_COLORI_STATO = {
    "In Attesa":   ("#e0f2fe", "#0369a1"),
    "Pianificato": ("#f5f3ff", "#7c3aed"),
    "Completato":  ("#f1f5f9", "#475569"),
}


class ViewPazienti(QWidget):
    def __init__(self):
        super().__init__()
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setup_ui()
        self.load_styles()

    def setup_ui(self):
        main = QVBoxLayout(self)
        main.setContentsMargins(0, 0, 0, 0)
        self.stacked_widget = QStackedWidget()
        main.addWidget(self.stacked_widget)
        self._build_page_lista()
        self._build_page_dettaglio()

    def _build_page_lista(self):
        self.page_lista = QWidget()
        outer = QVBoxLayout(self.page_lista)
        outer.setContentsMargins(40, 40, 40, 40)

        self.card_container = QFrame()
        self.card_container.setObjectName("MainCard")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(32)
        shadow.setColor(QColor(0, 0, 0, 22))
        shadow.setOffset(0, 6)
        self.card_container.setGraphicsEffect(shadow)

        card = QVBoxLayout(self.card_container)
        card.setContentsMargins(40, 35, 40, 40)
        card.setSpacing(18)

        header_row = QHBoxLayout()
        titles = QVBoxLayout()
        titles.setSpacing(3)
        lbl_titolo = QLabel("Pazienti in Lista d'Attesa")
        lbl_titolo.setObjectName("TitoloSezione")
        lbl_sottotitolo = QLabel("Gestione e consultazione dei pazienti in attesa di intervento")
        lbl_sottotitolo.setObjectName("SottoTitoloSezione")
        titles.addWidget(lbl_titolo)
        titles.addWidget(lbl_sottotitolo)
        header_row.addLayout(titles)
        header_row.addStretch()

        summary_col = QVBoxLayout()
        summary_col.setSpacing(4)
        summary_col.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.lbl_count_attesa = QLabel("")
        self.lbl_count_attesa.setObjectName("CountAttesa")
        self.lbl_count_attesa.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.lbl_count_total = QLabel("")
        self.lbl_count_total.setObjectName("CountTotal")
        self.lbl_count_total.setAlignment(Qt.AlignmentFlag.AlignRight)
        summary_col.addWidget(self.lbl_count_attesa)
        summary_col.addWidget(self.lbl_count_total)
        header_row.addLayout(summary_col)

        card.addLayout(header_row)

        self.search_container = QFrame()
        self.search_container.setObjectName("SearchContainer")
        self.search_container.setFixedHeight(50)
        sc = QHBoxLayout(self.search_container)
        sc.setContentsMargins(16, 0, 16, 0)
        sc.setSpacing(12)
        lbl_icon = QLabel("🔍")
        lbl_icon.setObjectName("SearchIcon")
        self.search_bar = QLineEdit()
        self.search_bar.setObjectName("SearchBar")
        self.search_bar.setPlaceholderText("Cerca per nome, cognome o codice intervento...")
        sc.addWidget(lbl_icon)
        sc.addWidget(self.search_bar)
        card.addWidget(self.search_container)

        chips_row = QHBoxLayout()
        chips_row.setSpacing(10)
        lbl_filtri = QLabel("URGENZA")
        lbl_filtri.setObjectName("LblFiltri")
        chips_row.addWidget(lbl_filtri)

        self.chk_urg_alta = QPushButton("● Alta")
        self.chk_urg_alta.setObjectName("ChipUrgAlta")
        self.chk_urg_alta.setCheckable(True)
        self.chk_urg_alta.setChecked(True)

        self.chk_urg_media = QPushButton("● Media")
        self.chk_urg_media.setObjectName("ChipUrgMedia")
        self.chk_urg_media.setCheckable(True)
        self.chk_urg_media.setChecked(True)

        self.chk_urg_bassa = QPushButton("● Bassa")
        self.chk_urg_bassa.setObjectName("ChipUrgBassa")
        self.chk_urg_bassa.setCheckable(True)
        self.chk_urg_bassa.setChecked(True)

        for chip in [self.chk_urg_alta, self.chk_urg_media, self.chk_urg_bassa]:
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(34)
            chips_row.addWidget(chip)

        sep_chips = QFrame()
        sep_chips.setFrameShape(QFrame.Shape.VLine)
        sep_chips.setFixedWidth(1)
        sep_chips.setStyleSheet("background-color: #e2e8f0; border: none;")
        chips_row.addSpacing(6)
        chips_row.addWidget(sep_chips)
        chips_row.addSpacing(6)

        lbl_stato = QLabel("STATO")
        lbl_stato.setObjectName("LblFiltri")
        chips_row.addWidget(lbl_stato)

        self.chk_in_attesa = QPushButton("● In Attesa")
        self.chk_in_attesa.setObjectName("ChipInAttesa")
        self.chk_in_attesa.setCheckable(True)
        self.chk_in_attesa.setChecked(True)

        self.chk_pianificato = QPushButton("● Pianificato")
        self.chk_pianificato.setObjectName("ChipPianificato")
        self.chk_pianificato.setCheckable(True)
        self.chk_pianificato.setChecked(True)

        self.chk_completato = QPushButton("● Completato")
        self.chk_completato.setObjectName("ChipCompletato")
        self.chk_completato.setCheckable(True)
        self.chk_completato.setChecked(False)

        for chip in [self.chk_in_attesa, self.chk_pianificato, self.chk_completato]:
            chip.setCursor(Qt.CursorShape.PointingHandCursor)
            chip.setFixedHeight(34)
            chips_row.addWidget(chip)

        chips_row.addStretch()
        card.addLayout(chips_row)

        body = QHBoxLayout()
        body.setSpacing(24)

        self.lista_risultati = QListWidget()
        self.lista_risultati.setObjectName("ListaRisultati")
        self.lista_risultati.setCursor(Qt.CursorShape.PointingHandCursor)
        self.lista_risultati.setSpacing(5)

        _orig = self.lista_risultati.mousePressEvent
        def _on_click(ev):
            if not self.lista_risultati.itemAt(ev.pos()):
                self.lista_risultati.clearSelection()
            _orig(ev)
        self.lista_risultati.mousePressEvent = _on_click

        body.addWidget(self.lista_risultati, stretch=7)

        btn_col = QVBoxLayout()
        btn_col.setSpacing(14)

        self.btn_apri = QPushButton("Dettaglio Paziente")
        self.btn_apri.setObjectName("BtnApri")
        self.btn_apri.setFixedHeight(56)
        self.btn_apri.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_apri.setEnabled(False)

        self.btn_aggiungi = QPushButton("+ Nuovo Paziente")
        self.btn_aggiungi.setObjectName("BtnAggiungi")
        self.btn_aggiungi.setFixedHeight(56)
        self.btn_aggiungi.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_bulk = QPushButton("+ Inserimento Multiplo")
        self.btn_bulk.setObjectName("BtnBulk")
        self.btn_bulk.setFixedHeight(56)
        self.btn_bulk.setCursor(Qt.CursorShape.PointingHandCursor)

        btn_col.addWidget(self.btn_apri)
        btn_col.addWidget(self.btn_aggiungi)
        btn_col.addWidget(self.btn_bulk)
        btn_col.addStretch()
        body.addLayout(btn_col, stretch=3)
        card.addLayout(body)

        outer.addWidget(self.card_container)
        self.stacked_widget.addWidget(self.page_lista)

    def _build_page_dettaglio(self):
        self.page_dettaglio = QWidget()
        pagina = QVBoxLayout(self.page_dettaglio)
        pagina.setContentsMargins(0, 0, 0, 0)
        pagina.setSpacing(0)
        # Banda come nello Scadenzario e nel Libretto: chi si sta guardando.
        self.banda_dettaglio = BandaSezione(
            "Lista Pazienti", aiuto_indietro="Torna alla lista dei pazienti"
        )
        self.btn_indietro = self.banda_dettaglio.btn_indietro
        pagina.addWidget(self.banda_dettaglio)
        corpo = QWidget()
        pagina.addWidget(corpo, 1)
        layout = QVBoxLayout(corpo)
        layout.setContentsMargins(40, 24, 40, 28)
        layout.setSpacing(18)

        self.btn_modifica = QPushButton("✏  Modifica")
        self.btn_modifica.setObjectName("BtnModifica")
        self.btn_modifica.setFixedHeight(42)
        self.btn_modifica.setCursor(Qt.CursorShape.PointingHandCursor)

        self.btn_elimina = QPushButton("🗑  Elimina")
        self.btn_elimina.setObjectName("BtnElimina")
        self.btn_elimina.setFixedHeight(42)
        self.btn_elimina.setCursor(Qt.CursorShape.PointingHandCursor)

        card_det = QFrame()
        card_det.setObjectName("CardDettaglio")
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(25)
        shadow.setColor(QColor(0, 0, 0, 18))
        shadow.setOffset(0, 4)
        card_det.setGraphicsEffect(shadow)

        cd = QVBoxLayout(card_det)
        cd.setContentsMargins(40, 30, 40, 40)
        cd.setSpacing(24)

        azioni = QHBoxLayout()
        azioni.setSpacing(12)
        lbl_scheda = QLabel("Scheda del paziente")
        lbl_scheda.setObjectName("TitoloScheda")
        azioni.addWidget(lbl_scheda)
        azioni.addStretch()
        azioni.addWidget(self.btn_modifica)
        azioni.addWidget(self.btn_elimina)
        cd.addLayout(azioni)

        info_row = QHBoxLayout()
        info_row.setSpacing(16)
        box_urg, self.val_urgenza   = self._crea_info_box("Classe di Urgenza", "-", accent=True)
        box_cpx, self.val_complessita = self._crea_info_box("Complessità", "-")
        box_dat, self.val_data      = self._crea_info_box("Data Inserimento", "-")
        box_op, self.val_data_intervento = self._crea_info_box("Data Intervento", "-")
        box_sta, self.val_stato     = self._crea_info_box("Stato", "-")
        for box in [box_urg, box_cpx, box_dat, box_op, box_sta]:
            info_row.addWidget(box)
        cd.addLayout(info_row)

        sep1 = QFrame()
        sep1.setObjectName("Separatore")
        sep1.setFixedHeight(1)
        cd.addWidget(sep1)

        lbl_clinica = QLabel("Dettagli Clinici")
        lbl_clinica.setObjectName("TitoloTabella")
        cd.addWidget(lbl_clinica)

        def _riga_clinica(etichetta):
            row = QHBoxLayout()
            row.setSpacing(16)
            lbl_k = QLabel(etichetta.upper())
            lbl_k.setObjectName("LblInfo")
            lbl_k.setFixedWidth(180)
            lbl_v = QLabel("—")
            lbl_v.setObjectName("ValInfo")
            lbl_v.setWordWrap(True)
            row.addWidget(lbl_k)
            row.addWidget(lbl_v, 1)
            cd.addLayout(row)
            return lbl_v

        self.val_codice_diagnosi = _riga_clinica("Codice ICD-9-CM")
        self.val_diagnosi   = _riga_clinica("Descrizione Diagnosi")
        self.val_intervento = _riga_clinica("Intervento")
        self.val_tipo       = _riga_clinica("Tipo Chirurgia")

        sep2 = QFrame()
        sep2.setObjectName("Separatore")
        sep2.setFixedHeight(1)
        cd.addWidget(sep2)

        lbl_note = QLabel("Note Cliniche / Preparazione")
        lbl_note.setObjectName("TitoloTabella")
        cd.addWidget(lbl_note)

        self.txt_note = QTextEdit()
        self.txt_note.setObjectName("TxtNote")
        self.txt_note.setReadOnly(True)
        cd.addWidget(self.txt_note)

        layout.addWidget(card_det)
        self.stacked_widget.addWidget(self.page_dettaglio)

    def _crea_info_box(self, etichetta, valore_iniziale, accent=False):
        box = QFrame()
        box.setObjectName("InfoBox")
        bl = QVBoxLayout(box)
        bl.setContentsMargins(16, 12, 16, 12)
        bl.setSpacing(6)
        lbl = QLabel(etichetta.upper())
        lbl.setObjectName("LblInfo")
        val = QLabel(valore_iniziale)
        val.setObjectName("ValInfoUrgenza" if accent else "ValInfo")
        val.setWordWrap(True)
        bl.addWidget(lbl)
        bl.addWidget(val)
        return box, val

    def crea_item_lista(self, cognome, nome, codice, urgenza, stato):
        """Elemento della lista d'attesa, nello stesso stile dell'anagrafica del Libretto."""
        _inizio, _fine, accento, tinta = TONI_MODALITA["PAZIENTI"]
        etichette = []
        for testo, colori in ((urgenza, _COLORI_URGENZA), (stato, _COLORI_STATO)):
            sfondo, colore = colori.get(testo, ("#f1f5f9", "#475569"))
            etichette.append((testo, sfondo, colore))
        return crea_elemento_elenco(
            cognome=cognome, nome=nome, sottotitolo=f"Codice {codice}",
            etichette=etichette, accento=accento, tinta=tinta,
        )

    def imposta_dettaglio(
        self,
        paz,
        *,
        stato_effettivo: str | None = None,
        data_intervento: str | None = None,
    ):
        stato_banda = stato_effettivo or paz.get("stato", "In Attesa")
        self.banda_dettaglio.imposta_intestazione(
            f"{paz.get('cognome', '').upper()} {paz.get('nome', '')}".strip(),
            " · ".join(filter(None, (
                f"Urgenza {paz['urgenza']}" if paz.get("urgenza") else "",
                stato_banda,
                f"Intervento {data_intervento}" if data_intervento else "",
            ))),
            "PAZIENTI",
        )
        self.val_data.setText(paz.get("data_inserimento", "N/D"))
        self.val_data_intervento.setText(data_intervento or "Non pianificata")

        cpx = paz.get("complessita", "")
        _COLORI_CPX = {
            "Alta":  ("#fee2e2", "#dc2626"),
            "Media": ("#fef9c3", "#d97706"),
            "Bassa": ("#dcfce7", "#15803d"),
        }
        self.val_complessita.setText(cpx if cpx else "—")
        bg_c, fg_c = _COLORI_CPX.get(cpx, ("#f1f5f9", "#475569"))
        self.val_complessita.setStyleSheet(
            f"background-color:{bg_c}; color:{fg_c}; font-size:18px; "
            f"font-weight:bold; padding:10px 16px; border-radius:10px; "
            f"border:1.5px solid {fg_c}60;"
        )

        urgenza = paz.get("urgenza", "")
        self.val_urgenza.setText(urgenza if urgenza else "–")
        bg, fg = _COLORI_URGENZA.get(urgenza, ("#f1f5f9", "#475569"))
        self.val_urgenza.setStyleSheet(
            f"background-color:{bg}; color:{fg}; font-size:18px; "
            f"font-weight:bold; padding:10px 16px; border-radius:10px; "
            f"border:1.5px solid {fg}60;"
        )

        stato = stato_effettivo or paz.get("stato", "In Attesa")
        self.val_stato.setText(stato if stato else "–")
        bg2, fg2 = _COLORI_STATO.get(stato, ("#f1f5f9", "#475569"))
        self.val_stato.setStyleSheet(
            f"background-color:{bg2}; color:{fg2}; font-size:18px; "
            f"font-weight:bold; padding:10px 16px; border-radius:10px; "
            f"border:1.5px solid {fg2}60;"
        )

        self.val_codice_diagnosi.setText(paz.get("codice_diagnosi", "") or "—")
        self.val_diagnosi.setText(
            paz.get("descrizione_diagnosi", "") or paz.get("diagnosi", "") or "—"
        )

        interventi_list = paz.get("interventi", [])
        if interventi_list:
            parti = []
            for inv in interventi_list:
                cod_i = inv.get("codice", "")
                desc_i = inv.get("descrizione", "")
                dur_i = inv.get("durata", "")
                riga = f"[{cod_i}]  {desc_i}" if cod_i else desc_i
                if dur_i:
                    riga += f"  ({dur_i} min)"
                if riga.strip():
                    parti.append(riga)
            self.val_intervento.setText("\n".join(parti) if parti else "—")
        else:
            cod = paz.get("codice_intervento", "")
            inter = paz.get("descrizione_intervento", "")
            if cod and inter:
                self.val_intervento.setText(f"[{cod}]  {inter}")
            elif inter:
                self.val_intervento.setText(inter)
            elif cod:
                self.val_intervento.setText(cod)
            else:
                self.val_intervento.setText("—")

        self.val_tipo.setText(paz.get("tipo_chirurgia", "") or "—")

        note = paz.get("note", "")
        self.txt_note.setText(note if note else "Nessuna nota clinica inserita.")

    def aggiorna_conteggi(self, n_attesa: int, n_pianificati: int, n_totale: int):
        self.lbl_count_attesa.setText(
            f"{n_attesa} in attesa  ·  {n_pianificati} pianificat{'o' if n_pianificati == 1 else 'i'}"
        )
        self.lbl_count_total.setText(f"{n_totale} pazienti totali")

    def load_styles(self):
        style_path = os.path.join(PROJECT_ROOT, "asset", "styles", "pazienti.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        if self.stacked_widget.currentIndex() == 0:
            self.lista_risultati.clearSelection()
