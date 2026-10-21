from __future__ import annotations

import datetime as dt
import json
import os
from copy import deepcopy
from pathlib import Path

from src.calendar_versions import (
    CalendarVersion,
    CalendarVersionError,
    month_filename,
    version_directory,
    week_days,
)
from src.data_paths import resolve_data_directory
from src.models.data_manager_libretto import DataManagerLibretto
from src.models.json_files import read_json_object
from src.models.patient_plan_state import (
    patient_status_updates,
    read_operational_plan_months,
    read_plan_months,
    write_json_batch,
)


class DataManagerSaleOperatorie:
    def __init__(
        self,
        dir_sale_operatorie=None,
        filepath_anagrafica=None,
        dir_pazienti=None,
        version: CalendarVersion = CalendarVersion.PREVISTO,
    ):
        self.version = CalendarVersion(version)
        self._base_directory = Path(
            dir_sale_operatorie
            if dir_sale_operatorie is not None
            else resolve_data_directory() / "sale_operatorie"
        )
        self.dir_sale_operatorie = str(version_directory(self._base_directory, self.version))
        data_directory = self._base_directory.resolve().parent
        self.dir_pazienti = (
            Path(dir_pazienti) if dir_pazienti is not None else data_directory / "pazienti"
        )
        self.filepath_anagrafica = str(
            filepath_anagrafica
            if filepath_anagrafica is not None
            else data_directory / "static_data" / "anagrafica_specializzandi.json"
        )
        self.specializzandi = self.load_anagrafica()

        self._cached_anno = None
        self._cached_mese = None
        self._cached_data = None

    def for_version(self, version: CalendarVersion) -> DataManagerSaleOperatorie:
        """Bind a new manager to a version while preserving all associated paths."""
        return DataManagerSaleOperatorie(
            self._base_directory, self.filepath_anagrafica, self.dir_pazienti, version=version,
        )

    def has_settimana(self, lun: dt.date) -> bool:
        """Check presence; actual weeks require an explicit canonical week marker."""
        days = week_days(lun)
        canonical = self.load_mese(lun.year, lun.month)
        if lun.isoformat() in canonical.get("metadata", {}).get("settimane", {}):
            return True
        if self.version == CalendarVersion.EFFETTIVO:
            return False
        months = {(lun.year, lun.month): canonical}
        for day in days:
            key = (day.year, day.month)
            if key not in months:
                months[key] = self.load_mese(*key)
            if day.isoformat() in months[key].get("turni", {}):
                return True
        return False

    def invalidate_cache(self):
        """Force the next read to reload data written by an external planner."""

        self._cached_anno = None
        self._cached_mese = None
        self._cached_data = None

    def _get_filepath(self, anno, mese):
        return os.path.join(self.dir_sale_operatorie, month_filename(anno, mese))

    def load_mese(self, anno, mese):

        filepath = self._get_filepath(anno, mese)
        if os.path.exists(filepath):
            # Un file danneggiato solleva CorruptedDataError: mai trattarlo come mese vuoto.
            data = read_json_object(filepath)
        else:
            data = {"metadata": {"stato": "BOZZA"}, "turni": {}}

        self._cached_anno = anno
        self._cached_mese = mese
        self._cached_data = data
        return deepcopy(data)

    def _validate_write(self, anno: int, mese: int, data: dict) -> None:
        months = read_plan_months(Path(self.dir_sale_operatorie))
        key = month_filename(anno, mese)[:-5]
        previous = months.get(key, {})
        before_days = previous.get("turni", {})
        after_days = data.get("turni", {})
        weeks = previous.get("metadata", {}).get("settimane", {})
        new_weeks = data.get("metadata", {}).get("settimane", {})
        for monday_text in weeks.keys() | new_weeks.keys():
            monday = dt.date.fromisoformat(monday_text)
            week_days(monday)
            if monday.year != anno or monday.month != mese:
                raise CalendarVersionError(
                    "Lo stato della settimana appartiene al mese del lunedì."
                )
            if weeks.get(monday_text) != new_weeks.get(monday_text):
                if weeks.get(monday_text) == "CONVALIDATO":
                    raise CalendarVersionError("La settimana è già convalidata.")
                if new_weeks.get(monday_text) == "CONVALIDATO":
                    raise CalendarVersionError("Usare convalida_settimana per convalidare.")
                if self.version == CalendarVersion.EFFETTIVO:
                    raise CalendarVersionError("Creare prima la copia Effettivo della settimana.")
        if self.version == CalendarVersion.EFFETTIVO and key not in months:
            raise CalendarVersionError("Creare prima la copia Effettivo della settimana.")
        for day_text in before_days.keys() | after_days.keys():
            if before_days.get(day_text) == after_days.get(day_text):
                continue
            day = dt.date.fromisoformat(day_text)
            if day.year != anno or day.month != mese:
                raise CalendarVersionError("Il giorno non appartiene al mese da salvare.")
            monday = day - dt.timedelta(days=day.weekday())
            canonical = months.get(monday.strftime("%Y-%m"), {})
            states = canonical.get("metadata", {}).get("settimane", {})
            if states.get(monday.isoformat()) == "CONVALIDATO":
                raise CalendarVersionError("La settimana è già convalidata.")
            if self.version == CalendarVersion.EFFETTIVO and monday.isoformat() not in states:
                raise CalendarVersionError("Creare prima la copia Effettivo della settimana.")

    def _write_updates(self, updates: dict[Path, dict]) -> None:
        try:
            updates.update(
                patient_status_updates(
                    self.dir_pazienti,
                    self._base_directory,
                    updates,
                )
            )
            write_json_batch(updates)
        finally:
            self.invalidate_cache()

    def save_mese(self, anno, mese, data):
        try:
            self._validate_write(anno, mese, data)
            self._write_updates({Path(self._get_filepath(anno, mese)): data})
        finally:
            self.invalidate_cache()

    def _prepare_actual_week(self, lun: dt.date, sources: dict[str, dict]) -> dict[Path, dict]:
        actual = self.for_version(CalendarVersion.EFFETTIVO)
        if actual.has_settimana(lun):
            raise CalendarVersionError("La copia Effettivo della settimana esiste già.")
        months = read_plan_months(Path(actual.dir_sale_operatorie))
        updates = {}
        for day in week_days(lun):
            key = day.strftime("%Y-%m")
            month = months.setdefault(key, {"metadata": {"stato": "BOZZA"}, "turni": {}})
            target_days = month.setdefault("turni", {})
            if day.isoformat() in target_days:
                raise CalendarVersionError("Esistono già dati Effettivo per la settimana.")
            target_days[day.isoformat()] = deepcopy(
                sources.get(key, {}).get("turni", {}).get(day.isoformat(), {})
            )
            updates[Path(actual._get_filepath(day.year, day.month))] = month
        months[lun.strftime("%Y-%m")].setdefault("metadata", {}).setdefault("settimane", {})[
            lun.isoformat()
        ] = "BOZZA"
        return updates

    def crea_effettivo_settimana(self, lun: dt.date) -> None:
        """Explicitly copy a confirmed planned week without overwriting actual data."""
        week_days(lun)
        planned = self.for_version(CalendarVersion.PREVISTO)
        if not planned.has_settimana(lun) or planned.get_stato_settimana(lun) != "CONVALIDATO":
            raise CalendarVersionError("Convalidare prima la settimana Previsto.")
        sources = read_plan_months(Path(planned.dir_sale_operatorie))
        self._write_updates(self._prepare_actual_week(lun, sources))

    def convalida_settimana(self, lun: dt.date, *, dir_libretti: str | Path | None = None) -> None:
        """Confirm atomically; only actual confirmation records performed activities."""
        week_days(lun)
        self.invalidate_cache()
        if not self.has_settimana(lun):
            raise CalendarVersionError("La settimana da convalidare non esiste.")
        if self.get_stato_settimana(lun) == "CONVALIDATO":
            raise CalendarVersionError("La settimana è già convalidata.")
        months = read_plan_months(Path(self.dir_sale_operatorie))
        canonical = months.setdefault(lun.strftime("%Y-%m"), {"metadata": {}, "turni": {}})
        updates = {}
        if self.version == CalendarVersion.PREVISTO:
            updates.update(self._prepare_actual_week(lun, months))
        canonical.setdefault("metadata", {}).setdefault("settimane", {})[lun.isoformat()] = (
            "CONVALIDATO"
        )
        updates[Path(self._get_filepath(lun.year, lun.month))] = canonical
        try:
            updates.update(patient_status_updates(self.dir_pazienti, self._base_directory, updates))
            if self.version == CalendarVersion.EFFETTIVO:
                libretti = (
                    Path(dir_libretti)
                    if dir_libretti is not None
                    else self._base_directory.resolve().parent / "libretti"
                )
                updates.update(self._prepare_performed_week(lun, months, libretti))
            write_json_batch(updates)
        finally:
            self.invalidate_cache()

    def _prepare_performed_week(
        self,
        lun: dt.date,
        months: dict[str, dict],
        libretti: Path,
    ) -> dict[Path, dict]:
        patients = {}
        for path in sorted(self.dir_pazienti.glob("*.json")):
            record = json.loads(path.read_text(encoding="utf-8"))
            patients[record.get("id")] = (path, record)
        activities: list[tuple[str, str, dict]] = []
        updates = {}
        for day in week_days(lun):
            daily = months.get(day.strftime("%Y-%m"), {}).get("turni", {}).get(day.isoformat(), {})
            assigned = daily.get("specializzandi", {})
            for operation in daily.get("operazioni", []):
                if operation.get("id_paziente") and not self.dir_pazienti.is_dir():
                    raise CalendarVersionError("La directory pazienti non è disponibile.")
                patient_entry = patients.get(operation.get("id_paziente"))
                if operation.get("id_paziente") and patient_entry is None:
                    raise CalendarVersionError(
                        "Una scheda paziente non esiste: correggere il piano Effettivo."
                    )
                patient = patient_entry[1] if patient_entry else {}
                if patient_entry:
                    updates[patient_entry[0]] = {**patient, "stato": "Completato"}
                if not operation.get("nome_paziente"):
                    continue
                activity = {
                    "data": day.isoformat(),
                    "slot": operation.get("ora_inizio", "08:00"),
                    **{
                        key: operation.get(key, "")
                        for key in (
                            "nome_paziente",
                            "id_paziente",
                            "diagnosi",
                            "intervento",
                            "codice_intervento",
                            "chirurgo",
                        )
                    },
                    "interventi": operation.get("interventi", []),
                    "complessita": operation.get("complessita") or patient.get("complessita", ""),
                    "tipo_chirurgia": operation.get("tipo_chirurgia")
                    or patient.get("tipo_chirurgia", ""),
                    "ora_inizio": operation.get("ora_inizio", "08:00"),
                    "ora_fine": operation.get("ora_fine", "18:00"),
                    "durata": operation.get("durata", 90),
                }
                resident_id = operation.get("id_specializzando")
                if resident_id:
                    activities.append((
                        resident_id, "",
                        {**activity, "ruolo": operation.get("ruolo_specializzando", "")},
                    ))
                    continue
                if any(
                    key in operation
                    for key in (
                        "id_specializzando",
                        "specializzando",
                        "ruolo_specializzando",
                    )
                ):
                    targets = [
                        (
                            operation.get("ruolo_specializzando", ""),
                            operation.get("specializzando", ""),
                        )
                    ]
                else:
                    targets = [(role, assigned.get(role, "")) for role in ("OR I", "OR II")]
                for role, name in targets:
                    if name:
                        activities.append(("", name, {**activity, "ruolo": role}))
        if activities:
            if not libretti.is_dir():
                raise CalendarVersionError("La directory libretti non è disponibile.")
            updates.update(
                DataManagerLibretto(libretti).prepara_attivita_settimana(
                    {}, require_all=True, attivita_ordinate=activities,
                )
            )
        return updates

    def load_anagrafica(self):
        if os.path.exists(self.filepath_anagrafica):
            with open(self.filepath_anagrafica, encoding='utf-8') as f:
                return json.load(f)
        return []

    def get_specializzandi_attivi(self):
        attivi = []
        for spec in self.specializzandi:
            if spec.get("attivo", False):
                nome_formattato = f"{spec['cognome']} {spec['nome'][0]}."
                attivi.append(nome_formattato)
        return attivi

    def get_valore_cella(self, data_str, nome_riga):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        return data["turni"].get(data_str, {}).get(nome_riga, "")

    def get_specializzandi(self, data_str):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)

        turno = data["turni"].get(data_str, {})

        specializzandi = turno.get("specializzandi") or {}
        or1 = specializzandi.get("OR I", "")
        or2 = specializzandi.get("OR II", "")

        return f"{or1}\n{or2}".strip()

    def get_slot(self, data_str, nome_riga):
        slot = self.get_slot_raw(data_str, nome_riga)
        if not slot:
            return ""
        if isinstance(slot, str):
            return slot
        nome_paz = slot.get("nome_paziente", "")
        if not nome_paz:
            return ""
        id_paz = slot.get("id_paziente", "")
        codice = slot.get("codice_intervento", "")
        seconda_riga = " · ".join(filter(None, [id_paz, codice]))
        return f"{nome_paz}\n{seconda_riga}" if seconda_riga else nome_paz

    def get_slot_raw(self, data_str, slot_label):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        turno = data["turni"].get(data_str, {})
        return turno.get(slot_label, {})

    def set_valore_cella(self, data_str, nome_riga, valore):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)

        if data_str not in data["turni"]:
            data["turni"][data_str] = {}

        data["turni"][data_str][nome_riga] = valore
        self.save_mese(anno, mese, data)

    def set_specializzandi(self, data_str, or1, or2):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)

        if data_str not in data["turni"]:
            data["turni"][data_str] = {}

        data["turni"][data_str]["specializzandi"] = {"OR I": or1, "OR II": or2}
        self.save_mese(anno, mese, data)

    def get_stato_settimana(self, lun_date):
        """
        Restituisce lo stato della settimana che inizia il lunedì indicato.
        Lo stato è salvato in metadata.settimane[lun_str] del file mensile.
        """
        lun_str = lun_date.strftime("%Y-%m-%d")
        data = self.load_mese(lun_date.year, lun_date.month)
        settimane = data.get("metadata", {}).get("settimane", {})
        return settimane.get(lun_str, "BOZZA")

    def set_stato_settimana(self, lun_date, stato):
        week_days(lun_date)
        if stato == "CONVALIDATO":
            self.convalida_settimana(lun_date)
            return
        data = self.load_mese(lun_date.year, lun_date.month)
        data.setdefault("metadata", {}).setdefault("settimane", {})[lun_date.isoformat()] = stato
        self.save_mese(lun_date.year, lun_date.month, data)

    def set_slot_data(self, data_str, slot_label, slot_dict):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        if data_str not in data["turni"]:
            data["turni"][data_str] = {}
        data["turni"][data_str][slot_label] = slot_dict
        self.save_mese(anno, mese, data)

    def get_settimane_convalidate(self):
        """
        Scansiona tutti i file mensili e restituisce una lista ordinata di
        datetime.date (i lunedì) per cui lo stato è 'CONVALIDATO'.
        """
        convalidate = []
        if not os.path.exists(self.dir_sale_operatorie):
            return convalidate

        for filename in os.listdir(self.dir_sale_operatorie):
            if not (filename.endswith(".json") and len(filename) == 12):
                continue
            try:
                anno = int(filename[0:4])
                mese = int(filename[5:7])
            except ValueError:
                continue

            data = self.load_mese(anno, mese)
            settimane = data.get("metadata", {}).get("settimane", {})
            for lun_str, stato in settimane.items():
                if stato == "CONVALIDATO":
                    try:
                        lun_date = dt.date.fromisoformat(lun_str)
                        convalidate.append(lun_date)
                    except ValueError:
                        pass

        return sorted(convalidate)

    def get_pazienti_pianificati_ids(self, exclude_lun_date: dt.date | None = None) -> set:
        """
        Restituisce gli ID dei pazienti assegnati a qualsiasi slot
        di settimane non ancora convalidate (stato BOZZA).
        Se exclude_lun_date è fornito, salta la settimana che inizia in quella data.
        """
        return set(self.get_pianificazioni_pazienti(exclude_lun_date))

    def get_pianificazioni_pazienti(
        self,
        exclude_lun_date: dt.date | None = None,
    ) -> dict[str, tuple[dt.date, ...]]:
        """Restituisce le date pianificate per ID paziente."""

        dates_by_patient: dict[str, set[dt.date]] = {}
        exclude_str = exclude_lun_date.strftime("%Y-%m-%d") if exclude_lun_date else None
        months = read_operational_plan_months(self._base_directory)
        for month_key, data in months.items():
            anno, mese = map(int, month_key.split("-"))
            settimane_stati = data.get("metadata", {}).get("settimane", {})

            for data_str, turno in data.get("turni", {}).items():
                try:
                    d = dt.date.fromisoformat(data_str)
                except ValueError:
                    continue
                lun = d - dt.timedelta(days=d.weekday())
                lun_str = lun.strftime("%Y-%m-%d")
                if lun.year == anno and lun.month == mese:
                    stato_sett = settimane_stati.get(lun_str, "BOZZA")
                else:
                    lun_data = months.get(lun.strftime("%Y-%m"), {})
                    stato_sett = (
                        lun_data.get("metadata", {}).get("settimane", {}).get(lun_str, "BOZZA")
                    )
                if stato_sett == "CONVALIDATO":
                    continue
                if exclude_str and lun_str == exclude_str:
                    continue
                for op in turno.get("operazioni", []):
                    if op.get("id_paziente"):
                        dates_by_patient.setdefault(op["id_paziente"], set()).add(d)
                for key, val in turno.items():
                    if (
                        key not in ("operazioni", "specializzandi")
                        and isinstance(val, dict)
                        and val.get("id_paziente")
                    ):
                        dates_by_patient.setdefault(val["id_paziente"], set()).add(d)

        return {
            patient_id: tuple(sorted(dates))
            for patient_id, dates in sorted(dates_by_patient.items())
        }

    def get_operazioni(self, data_str: str) -> list:
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        turno = data["turni"].get(data_str, {})
        return turno.get("operazioni", [])

    def set_operazioni(self, data_str: str, operazioni: list):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        if data_str not in data["turni"]:
            data["turni"][data_str] = {}
        data["turni"][data_str]["operazioni"] = operazioni
        for old_key in ["8.00-10.00", "10.00-12.00", "14.00-16.00", "16.00-18.00"]:
            data["turni"][data_str].pop(old_key, None)
        self._cached_data = None
        self.save_mese(anno, mese, data)

    def get_mesi_disponibili(self):
        disponibili = []
        if not os.path.exists(self.dir_sale_operatorie):
            return disponibili

        for filename in os.listdir(self.dir_sale_operatorie):
            if filename.endswith(".json") and len(filename) == 12:
                try:
                    anno = int(filename[0:4])
                    mese = int(filename[5:7])
                    disponibili.append((anno, mese))
                except ValueError:
                    pass
        return sorted(disponibili)

    def get_stato_mese(self, anno, mese):
        data = self.load_mese(anno, mese)
        return data.get("metadata", {}).get("stato", "BOZZA")

    def set_stato_mese(self, anno, mese, stato):
        data = self.load_mese(anno, mese)
        data["metadata"]["stato"] = stato
        self.save_mese(anno, mese, data)
