from __future__ import annotations

import logging
import os
from copy import deepcopy
from datetime import date, timedelta
from pathlib import Path

from src.calendar_versions import (
    CalendarVersion,
    CalendarVersionError,
    month_filename,
    version_directory,
)
from src.data_paths import resolve_data_directory
from src.models.json_files import CorruptedDataError, read_json_object
from src.models.patient_plan_state import write_json_batch
from src.planning_schema import OPTIMIZATION_KEY, default_schedule_optimization

_LOGGER = logging.getLogger(__name__)


class DataManager:
    def __init__(
        self,
        dir_scadenzario=None,
        dir_libretti=None,
        version: CalendarVersion = CalendarVersion.PREVISTO,
    ):
        self.version = CalendarVersion(version)
        self._base_directory = Path(
            dir_scadenzario
            if dir_scadenzario is not None
            else resolve_data_directory() / "scadenzario"
        )
        self.dir_scadenzario = str(version_directory(self._base_directory, self.version))
        self.dir_libretti = str(
            dir_libretti
            if dir_libretti is not None
            else self._base_directory.resolve().parent / "libretti"
        )
        self._cached_anno = None
        self._cached_mese = None
        self._cached_data = None

    def for_version(self, version: CalendarVersion) -> DataManager:
        """Return an independent manager retaining the original data directories."""
        return DataManager(self._base_directory, self.dir_libretti, version=version)

    def invalidate_cache(self) -> None:
        """Discard data potentially changed by another bound manager."""
        self._cached_anno = self._cached_mese = self._cached_data = None

    def has_mese(self, anno: int, mese: int) -> bool:
        """Return whether this version has a persisted month, without creating it."""
        return Path(self._get_filepath(anno, mese)).is_file()

    def _get_filepath(self, anno, mese):
        return os.path.join(self.dir_scadenzario, month_filename(anno, mese))

    def load_mese(self, anno, mese):

        filepath = self._get_filepath(anno, mese)
        if os.path.exists(filepath):
            # Un file danneggiato solleva CorruptedDataError: mai trattarlo come mese vuoto,
            # altrimenti il primo salvataggio lo sovrascriverebbe.
            data = read_json_object(filepath)
        else:
            data = {
                "metadata": {"stato": "BOZZA"},
                "turni": {},
                OPTIMIZATION_KEY: default_schedule_optimization(),
            }

        self._cached_anno = anno
        self._cached_mese = mese
        self._cached_data = data
        return deepcopy(data)

    def _validate_write(self, anno: int, mese: int, data: dict) -> None:
        path = Path(self._get_filepath(anno, mese))
        for day_text in data.get("turni", {}):
            day = date.fromisoformat(day_text)
            if (day.year, day.month) != (anno, mese):
                raise CalendarVersionError("Il giorno non appartiene al mese da salvare.")
        if not path.exists():
            if self.version == CalendarVersion.EFFETTIVO:
                raise CalendarVersionError("Creare prima la copia Effettivo del mese.")
            previous = {}
        else:
            previous = read_json_object(path)
        if previous.get("metadata", {}).get("stato") == "CONVALIDATO" and previous != data:
            raise CalendarVersionError("Il mese è già convalidato e non può essere modificato.")
        if (
            data.get("metadata", {}).get("stato") == "CONVALIDATO"
            and previous.get("metadata", {}).get("stato") != "CONVALIDATO"
        ):
            raise CalendarVersionError("Usare convalida_mese per convalidare il mese.")

    def save_mese(self, anno, mese, data):
        try:
            self._validate_write(anno, mese, data)
            write_json_batch({Path(self._get_filepath(anno, mese)): data})
        finally:
            self.invalidate_cache()

    def _prepare_actual_month(self, anno: int, mese: int, source: dict) -> dict:
        actual = self.for_version(CalendarVersion.EFFETTIVO)
        if actual.has_mese(anno, mese):
            raise CalendarVersionError("La copia Effettivo del mese esiste già.")
        copied = deepcopy(source)
        copied.setdefault("metadata", {})["stato"] = "BOZZA"
        return {Path(actual._get_filepath(anno, mese)): copied}

    def crea_effettivo_mese(self, anno: int, mese: int) -> None:
        """Copy a confirmed planned month into a new editable actual month."""
        planned = self.for_version(CalendarVersion.PREVISTO)
        source = planned.load_mese(anno, mese)
        if (
            not planned.has_mese(anno, mese)
            or source.get("metadata", {}).get("stato") != "CONVALIDATO"
        ):
            raise CalendarVersionError("Convalidare prima il mese Previsto.")
        try:
            write_json_batch(self._prepare_actual_month(anno, mese, source))
        finally:
            self.invalidate_cache()

    def convalida_mese(self, anno: int, mese: int) -> None:
        """Freeze this month; planned confirmation atomically creates its actual copy."""
        self.invalidate_cache()
        if not self.has_mese(anno, mese):
            raise CalendarVersionError("Il mese da convalidare non esiste.")
        source = self.load_mese(anno, mese)
        if source.get("metadata", {}).get("stato") == "CONVALIDATO":
            raise CalendarVersionError("Il mese è già convalidato.")
        updates = {}
        if self.version == CalendarVersion.PREVISTO:
            updates.update(self._prepare_actual_month(anno, mese, source))
        source.setdefault("metadata", {})["stato"] = "CONVALIDATO"
        updates[Path(self._get_filepath(anno, mese))] = source
        try:
            write_json_batch(updates)
        finally:
            self.invalidate_cache()

    @property
    def specializzandi(self):
        """Anagrafica riletta a ogni accesso: il Libretto la modifica mentre l'app è aperta."""
        return self.load_anagrafica()

    def load_anagrafica(self):
        specializzandi = []
        if not os.path.exists(self.dir_libretti):
            return specializzandi
        for filename in sorted(os.listdir(self.dir_libretti)):
            if filename.endswith(".json"):
                filepath = os.path.join(self.dir_libretti, filename)
                try:
                    specializzandi.append(read_json_object(filepath))
                except (CorruptedDataError, OSError):
                    _LOGGER.warning("Libretto illeggibile ignorato: %s", filename)
        return specializzandi

    def get_specializzandi_attivi(self):
        attivi = []
        for spec in self.specializzandi:
            if spec.get("stato") == "Molinette":
                nome_formattato = f"{spec['cognome']} {spec['nome'][0]}."
                attivi.append(nome_formattato)
        return attivi

    def get_nome_completo_specializzando(self, nome_formattato: str) -> str:
        """Ricava il nome completo dall'anagrafica locale."""

        from src.calendar_presentation import resolve_resident_name

        return resolve_resident_name(nome_formattato, self.specializzandi)

    def get_valore_cella(self, data_str, nome_riga):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        return data["turni"].get(data_str, {}).get(nome_riga, "")

    def set_valore_cella(self, data_str, nome_riga, valore):
        anno = int(data_str[:4])
        mese = int(data_str[5:7])
        data = self.load_mese(anno, mese)
        
        if data_str not in data["turni"]:
            data["turni"][data_str] = {}
            
        data["turni"][data_str][nome_riga] = valore
        self.save_mese(anno, mese, data)
        
    def get_giro_visite_settimana(self, lun_str: str, anno: int, mese: int) -> str:
        data = self.load_mese(anno, mese)
        if lun_str in data.get("giro_visite", {}):
            return data["giro_visite"][lun_str]
        for year, month in self._mesi_giro_visite(lun_str):
            assignment = self.load_mese(year, month).get("giro_visite", {}).get(lun_str)
            if assignment is not None:
                return assignment
        return ""

    @staticmethod
    def _mesi_giro_visite(lun_str: str) -> tuple[tuple[int, int], ...]:
        monday = date.fromisoformat(lun_str)
        if monday.weekday() != 0:
            raise ValueError("Il giro visite deve iniziare di lunedì.")
        days = [monday + timedelta(days=offset) for offset in range(5)]
        return tuple(sorted({(day.year, day.month) for day in days}))

    def valida_giro_visite_settimana(self, lun_str: str, valore: str) -> None:
        """Controlla mesi convalidati e altri incarichi su tutti i cinque giorni."""
        monday = date.fromisoformat(lun_str)
        months = {
            key: self.load_mese(*key) for key in self._mesi_giro_visite(lun_str)
        }
        for data in months.values():
            previous = data.get("giro_visite", {}).get(lun_str, "")
            if data.get("metadata", {}).get("stato") == "CONVALIDATO" and previous != valore:
                raise ValueError("La settimana comprende giorni di un mese già convalidato.")
        if not valore:
            return
        for offset in range(5):
            day = monday + timedelta(days=offset)
            daily = months[day.year, day.month].get("turni", {}).get(day.isoformat(), {})
            if any(
                isinstance(assigned, str)
                and assigned.strip().casefold() == valore.strip().casefold()
                for role, assigned in daily.items()
                if role not in ("Tipo Guardia", "Giro Visite")
            ):
                raise ValueError(
                    f"Lo specializzando ha già un altro incarico il {day:%d/%m/%Y}. "
                    "Scegli un nome disponibile per tutta la settimana."
                )

    def set_giro_visite_settimana(self, lun_str: str, anno: int, mese: int, valore: str):
        self.valida_giro_visite_settimana(lun_str, valore)
        if self.version == CalendarVersion.EFFETTIVO and any(
            not self.has_mese(year, month) for year, month in self._mesi_giro_visite(lun_str)
        ):
            raise CalendarVersionError(
                "Creare la copia Effettivo di tutti i mesi della settimana del Giro Visite."
            )
        updates = {}
        try:
            for year, month in self._mesi_giro_visite(lun_str):
                data = self.load_mese(year, month)
                if data.get("metadata", {}).get("stato") == "CONVALIDATO":
                    continue
                data.setdefault("giro_visite", {})[lun_str] = valore
                self._validate_write(year, month, data)
                updates[Path(self._get_filepath(year, month))] = data
            write_json_batch(updates)
        finally:
            self.invalidate_cache()

    def get_mesi_disponibili(self):
        disponibili = []
        if not os.path.exists(self.dir_scadenzario):
            return disponibili

        for filename in os.listdir(self.dir_scadenzario):
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
        if stato == "CONVALIDATO":
            self.convalida_mese(anno, mese)
            return
        data = self.load_mese(anno, mese)
        data.setdefault("metadata", {})["stato"] = stato
        self.save_mese(anno, mese, data)
