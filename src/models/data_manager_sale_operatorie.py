import json
import os
import datetime as dt
from datetime import datetime


class DataManagerSaleOperatorie:
    def __init__(self, dir_sale_operatorie="mock_data/sale_operatorie",
                 filepath_anagrafica="mock_data/static_data/anagrafica_specializzandi.json"):
        self.dir_sale_operatorie = dir_sale_operatorie
        self.filepath_anagrafica = filepath_anagrafica
        self.specializzandi = self.load_anagrafica()

        self._cached_anno = None
        self._cached_mese = None
        self._cached_data = None

        if not os.path.exists(self.dir_sale_operatorie):
            os.makedirs(self.dir_sale_operatorie, exist_ok=True)

    def _get_filepath(self, anno, mese):
        return os.path.join(self.dir_sale_operatorie, f"{anno:04d}-{mese:02d}.json")

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
        if os.path.exists(self.filepath_anagrafica):
            with open(self.filepath_anagrafica, 'r', encoding='utf-8') as f:
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
        """Ritorna stringa formattata su due righe: 'Nome\nPZ0001 · 38.12' per la cella."""
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
        """Ritorna il dict grezzo dello slot (nome_paziente, id_paziente, diagnosi, ...)."""
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
        """Scrive i due specializzandi assegnati alla sala operatoria per un giorno."""
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
        """Scrive lo stato (BOZZA / CONVALIDATO) per la settimana indicata."""
        lun_str = lun_date.strftime("%Y-%m-%d")
        anno, mese = lun_date.year, lun_date.month
        data = self.load_mese(anno, mese)
        if "settimane" not in data["metadata"]:
            data["metadata"]["settimane"] = {}
        data["metadata"]["settimane"][lun_str] = stato
        self.save_mese(anno, mese, data)

    def set_slot_data(self, data_str, slot_label, slot_dict):
        """
        Scrive un dict strutturato per uno slot orario.
        slot_dict ha chiavi: nome_paziente, diagnosi, intervento, chirurgo.
        """
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

    def get_mesi_disponibili(self):
        """Ritorna una lista di tuple (anno, mese) analizzando i file salvati."""
        disponibili = []
        if not os.path.exists(self.dir_sale_operatorie):
            return disponibili

        for filename in os.listdir(self.dir_sale_operatorie):
            if filename.endswith(".json") and len(filename) == 12:  # pattern YYYY-MM.json
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
