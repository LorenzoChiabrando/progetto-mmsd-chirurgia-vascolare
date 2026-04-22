import json
import os
from datetime import datetime

class DataManager:
    def __init__(self, dir_scadenzario="mock_data/scadenzario",
                 dir_libretti="mock_data/libretti"):
        self.dir_scadenzario = dir_scadenzario
        self.dir_libretti = dir_libretti
        self.specializzandi = self.load_anagrafica()
        
        self._cached_anno = None
        self._cached_mese = None
        self._cached_data = None

        if not os.path.exists(self.dir_scadenzario):
            os.makedirs(self.dir_scadenzario, exist_ok=True)

    def _get_filepath(self, anno, mese):
        return os.path.join(self.dir_scadenzario, f"{anno:04d}-{mese:02d}.json")

    def load_mese(self, anno, mese):
        """Carica il mese specifico, usando la cache se possibile."""
        if self._cached_anno == anno and self._cached_mese == mese:
            return self._cached_data
            
        filepath = self._get_filepath(anno, mese)
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {
                "metadata": {"stato": "BOZZA"},
                "turni": {}
            }
            
        self._cached_anno = anno
        self._cached_mese = mese
        self._cached_data = data
        return data

    def save_mese(self, anno, mese, data):
        """Salva i dati di un mese specifico e aggiorna la cache."""
        filepath = self._get_filepath(anno, mese)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=4)
            
        self._cached_anno = anno
        self._cached_mese = mese
        self._cached_data = data

    def load_anagrafica(self):
        """Carica tutti gli specializzandi dai file SP*.json nella cartella libretti."""
        specializzandi = []
        if not os.path.exists(self.dir_libretti):
            return specializzandi
        for filename in sorted(os.listdir(self.dir_libretti)):
            if filename.endswith(".json"):
                filepath = os.path.join(self.dir_libretti, filename)
                try:
                    with open(filepath, 'r', encoding='utf-8') as f:
                        specializzandi.append(json.load(f))
                except (json.JSONDecodeError, OSError):
                    pass
        return specializzandi

    def get_specializzandi_attivi(self):
        """Restituisce i nomi degli specializzandi attivi alle Molinette."""
        attivi = []
        for spec in self.specializzandi:
            if spec.get("stato") == "Molinette":
                nome_formattato = f"{spec['cognome']} {spec['nome'][0]}."
                attivi.append(nome_formattato)
        return attivi

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
        """Restituisce lo specializzando assegnato al Giro Visite per la settimana (chiave = lunedì ISO)."""
        data = self.load_mese(anno, mese)
        return data.get("giro_visite", {}).get(lun_str, "")

    def set_giro_visite_settimana(self, lun_str: str, anno: int, mese: int, valore: str):
        """Salva lo specializzando al Giro Visite per la settimana indicata."""
        data = self.load_mese(anno, mese)
        if "giro_visite" not in data:
            data["giro_visite"] = {}
        data["giro_visite"][lun_str] = valore
        self.save_mese(anno, mese, data)

    def get_mesi_disponibili(self):
        """Ritorna una lista di tuple (anno, mese) analizzando i file salvati."""
        disponibili = []
        if not os.path.exists(self.dir_scadenzario):
            return disponibili
            
        for filename in os.listdir(self.dir_scadenzario):
            if filename.endswith(".json") and len(filename) == 12: # pattern YYYY-MM.json
                try:
                    anno = int(filename[0:4])
                    mese = int(filename[5:7])
                    disponibili.append((anno, mese))
                except ValueError:
                    pass
        return sorted(disponibili)
        
    def get_stato_mese(self, anno, mese):
        """Recupera lo stato attuale dal blocco metadata del JSON."""
        data = self.load_mese(anno, mese)
        return data.get("metadata", {}).get("stato", "BOZZA")
        
    def set_stato_mese(self, anno, mese, stato):
        """Forza un nuovo stato (es. STAMPA) nel JSON del mese."""
        data = self.load_mese(anno, mese)
        data["metadata"]["stato"] = stato
        self.save_mese(anno, mese, data)
