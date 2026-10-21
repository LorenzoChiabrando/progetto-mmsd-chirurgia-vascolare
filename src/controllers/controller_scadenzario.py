from __future__ import annotations

import calendar
import datetime
from contextlib import contextmanager
from pathlib import Path

from PySide6.QtWidgets import QDialog, QFileDialog
from PySide6.QtCore import Qt

from src.calendar_presentation import (
    GUARD_TEXT_COLORS,
    ROLE_CELL_COLORS,
    month_dates,
    month_weeks,
    resolve_resident_name,
    row_display_label,
)
from src.calendar_versions import CalendarVersion
from src.error_messages import describe_error
from src.exports.calendar_pdf import CalendarPdfDocument, CalendarPdfRow, write_calendar_pdf
from src.models.json_files import CorruptedDataError
from src.roster_assignment import (
    GUARD_TYPE_ROLE,
    WARD_ROUND_ROLE,
    assignment_context,
    busy_residents_for_day,
    busy_residents_for_week,
    resident_options,
)
from src.roster_month import GUARD_ROLE, ROLE_KEYS, RosterMonth, load_roster_month, resident_rows
from src.views.components import messages
from src.views.dialog_assegnazione_turno import DialogAssegnazioneSpecializzando, DialogTipoGuardia
from src.views.dialog_mese_anno import DialogMeseAnno


_SEZIONE = "scadenzario"
_RUOLI_SALA = ("Sala Op. I", "Sala Op. II")
"""Ruoli obbligatori in ogni giorno feriale: senza di essi il mese non si convalida."""

_RUOLI_SALE_OPERATORIE = {"Sala Op. I": ("OR-1", "OR I"), "Sala Op. II": ("OR-2", "OR II")}
"""Riga dello scadenzario -> (sala, ruolo) usati nei file delle Sale Operatorie."""

_PDF_GUARD_NOTE = "118 = Emergenza territoriale · PI = Pronto Intervento · L = Liscia (routinaria)"


def build_scadenzario_pdf_document(
    roster: RosterMonth,
    dates: tuple[datetime.date, ...],
    residents: list[dict],
    *,
    version: CalendarVersion = CalendarVersion.PREVISTO,
) -> CalendarPdfDocument:
    """Prepara il PDF dello scadenzario a partire dal mese caricato.

    Nel mese gli specializzandi compaiono come ``Cognome N.`` (il PDF li abbrevia al
    cognome se serve), nella settimana con il nome completo. Il titolo indica la
    versione (Previsto o Effettivo) da cui proviene ``roster``.
    """

    if not dates:
        raise ValueError("Serve almeno una data da esportare.")
    monthly = len(dates) > 7
    weekday_labels = ("Lun", "Mar", "Mer", "Gio", "Ven", "Sab", "Dom")
    columns = tuple(f"{day.day} {weekday_labels[day.weekday()]}" for day in dates)
    rows: list[CalendarPdfRow] = []
    for role in ROLE_KEYS:
        values: list[str] = []
        for day in dates:
            value = roster.value(day, role) if RosterMonth.is_workday(day) else "-"
            if role != GUARD_ROLE and value and value != "-" and not monthly:
                value = resolve_resident_name(value, residents)
            values.append(value or "-")
        rows.append(
            CalendarPdfRow(
                label=row_display_label(role),
                values=tuple(values),
                background=ROLE_CELL_COLORS[role],
                value_colors=GUARD_TEXT_COLORS if role == GUARD_ROLE else {},
            )
        )

    period = f"{dates[0]:%d/%m/%Y} - {dates[-1]:%d/%m/%Y}"
    title = "Scadenzario mensile" if monthly else "Scadenzario settimanale"
    return CalendarPdfDocument(
        title=f"{title} · {CalendarVersion(version).value.capitalize()}",
        period=period,
        column_headers=columns,
        rows=tuple(rows),
        footnote=_PDF_GUARD_NOTE,
        rest_columns=frozenset(index for index, day in enumerate(dates) if day.weekday() >= 5),
        stacked_names=monthly,
    )


def _missing_operating_room_assignments(data: dict, year: int, month: int) -> list[str]:
    """Return weekday dates missing either operating-room specialist assignment."""

    _, days_in_month = calendar.monthrange(year, month)
    missing: list[str] = []
    for day_number in range(1, days_in_month + 1):
        day = datetime.date(year, month, day_number)
        if day.weekday() >= 5:
            continue
        daily = data.get("turni", {}).get(day.isoformat(), {})
        missing_fields = [
            field
            for field in _RUOLI_SALA
            if not isinstance(daily.get(field), str) or not daily[field].strip()
        ]
        if missing_fields:
            missing.append(f"{day.isoformat()}: {', '.join(missing_fields)}")
    return missing


def _duplicate_operating_room_assignments(data: dict, year: int, month: int) -> list[str]:
    """Return weekdays where one specialist is assigned to both physical rooms."""

    _, days_in_month = calendar.monthrange(year, month)
    duplicates: list[str] = []
    for day_number in range(1, days_in_month + 1):
        day = datetime.date(year, month, day_number)
        if day.weekday() >= 5:
            continue
        daily = data.get("turni", {}).get(day.isoformat(), {})
        first = daily.get("Sala Op. I")
        second = daily.get("Sala Op. II")
        if (
            isinstance(first, str)
            and isinstance(second, str)
            and first.strip()
            and first.strip().casefold() == second.strip().casefold()
        ):
            duplicates.append(day.isoformat())
    return duplicates


class ControllerScadenzario:
    def __init__(self, view, model, model_sale_operatorie=None):
        self.view = view
        self.versione_corrente = CalendarVersion.PREVISTO
        self._model_previsto = model.for_version(CalendarVersion.PREVISTO)
        self._model_effettivo = model.for_version(CalendarVersion.EFFETTIVO)
        self.model = self._model_previsto
        self._model_sale_base = model_sale_operatorie
        self.model_sale_op = (
            model_sale_operatorie.for_version(self.versione_corrente)
            if model_sale_operatorie is not None else None
        )
        self.modalita_corrente = None

        self.mesi_ita = ["Gennaio", "Febbraio", "Marzo", "Aprile", "Maggio", "Giugno",
                         "Luglio", "Agosto", "Settembre", "Ottobre", "Novembre", "Dicembre"]
        self.giorni_ita = ["lun", "mar", "mer", "gio", "ven", "sab", "dom"]

        self.oggi = datetime.date.today()
        self.real_anno = self.oggi.year
        self.real_mese = self.oggi.month

        self.anno_corrente = self.real_anno
        self.mese_corrente = self.real_mese

        self.view.btn_storico.clicked.connect(lambda: self.apri_calendario("STORICO"))
        self.view.btn_corrente.clicked.connect(lambda: self.apri_calendario("CORRENTE"))
        self.view.btn_pianificazione.clicked.connect(lambda: self.apri_calendario("PIANIFICAZIONE"))
        self.view.btn_indietro.clicked.connect(self.torna_alla_dashboard)

        self.view.btn_convalida.clicked.connect(self.convalida_mese)
        self.view.btn_crea_effettivo.clicked.connect(self.crea_effettivo_mese)
        self.view.combo_versione.currentIndexChanged.connect(self.cambia_versione)

        self.view.btn_prev.clicked.connect(self.mese_precedente)
        self.view.btn_next.clicked.connect(self.mese_successivo)
        self.view.btn_mese_anno.clicked.connect(self.scegli_mese_anno)
        self.view.btn_esporta_pdf.clicked.connect(self.esporta_pdf)
        self.view.btn_vista_dettaglio.clicked.connect(
            lambda: self.imposta_vista_compatta(False)
        )
        self.view.btn_vista_mese.clicked.connect(
            lambda: self.imposta_vista_compatta(True)
        )

        self.view.btn_per_attivita.clicked.connect(
            lambda: self.view.mostra_vista_specializzandi(False)
        )
        self.view.btn_per_specializzando.clicked.connect(
            lambda: self.view.mostra_vista_specializzandi(True)
        )
        self.view.tabella.clicked.connect(
            lambda index: self._gestisci_click_cella(index.row(), index.column())
        )

        self.roster = None
        self.aggiorna_tabella()

    @property
    def _nome_versione(self) -> str:
        """``Previsto`` o ``Effettivo``, per titoli e messaggi."""

        return self.versione_corrente.value.capitalize()

    def cambia_versione(self, _index: int) -> None:
        """Passa a Previsto o Effettivo senza cambiare periodo, vista o dati salvati.

        Se il mese della nuova versione è danneggiato si resta sulla versione di partenza;
        l'errore viene rilanciato e lo mostra il gestore globale.
        """

        version = CalendarVersion(self.view.combo_versione.currentData())
        if version == self.versione_corrente:
            return
        partenza = (self.versione_corrente, self.model, self.model_sale_op)
        self.versione_corrente = version
        self.model = (
            self._model_previsto if version == CalendarVersion.PREVISTO
            else self._model_effettivo
        )
        if self._model_sale_base is not None:
            self.model_sale_op = self._model_sale_base.for_version(version)
        try:
            self.aggiorna_tabella()
        except CorruptedDataError:
            self.versione_corrente, self.model, self.model_sale_op = partenza
            self.view.combo_versione.blockSignals(True)
            self.view.combo_versione.setCurrentIndex(
                self.view.combo_versione.findData(self.versione_corrente.value)
            )
            self.view.combo_versione.blockSignals(False)
            raise
        self.view.lbl_dettaglio_cella.setText("")

    def _effettivo_assente(self) -> bool:
        return (
            self.versione_corrente == CalendarVersion.EFFETTIVO
            and not self.model.has_mese(self.anno_corrente, self.mese_corrente)
        )

    def _puo_modificare(self) -> bool:
        """Mese esistente e non convalidato; nello Storico si corregge solo l'Effettivo."""

        if self._effettivo_assente():
            return False
        if self.model.get_stato_mese(self.anno_corrente, self.mese_corrente) == "CONVALIDATO":
            return False
        return not (
            self.modalita_corrente == "STORICO"
            and self.versione_corrente == CalendarVersion.PREVISTO
        )

    def _mesi_disponibili(self) -> list[tuple[int, int]]:
        return sorted(set(self._model_previsto.get_mesi_disponibili())
                      | set(self._model_effettivo.get_mesi_disponibili()))

    def _conflitto_assegnazioni_interventi(self, data_str: str, riga: str, valore: str) -> bool:
        """Vero se la sala ha interventi assegnati a uno specializzando diverso da ``valore``.

        Cambiare il turno dell'Effettivo non riassegna i singoli interventi: in quel caso
        la modifica va rifiutata invece di lasciare sala e interventi incoerenti.
        """

        room_id, role = _RUOLI_SALE_OPERATORIE[riga]
        for operation in self.model_sale_op.get_operazioni(data_str):
            operation_room = operation.get("sala_operatoria")
            if operation_room and operation_room != room_id:
                continue
            operation_role = operation.get("ruolo_specializzando")
            if not operation_room and operation_role and operation_role != role:
                continue
            assigned = any(key in operation for key in (
                "id_specializzando", "specializzando", "ruolo_specializzando",
            ))
            specialist = operation.get("specializzando", "").strip().casefold()
            if assigned and specialist != valore.casefold():
                return True
        return False

    def crea_effettivo_mese(self) -> None:
        """Crea l'Effettivo mancante copiandolo dal Previsto convalidato, dopo conferma."""

        if not self._effettivo_assente():
            return
        if not messages.ask_confirmation(
            self.view,
            "Crea calendario Effettivo",
            f"Creare l'Effettivo di {self.mese_corrente:02d}/{self.anno_corrente} "
            "dal Previsto convalidato?\n\nLa copia sarà modificabile separatamente.",
            section=_SEZIONE,
            confirm_text="Crea Effettivo",
        ):
            return
        try:
            self._model_previsto.crea_effettivo_mese(self.anno_corrente, self.mese_corrente)
        except (OSError, ValueError) as error:
            messages.show_message(
                self.view,
                "Creazione Effettivo non riuscita",
                describe_error(error),
                section=_SEZIONE,
                kind="warning",
            )
        self.aggiorna_tabella()

    def get_max_history_date(self):
        """
        Calcola dinamicamente fino a che mese si può spingere lo Storico.
        Se il mese corrente è già CONVALIDATO, rientra nello storico.
        Altrimenti, lo storico si ferma rigorosamente al mese precedente.
        """
        if self._model_previsto.get_stato_mese(self.real_anno, self.real_mese) == "CONVALIDATO":
            return datetime.date(self.real_anno, self.real_mese, 1)
        else:
            if self.real_mese == 1:
                return datetime.date(self.real_anno - 1, 12, 1)
            else:
                return datetime.date(self.real_anno, self.real_mese - 1, 1)

    def _mesi_storici(self) -> list[tuple[int, int]]:
        """Mesi dello Storico, in ordine: Previsto convalidato e non oltre il mese corrente.

        Come per le settimane delle Sale operatorie, un mese mai convalidato non è storia:
        resta una bozza e non compare, anche se è passato.
        """
        limite = self.get_max_history_date()
        return [
            (anno, mese)
            for anno, mese in self._mesi_disponibili()
            if datetime.date(anno, mese, 1) <= limite
            and self._model_previsto.has_mese(anno, mese)
            and self._model_previsto.get_stato_mese(anno, mese) == "CONVALIDATO"
        ]

    def _vai_al_mese_storico(self, direzione: int) -> None:
        """Passa al mese convalidato precedente (-1) o successivo (+1), saltando le bozze."""
        corrente = (self.anno_corrente, self.mese_corrente)
        candidati = [
            mese for mese in self._mesi_storici()
            if (mese < corrente if direzione < 0 else mese > corrente)
        ]
        if candidati:
            self.anno_corrente, self.mese_corrente = (
                candidati[-1] if direzione < 0 else candidati[0]
            )

    def convalida_mese(self):
        if not self._puo_modificare():
            return
        month_data = self.model.load_mese(self.anno_corrente, self.mese_corrente)
        missing = _missing_operating_room_assignments(
            month_data,
            self.anno_corrente,
            self.mese_corrente,
        )
        if missing:
            preview = "\n".join(f"• {item}" for item in missing[:8])
            remaining = len(missing) - 8
            if remaining > 0:
                preview += f"\n• ...e altri {remaining} giorni"
            messages.show_message(
                self.view,
                f"Scadenzario {self._nome_versione} incompleto",
                "Prima della convalida assegna Sala Op. I e Sala Op. II "
                "a tutti i giorni lavorativi.\n\n" + preview,
                section=_SEZIONE,
                kind="warning",
            )
            return

        duplicates = _duplicate_operating_room_assignments(
            month_data,
            self.anno_corrente,
            self.mese_corrente,
        )
        if duplicates:
            preview = "\n".join(f"• {item}" for item in duplicates[:8])
            remaining = len(duplicates) - 8
            if remaining > 0:
                preview += f"\n• ...e altri {remaining} giorni"
            messages.show_message(
                self.view,
                f"Assegnazione sale non valida · {self._nome_versione}",
                "Lo stesso specializzando non può coprire contemporaneamente "
                "Sala Op. I e Sala Op. II.\n\n" + preview,
                section=_SEZIONE,
                kind="warning",
            )
            return

        explanation = (
            "Il Previsto non sarà più modificabile. Verrà creata una copia Effettivo "
            "modificabile separatamente."
            if self.versione_corrente == CalendarVersion.PREVISTO else
            "L'Effettivo non sarà più modificabile. Le attività operatorie si "
            "confermano separatamente nelle Sale Operatorie."
        )
        if messages.ask_confirmation(
            self.view,
            f"Convalida {self._nome_versione}",
            f"Convalidare il mese {self.mese_corrente:02d}/{self.anno_corrente} "
            f"{self._nome_versione}?\n\n{explanation}",
            section=_SEZIONE,
            confirm_text="Convalida",
        ):
            try:
                self.model.convalida_mese(self.anno_corrente, self.mese_corrente)
            except (OSError, ValueError) as error:
                messages.show_message(
                    self.view,
                    f"Convalida {self._nome_versione} non riuscita",
                    describe_error(error),
                    section=_SEZIONE,
                    kind="warning",
                )
            self.aggiorna_tabella()

    @contextmanager
    def _resta_sul_mese_se_danneggiato(self):
        """Se il file del mese di arrivo è danneggiato, torna a mese e modalità di partenza.

        L'errore viene rilanciato e lo mostra il gestore globale. Lo schermo resta
        coerente perché ``aggiorna_tabella`` legge i dati prima di toccare la vista.
        """
        partenza = (self.anno_corrente, self.mese_corrente, self.modalita_corrente)
        try:
            yield
        except CorruptedDataError:
            self.anno_corrente, self.mese_corrente, self.modalita_corrente = partenza
            raise

    def apri_calendario(self, modalita):
        with self._resta_sul_mese_se_danneggiato():
            self._apri_calendario(modalita)

    def _apri_calendario(self, modalita):
        if modalita == "STORICO":
            storici_validi = self._mesi_storici()

            if not storici_validi:
                messages.show_message(
                    self.view,
                    f"Nessuno storico · {self._nome_versione}",
                    "Non ci sono ancora mesi convalidati nello storico.\n"
                    "Convalida il Previsto di un mese da Mese Corrente o Pianificazione.",
                    section=_SEZIONE,
                )
                return
            else:
                self.anno_corrente, self.mese_corrente = storici_validi[-1]

        elif modalita == "CORRENTE":
            self.anno_corrente = self.real_anno
            self.mese_corrente = self.real_mese

        elif modalita == "PIANIFICAZIONE":
            if self.real_mese == 12:
                self.anno_corrente = self.real_anno + 1
                self.mese_corrente = 1
            else:
                self.anno_corrente = self.real_anno
                self.mese_corrente = self.real_mese + 1

        self.modalita_corrente = modalita
        # Prima il mese, poi il cambio pagina: con un file danneggiato si resta sulla dashboard.
        self.aggiorna_tabella()
        self.view.stacked_widget.setCurrentIndex(1)

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
            if self.real_mese == 12:
                min_plan_date = datetime.date(self.real_anno + 1, 1, 1)
            else:
                min_plan_date = datetime.date(self.real_anno, self.real_mese + 1, 1)
            if view_date <= min_plan_date:
                self.view.btn_prev.setVisible(False)

        elif self.modalita_corrente == "STORICO":
            corrente = (self.anno_corrente, self.mese_corrente)
            storici_validi = self._mesi_storici()
            self.view.btn_prev.setVisible(any(mese < corrente for mese in storici_validi))
            self.view.btn_next.setVisible(any(mese > corrente for mese in storici_validi))

    def torna_alla_dashboard(self):
        self.modalita_corrente = None
        self.view.stacked_widget.setCurrentIndex(0)

    def imposta_vista_compatta(self, compact: bool) -> None:
        """Attiva o disattiva la vista mensile compatta."""

        self.view.set_compact_mode(compact)
        self.aggiorna_tabella()

    def _cella_modificabile(self, row: int, column: int) -> bool:
        if row < 1 or column < 0 or self.modalita_corrente is None:
            return False
        if not self._puo_modificare():
            return False
        day = datetime.date(self.anno_corrente, self.mese_corrente, column + 1)
        return day.weekday() < 5

    def _gestisci_click_cella(self, row: int, column: int) -> None:
        self._mostra_nome_completo(row, column)
        if self._cella_modificabile(row, column):
            self._apri_modal_assegnazione(row, column)

    def _specializzandi_occupati(self, day: datetime.date, role: str) -> dict[str, str]:
        """Specializzandi già impegnati nel giorno (o nella settimana del giro visite)."""

        monday = day - datetime.timedelta(days=day.weekday())
        if role == WARD_ROUND_ROLE:
            week = [monday + datetime.timedelta(days=offset) for offset in range(5)]
            return busy_residents_for_week({
                weekday: self.model.load_mese(weekday.year, weekday.month)
                .get("turni", {})
                .get(weekday.isoformat(), {})
                for weekday in week
            })
        daily = (
            self.model.load_mese(day.year, day.month).get("turni", {}).get(day.isoformat(), {})
        )
        ward_round = self.model.get_giro_visite_settimana(
            monday.isoformat(), day.year, day.month
        )
        return busy_residents_for_day(daily, role, ward_round)

    def _apri_modal_assegnazione(self, row: int, column: int) -> None:
        """Apre il dialog della cella e passa la scelta ad ``assegna``."""

        modello = self.view.modello_attivita
        day = modello.date_at(column)
        role = self.view.row_labels[row]
        current = modello.value_at(row, column)
        context = assignment_context(day, role)

        if role == GUARD_TYPE_ROLE:
            dialog = DialogTipoGuardia(context, current, self.view)
        else:
            options = resident_options(
                self.model.specializzandi,
                self._specializzandi_occupati(day, role),
                current,
            )
            dialog = DialogAssegnazioneSpecializzando(options, context, current, self.view)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        nuovo_valore = dialog.selected_value()
        if nuovo_valore != current:
            self.assegna(row, column, nuovo_valore)

    def _mostra_nome_completo(self, row: int, column: int) -> None:
        if not self.view._compact or row < 2 or column < 0:
            return
        value = self.view.modello_attivita.value_at(row, column)
        full_name = self.model.get_nome_completo_specializzando(value) if value else ""
        day = datetime.date(self.anno_corrente, self.mese_corrente, column + 1)
        self.view.mostra_dettaglio_assegnazione(
            day.strftime("%d/%m/%Y"),
            self.view.row_labels[row],
            full_name,
            versione=self.versione_corrente.value,
        )

    def esporta_pdf(self) -> None:
        """Esporta il mese o una settimana in PDF."""

        if self._effettivo_assente():
            return
        weeks = month_weeks(self.anno_corrente, self.mese_corrente)
        choices = ["Mese intero"] + [
            f"Settimana {index}: {week[0].strftime('%d/%m')} - {week[-1].strftime('%d/%m')}"
            for index, week in enumerate(weeks, 1)
        ]
        choice = messages.choose_option(
            self.view,
            f"Esporta scadenzario {self._nome_versione}",
            "Intervallo da esportare:",
            choices,
            section=_SEZIONE,
        )
        if choice is None:
            return
        if choice == choices[0]:
            dates = month_dates(self.anno_corrente, self.mese_corrente)
            scope = "mese"
        else:
            week_index = choices.index(choice) - 1
            dates = weeks[week_index]
            scope = f"settimana-{week_index + 1}"

        suggested = (
            f"scadenzario-{self.versione_corrente.value}-"
            f"{self.anno_corrente:04d}-{self.mese_corrente:02d}-{scope}.pdf"
        )
        path, _ = QFileDialog.getSaveFileName(
            self.view,
            f"Salva calendario {self._nome_versione} PDF",
            str(Path.home() / suggested),
            "Documento PDF (*.pdf)",
        )
        if not path:
            return
        try:
            document = build_scadenzario_pdf_document(
                self.roster, dates, self.model.specializzandi, version=self.versione_corrente
            )
            output_path = write_calendar_pdf(path, document)
        except (OSError, ValueError, RuntimeError) as error:
            messages.show_message(
                self.view,
                f"Esportazione {self._nome_versione} non riuscita",
                f"Impossibile creare il PDF:\n{describe_error(error)}",
                section=_SEZIONE,
                kind="error",
            )
            return
        messages.show_message(
            self.view,
            f"PDF {self._nome_versione} creato",
            f"Calendario esportato in:\n{output_path}",
            section=_SEZIONE,
        )

    def _messaggio_versione(self, absent: bool, can_create: bool, stato_json: str) -> str:
        if absent:
            return (
                "Effettivo non ancora creato. Puoi copiarlo dal Previsto convalidato."
                if can_create else
                "Effettivo non ancora creato. "
                "Convalida il Previsto per creare la copia modificabile."
            )
        if stato_json == "CONVALIDATO":
            return f"{self._nome_versione} convalidato: sola lettura."
        if self.versione_corrente == CalendarVersion.EFFETTIVO:
            return "Le correzioni all'Effettivo non modificano il Previsto."
        return "La convalida del Previsto crea una copia Effettivo modificabile."

    def aggiorna_tabella(self):
        # Prima i dati, poi la vista: se il file del mese è danneggiato lo schermo non cambia.
        absent = self._effettivo_assente()
        if absent:
            # Nessun valore, nemmeno il giro visite salvato nell'Effettivo del mese vicino.
            stato_json = "ASSENTE"
            roster = RosterMonth(self.anno_corrente, self.mese_corrente, "BOZZA")
            can_create = (
                self._model_previsto.get_stato_mese(self.anno_corrente, self.mese_corrente)
                == "CONVALIDATO"
            )
        else:
            stato_json = self.model.get_stato_mese(self.anno_corrente, self.mese_corrente)
            roster = load_roster_month(self.model, self.anno_corrente, self.mese_corrente)
            can_create = False
        can_edit = self._puo_modificare()

        self.gestisci_navigazione()
        self.view.btn_convalida.setVisible(can_edit)
        self.view.btn_convalida.setText(
            f"CONVALIDA IL MESE {self.versione_corrente.value.upper()}"
        )
        self.view.btn_esporta_pdf.setEnabled(not absent)
        self.view.btn_crea_effettivo.setVisible(can_create)
        self.view.lbl_versione_info.setText(
            self._messaggio_versione(absent, can_create, stato_json)
        )
        self.view.aggiorna_badge_modalita(
            self.modalita_corrente, stato_json, self.versione_corrente.value
        )
        nome_mese = self.mesi_ita[self.mese_corrente - 1].upper()
        self.view.btn_mese_anno.setText(f"{nome_mese} {self.anno_corrente}")

        self.roster = roster
        modello = self.view.modello_attivita
        oggi = datetime.date.today()
        specializzandi = self.model.specializzandi
        modello.set_roster(self.roster, specializzandi)
        modello.set_today(oggi)
        self.view.modello_specializzandi.set_rows(
            self.roster, resident_rows(self.roster, specializzandi)
        )
        self.view.modello_specializzandi.set_today(oggi)

    def _avviso(self, titolo: str, messaggio: str) -> None:
        messages.show_message(self.view, titolo, messaggio, section=_SEZIONE, kind="warning")

    def assegna(self, riga: int, colonna: int, nuovo_valore: str) -> None:
        """Assegna ``nuovo_valore`` alla cella (riga = ruolo, colonna = giorno) e ricarica il mese.

        Applica le regole dell'inserimento manuale: mese esistente e non convalidato (nello
        Storico solo l'Effettivo), giorno feriale, nessun altro incarico nella giornata, giro
        visite valido per tutta la settimana (con conferma se sostituisce o rimuove
        un'assegnazione). Le sale operatorie si sincronizzano solo con la stessa versione;
        nell'Effettivo una settimana delle Sale non ancora creata non viene toccata.
        """

        if riga == 0 or not self._puo_modificare():
            return
        data_corrente = datetime.date(self.anno_corrente, self.mese_corrente, colonna + 1)
        if data_corrente.weekday() >= 5:
            return
        data_str = data_corrente.isoformat()
        nome_riga = self.view.row_labels[riga]
        nuovo_valore = nuovo_valore.strip()
        if nuovo_valore == "-":
            nuovo_valore = ""
        effettivo = self.versione_corrente == CalendarVersion.EFFETTIVO

        if nome_riga == "Giro Visite":
            lun_date = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            lun_str = lun_date.isoformat()
            previous = self.model.get_giro_visite_settimana(
                lun_str, self.anno_corrente, self.mese_corrente
            )
            if previous == nuovo_valore:
                return
            try:
                self.model.valida_giro_visite_settimana(lun_str, nuovo_valore)
            except ValueError as error:
                self._avviso(
                    f"Giro visite {self.versione_corrente.value} non modificabile", str(error)
                )
                return
            if previous:
                friday = lun_date + datetime.timedelta(days=4)
                action = "Sostituire l'assegnazione" if nuovo_valore else "Rimuovere l'assegnazione"
                if not messages.ask_confirmation(
                    self.view,
                    f"Modifica giro visite · {self._nome_versione}",
                    f"{action} per tutta la settimana dal {lun_date:%d/%m} al {friday:%d/%m}?",
                    section=_SEZIONE,
                    confirm_text="Sostituisci" if nuovo_valore else "Rimuovi",
                    destructive=True,
                ):
                    return
            try:
                self.model.set_giro_visite_settimana(
                    lun_str, self.anno_corrente, self.mese_corrente, nuovo_valore
                )
            except (OSError, ValueError) as error:
                self._avviso(
                    f"Giro visite {self.versione_corrente.value} non salvato",
                    describe_error(error),
                )
                return
            self.aggiorna_tabella()
            return

        if nuovo_valore and nome_riga != "Tipo Guardia":
            monday = data_corrente - datetime.timedelta(days=data_corrente.weekday())
            used = [
                self.model.get_giro_visite_settimana(
                    monday.isoformat(), self.anno_corrente, self.mese_corrente
                )
            ] + [
                self.model.get_valore_cella(data_str, role)
                for role in self.view.row_labels[2:]
                if role not in (nome_riga, "Giro Visite")
            ]
            if nuovo_valore.casefold() in {value.strip().casefold() for value in used}:
                self._avviso(
                    f"Assegnazione non valida · {self._nome_versione}",
                    "Lo specializzando ha già un altro incarico in questa giornata.",
                )
                return

        sync_rooms = nome_riga in _RUOLI_SALA and self.model_sale_op is not None
        monday = data_corrente - datetime.timedelta(days=data_corrente.weekday())
        if sync_rooms and effettivo:
            sync_rooms = self.model_sale_op.has_settimana(monday)
        if sync_rooms and (
            self.model_sale_op.get_stato_settimana(monday) == "CONVALIDATO"
            or self.model_sale_op.get_stato_mese(data_corrente.year, data_corrente.month)
            == "CONVALIDATO"
        ):
            self._avviso(
                f"Sale {self._nome_versione} convalidate",
                "La settimana delle Sale Operatorie è già convalidata. "
                "L'assegnazione non è stata modificata.",
            )
            return
        actual_assignments = None
        if sync_rooms and effettivo:
            # Nell'Effettivo le Sale possono già divergere dallo scadenzario: si cambia solo
            # la sala modificata, senza ricopiare l'altra dallo scadenzario.
            daily = self.model_sale_op.load_mese(
                data_corrente.year, data_corrente.month
            ).get("turni", {}).get(data_str, {})
            actual_assignments = dict(daily.get("specializzandi") or {})
            _, edited_role = _RUOLI_SALE_OPERATORIE[nome_riga]
            other_role = "OR II" if edited_role == "OR I" else "OR I"
            other_assignment = actual_assignments.get(other_role, "")
            if nuovo_valore and nuovo_valore.casefold() == other_assignment.strip().casefold():
                self._avviso(
                    "Assegnazione non valida · Effettivo",
                    "Lo specializzando è già assegnato all'altra sala nell'Effettivo "
                    "delle Sale Operatorie. L'assegnazione non è stata modificata.",
                )
                return
            actual_assignments[edited_role] = nuovo_valore
            if self._conflitto_assegnazioni_interventi(data_str, nome_riga, nuovo_valore):
                self._avviso(
                    "Assegnazioni Effettivo da verificare",
                    "La sala contiene interventi assegnati a uno specializzando diverso. "
                    "La modifica del turno non riassegna i singoli interventi né le attività "
                    "del libretto. L'assegnazione non è stata modificata.",
                )
                return

        try:
            self.model.set_valore_cella(data_str, nome_riga, nuovo_valore)
        except (OSError, ValueError) as error:
            self._avviso(
                f"Assegnazione {self.versione_corrente.value} non salvata", describe_error(error)
            )
            return

        if sync_rooms:
            try:
                if actual_assignments is not None:
                    or1 = actual_assignments.get("OR I", "")
                    or2 = actual_assignments.get("OR II", "")
                else:
                    or1 = self.model.get_valore_cella(data_str, "Sala Op. I")
                    or2 = self.model.get_valore_cella(data_str, "Sala Op. II")
                self.model_sale_op.set_specializzandi(data_str, or1, or2)
            except (OSError, ValueError) as error:
                self._avviso(
                    f"Sincronizzazione Sale {self.versione_corrente.value} non riuscita",
                    "Assegnazione dello Scadenzario salvata. "
                    f"Aggiornamento delle Sale non riuscito:\n{describe_error(error)}",
                )
        self.aggiorna_tabella()

    def mese_precedente(self):
        with self._resta_sul_mese_se_danneggiato():
            if self.modalita_corrente == "STORICO":
                self._vai_al_mese_storico(-1)
            elif self.mese_corrente == 1:
                self.mese_corrente = 12
                self.anno_corrente -= 1
            else:
                self.mese_corrente -= 1
            self.aggiorna_tabella()

    def mese_successivo(self):
        with self._resta_sul_mese_se_danneggiato():
            if self.modalita_corrente == "STORICO":
                self._vai_al_mese_storico(1)
            elif self.mese_corrente == 12:
                self.mese_corrente = 1
                self.anno_corrente += 1
            else:
                self.mese_corrente += 1
            self.aggiorna_tabella()

    def scegli_mese_anno(self):
        with self._resta_sul_mese_se_danneggiato():
            self._scegli_mese_anno()

    def _scegli_mese_anno(self):
        dialog = DialogMeseAnno(self.mesi_ita, self.mese_corrente, self.anno_corrente, self.view)
        if not dialog.exec():
            return

        selected_mese, selected_anno = dialog.get_selezione()
        selected_date = datetime.date(selected_anno, selected_mese, 1)
        real_date = datetime.date(self.real_anno, self.real_mese, 1)

        if self.modalita_corrente == "PIANIFICAZIONE" and selected_date <= real_date:
            if self.real_mese == 12:
                self.anno_corrente = self.real_anno + 1
                self.mese_corrente = 1
            else:
                self.anno_corrente = self.real_anno
                self.mese_corrente = self.real_mese + 1

        elif self.modalita_corrente == "STORICO":
            # L'ultimo mese convalidato fino a quello scelto; prima del primo, il primo.
            storici_validi = self._mesi_storici()
            if storici_validi:
                scelta = (selected_anno, selected_mese)
                precedenti = [mese for mese in storici_validi if mese <= scelta]
                self.anno_corrente, self.mese_corrente = (
                    precedenti[-1] if precedenti else storici_validi[0]
                )
        else:
            self.mese_corrente = selected_mese
            self.anno_corrente = selected_anno

        self.aggiorna_tabella()
