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
        lun_str = lun_date.strftime("%Y-%m-%d")
        anno, mese = lun_date.year, lun_date.month
        data = self.load_mese(anno, mese)
        if "settimane" not in data["metadata"]:
            data["metadata"]["settimane"] = {}
        data["metadata"]["settimane"][lun_str] = stato
        self.save_mese(anno, mese, data)

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
        ids = set()
        exclude_str = exclude_lun_date.strftime("%Y-%m-%d") if exclude_lun_date else None
        if not os.path.exists(self.dir_sale_operatorie):
            return ids

        for filename in os.listdir(self.dir_sale_operatorie):
            if not (filename.endswith(".json") and len(filename) == 12):
                continue
            try:
                anno = int(filename[0:4])
                mese = int(filename[5:7])
            except ValueError:
                continue

            data = self.load_mese(anno, mese)
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
                    lun_data = self.load_mese(lun.year, lun.month)
                    stato_sett = lun_data.get("metadata", {}).get("settimane", {}).get(lun_str, "BOZZA")
                if stato_sett == "CONVALIDATO":
                    continue
                if exclude_str and lun_str == exclude_str:
                    continue
                for op in turno.get("operazioni", []):
                    if op.get("id_paziente"):
                        ids.add(op["id_paziente"])
                for key, val in turno.items():
                    if key not in ("operazioni", "specializzandi") and isinstance(val, dict) and val.get("id_paziente"):
                        ids.add(val["id_paziente"])

        return ids

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
