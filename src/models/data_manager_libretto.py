import os
import json
from datetime import date as _date

class DataManagerLibretto:
    def __init__(self, dir_libretti="mock_data/libretti"):
        self.dir_libretti = dir_libretti
        
        if not os.path.exists(self.dir_libretti):
            os.makedirs(self.dir_libretti, exist_ok=True)

    def get_tutti_specializzandi(self):
        """Legge tutti i file JSON presenti nella cartella libretti e ne fa una lista"""
        specializzandi = []
        for filename in os.listdir(self.dir_libretti):
            if filename.endswith(".json"):
                filepath = os.path.join(self.dir_libretti, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        specializzandi.append(data)
                    except json.JSONDecodeError:
                        pass 
        
        return sorted(specializzandi, key=lambda x: x.get('cognome', ''))
        
    def get_specializzando_by_id(self, spec_id):
        """Cerca e restituisce il dizionario del medico dato il suo ID"""
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def crea_nuovo_specializzando(self, dati_form):
        """Riceve un dizionario dal form e salva il nuovo JSON"""
        file_esistenti = [f for f in os.listdir(self.dir_libretti) if f.endswith(".json")]
        nuovo_id = f"SP{len(file_esistenti) + 1:03d}"
        
        nuovo_specializzando = {
            "id": nuovo_id,
            "matricola": dati_form["matricola"],
            "nome": dati_form["nome"],
            "cognome": dati_form["cognome"],
            "livello": dati_form["livello"],
            "stato": dati_form["stato"]
        }

        filepath = os.path.join(self.dir_libretti, f"{nuovo_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(nuovo_specializzando, f, indent=4)

        return nuovo_specializzando

    def aggiorna_specializzando(self, spec_id, dati):
        """Aggiorna i campi anagrafici di uno specializzando esistente."""
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            spec = json.load(f)
        spec.update({
            "matricola": dati["matricola"],
            "nome":      dati["nome"],
            "cognome":   dati["cognome"],
            "livello":   dati["livello"],
            "stato":     dati["stato"],
        })
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(spec, f, indent=4)
        return spec

    def elimina_specializzando(self, spec_id):
        """Elimina definitivamente il file JSON dello specializzando."""
        filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False

    # ── Registro attività operative ───────────────────────────────────────────

    def _trova_spec_by_nome_formattato(self, nome_formattato: str) -> dict | None:
        """
        Trova lo specializzando dato il formato 'Cognome I.' usato nelle sale operatorie.
        Ritorna il dict completo o None se non trovato.
        """
        parts = nome_formattato.strip().split()
        if len(parts) < 2:
            return None
        cognome_target = parts[0].lower()
        iniziale_target = parts[1].rstrip(".").upper()
        for spec in self.get_tutti_specializzandi():
            if (spec.get("cognome", "").lower() == cognome_target and
                    spec.get("nome", "")[:1].upper() == iniziale_target):
                return spec
        return None

    def registra_attivita_settimana(self, attivita_per_spec: dict):
        """
        Riceve un dict {nome_formattato: [lista_di_attivita_dict]} e scrive
        ogni attività nel file JSON dello specializzando corrispondente.
        La de-duplicazione avviene sulla chiave (data, slot): non aggiunge
        record già presenti.
        """
        for nome_form, lista_att in attivita_per_spec.items():
            spec = self._trova_spec_by_nome_formattato(nome_form)
            if not spec:
                continue
            spec_id = spec["id"]
            filepath = os.path.join(self.dir_libretti, f"{spec_id}.json")
            with open(filepath, "r", encoding="utf-8") as f:
                dati = json.load(f)

            if "attivita" not in dati:
                dati["attivita"] = []

            chiavi_esistenti = {(a["data"], a["slot"]) for a in dati["attivita"]}
            for att in lista_att:
                chiave = (att["data"], att["slot"])
                if chiave not in chiavi_esistenti:
                    dati["attivita"].append(att)
                    chiavi_esistenti.add(chiave)

            dati["attivita"].sort(key=lambda a: (a.get("data", ""), a.get("slot", "")))

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(dati, f, indent=4)

    def get_attivita(self, spec_id: str) -> list:
        """Restituisce la lista di attività dello specializzando, ordinate per data."""
        spec = self.get_specializzando_by_id(spec_id)
        if not spec:
            return []
        return spec.get("attivita", [])

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
