from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from unicodedata import normalize

from src.calendar_versions import CalendarVersionError
from src.data_paths import resolve_data_directory
from src.models.id_generator import next_available_id
from src.models.json_files import CorruptedDataError, read_json_object, write_json_atomic
from src.models.patient_plan_state import write_json_batch

_LOGGER = logging.getLogger(__name__)


class DataManagerLibretto:
    def __init__(self, dir_libretti=None):
        self.dir_libretti = str(
            dir_libretti if dir_libretti is not None else resolve_data_directory() / "libretti"
        )
        
        if not os.path.exists(self.dir_libretti):
            os.makedirs(self.dir_libretti, exist_ok=True)

    def get_tutti_specializzandi(self):
        specializzandi = []
        for filename in os.listdir(self.dir_libretti):
            if filename.endswith(".json"):
                filepath = os.path.join(self.dir_libretti, filename)
                try:
                    specializzandi.append(read_json_object(filepath))
                except CorruptedDataError:
                    # Un libretto rotto non deve nascondere tutti gli altri.
                    _LOGGER.warning("Libretto danneggiato ignorato: %s", filename)
        
        return sorted(specializzandi, key=lambda x: x.get('cognome', ''))
        
    def get_specializzando_by_id(self, spec_id):
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if os.path.exists(filepath):
            return read_json_object(filepath)
        return None

    def crea_nuovo_specializzando(self, dati_form):
        nuovo_specializzando = {
            "id": "",
            "matricola": dati_form["matricola"],
            "nome": dati_form["nome"],
            "cognome": dati_form["cognome"],
            "livello": dati_form["livello"],
            "stato": dati_form["stato"],
        }

        while True:
            nuovo_id = next_available_id(self.dir_libretti, "SP", 3)
            nuovo_specializzando["id"] = nuovo_id
            filepath = os.path.join(self.dir_libretti, f"{nuovo_id}.json")
            payload = json.dumps(nuovo_specializzando, indent=4)
            try:
                with open(filepath, 'x', encoding='utf-8') as f:
                    f.write(payload)
                break
            except FileExistsError:
                continue

        return nuovo_specializzando

    def aggiorna_specializzando(self, spec_id, dati):
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if not os.path.exists(filepath):
            return None
        spec = read_json_object(filepath)
        spec.update({
            "matricola": dati["matricola"],
            "nome":      dati["nome"],
            "cognome":   dati["cognome"],
            "livello":   dati["livello"],
            "stato":     dati["stato"],
        })
        write_json_atomic(filepath, spec)
        return spec

    def elimina_specializzando(self, spec_id):
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    @staticmethod
    def _normalized_resident_name(value: str) -> str:
        """Normalize a full display name without splitting compound surnames."""
        return " ".join(normalize("NFKC", value).split()).casefold().rstrip(".")

    def _trova_spec_by_nome_formattato(self, nome_formattato: str) -> dict | None:
        """Resolve the complete ``Surname I.`` label only when it is unique."""
        target = self._normalized_resident_name(nome_formattato)
        matches = []
        for spec in self.get_tutti_specializzandi():
            surname = spec.get("cognome", "").strip()
            name = spec.get("nome", "").strip()
            if not surname or not name:
                continue
            candidate = self._normalized_resident_name(f"{surname} {name[0]}.")
            if candidate == target:
                matches.append(spec)
        return matches[0] if len(matches) == 1 else None

    @staticmethod
    def _activity_key(activity: dict) -> tuple[str, str]:
        """Use the legacy start time only when the activity has no slot field."""
        slot = activity["slot"] if "slot" in activity else activity["ora_inizio"]
        return activity["data"], slot

    def prepara_attivita_settimana(
        self,
        attivita_per_spec: dict,
        *,
        require_all: bool = False,
        attivita_ordinate: list[tuple[str, str, dict]] | None = None,
    ) -> dict[Path, dict]:
        """Prepare deduplicated activities by stable ID or unique legacy label.

        ``attivita_ordinate`` contains (resident ID, display name, activity) entries
        in operation order. Nonempty IDs never fall back to a display name.
        ``require_all`` rejects missing or ambiguous recipients before any write.
        The first (date, slot) entry wins; legacy records without ``slot`` use
        ``ora_inizio`` for both deduplication and ordering without being modified.
        """
        recipients = [
            (self._trova_spec_by_nome_formattato(name), activities)
            for name, activities in attivita_per_spec.items()
        ]
        catalog = self.get_tutti_specializzandi() if attivita_ordinate else []
        for identifier, name, activity in attivita_ordinate or []:
            if identifier:
                matches = [spec for spec in catalog if spec.get("id") == identifier]
                spec = matches[0] if len(matches) == 1 else None
            else:
                spec = self._trova_spec_by_nome_formattato(name)
            recipients.append((spec, [activity]))
        updates: dict[Path, dict] = {}
        for spec, activities in recipients:
            if spec is None:
                if require_all:
                    raise CalendarVersionError(
                        "Un assegnatario è assente o ambiguo nei libretti: correggere il piano."
                    )
                continue
            filepath = Path(self.dir_libretti) / f"{spec['id']}.json"
            if filepath not in updates:
                updates[filepath] = read_json_object(filepath)
            dati = updates[filepath]
            records = dati.setdefault("attivita", [])
            existing = {self._activity_key(record) for record in records}
            for activity in activities:
                key = self._activity_key(activity)
                if key not in existing:
                    records.append(activity)
                    existing.add(key)
            records.sort(key=self._activity_key)
        return updates

    def registra_attivita_settimana(self, attivita_per_spec: dict):
        """Persist activities, retaining the historical (date, slot) identity."""
        write_json_batch(self.prepara_attivita_settimana(attivita_per_spec))

    def get_attivita(self, spec_id: str) -> list:
        spec = self.get_specializzando_by_id(spec_id)
        if not spec:
            return []
        return spec.get("attivita", [])

    def get_attivita_extra(self, spec_id: str) -> list:
        spec = self.get_specializzando_by_id(spec_id)
        if not spec:
            return []
        return spec.get("attivita_extra", [])

    def salva_attivita_extra(self, spec_id: str, att_data: dict):
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if not os.path.exists(filepath):
            return
        dati = read_json_object(filepath)
        if "attivita_extra" not in dati:
            dati["attivita_extra"] = []
        chiave = (att_data.get("data"), att_data.get("sede"), att_data.get("attivita"))
        for i, e in enumerate(dati["attivita_extra"]):
            if (e.get("data"), e.get("sede"), e.get("attivita")) == chiave:
                dati["attivita_extra"][i] = att_data
                break
        else:
            dati["attivita_extra"].append(att_data)
        dati["attivita_extra"].sort(key=lambda a: (a.get("data", ""), a.get("sede", "")))
        write_json_atomic(filepath, dati)

    def get_meta_giorno(self, spec_id: str, data_str: str) -> dict:
        spec = self.get_specializzando_by_id(spec_id)
        if not spec:
            return {}
        return spec.get("meta_giorni", {}).get(data_str, {})

    def salva_meta_giorno(self, spec_id: str, data_str: str, meta_dict: dict):
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if not os.path.exists(filepath):
            return
        dati = read_json_object(filepath)
        if "meta_giorni" not in dati:
            dati["meta_giorni"] = {}
        dati["meta_giorni"][data_str] = meta_dict
        write_json_atomic(filepath, dati)

    def calcola_training_score(self, spec_id: str) -> tuple:
        """
        Calcola il punteggio formativo.
        Regola: Alta=3pt, Media=2pt, Bassa=1pt; ruolo OR I aggiunge +0.5 per intervento.
        Ritorna (n_interventi: int, punteggio_totale: float).
        """
        _punti = {"Alta": 3.0, "Media": 2.0, "Bassa": 1.0}
        totale = 0.0
        attivita = self.get_attivita(spec_id)
        for att in attivita:
            base = _punti.get(att.get("complessita", ""), 1.0)
            bonus = 0.5 if att.get("ruolo") == "OR I" else 0.0
            totale += base + bonus
        return len(attivita), totale
