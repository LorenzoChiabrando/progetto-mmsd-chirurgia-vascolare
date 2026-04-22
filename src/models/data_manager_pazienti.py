import os
import json
from datetime import datetime

class DataManagerPazienti:
    def __init__(self, dir_pazienti="mock_data/pazienti"):
        self.dir_pazienti = dir_pazienti
        
        if not os.path.exists(self.dir_pazienti):
            os.makedirs(self.dir_pazienti, exist_ok=True)

    def get_tutti_pazienti(self):
        """Legge tutti i file JSON presenti nella cartella pazienti"""
        pazienti = []
        for filename in os.listdir(self.dir_pazienti):
            if filename.endswith(".json"):
                filepath = os.path.join(self.dir_pazienti, filename)
                with open(filepath, 'r', encoding='utf-8') as f:
                    try:
                        data = json.load(f)
                        pazienti.append(data)
                    except json.JSONDecodeError:
                        pass 
        
        return sorted(pazienti, key=lambda x: x.get('cognome', ''))

    def crea_nuovo_paziente(self, dati_form):
        """Salva il nuovo paziente in un file JSON dedicato"""
        file_esistenti = [f for f in os.listdir(self.dir_pazienti) if f.endswith(".json")]
        nuovo_id = f"PZ{len(file_esistenti) + 1:04d}"
        
        data_odierna = datetime.now().strftime("%d/%m/%Y")

        nuovo_paziente = {
            "id": nuovo_id,
            "nome": dati_form["nome"],
            "cognome": dati_form["cognome"],
            "diagnosi": dati_form.get("diagnosi", ""),
            "codice_intervento": dati_form.get("codice_intervento", ""),
            "descrizione_intervento": dati_form.get("descrizione_intervento", ""),
            "tipo_chirurgia": dati_form.get("tipo_chirurgia", ""),
            "complessita": dati_form.get("complessita", ""),
            "urgenza": dati_form["urgenza"],
            "stato": dati_form.get("stato", "In Attesa"),
            "data_inserimento": data_odierna,
            "note": dati_form.get("note", ""),
        }

        filepath = os.path.join(self.dir_pazienti, f"{nuovo_id}.json")
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(nuovo_paziente, f, indent=4)
            
        return nuovo_paziente

    def get_pazienti_in_attesa(self):
        """
        Restituisce i pazienti con stato 'In Attesa', ordinati per urgenza
        (Alta → Media → Bassa) e poi per cognome.
        """
        ordine_urgenza = {"Alta": 0, "Media": 1, "Bassa": 2}
        pazienti = [
            p for p in self.get_tutti_pazienti()
            if p.get("stato") == "In Attesa"
        ]
        pazienti.sort(key=lambda p: (
            ordine_urgenza.get(p.get("urgenza", "Bassa"), 2),
            p.get("cognome", ""),
        ))
        return pazienti

    def get_paziente_by_id(self, paziente_id):
        filepath = os.path.join(self.dir_pazienti, f"{paziente_id}.json")
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return None

    def aggiorna_paziente(self, paz_id, dati):
        filepath = os.path.join(self.dir_pazienti, f"{paz_id}.json")
        if not os.path.exists(filepath):
            return None
        with open(filepath, 'r', encoding='utf-8') as f:
            paz = json.load(f)
        paz.update({
            "nome": dati["nome"],
            "cognome": dati["cognome"],
            "diagnosi": dati.get("diagnosi", paz.get("diagnosi", "")),
            "codice_intervento": dati.get("codice_intervento", paz.get("codice_intervento", "")),
            "descrizione_intervento": dati.get("descrizione_intervento", paz.get("descrizione_intervento", "")),
            "tipo_chirurgia": dati.get("tipo_chirurgia", paz.get("tipo_chirurgia", "")),
            "complessita": dati.get("complessita", paz.get("complessita", "")),
            "urgenza": dati["urgenza"],
            "stato": dati.get("stato", paz.get("stato", "In Attesa")),
            "note": dati.get("note", paz.get("note", "")),
        })
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(paz, f, indent=4)
        return paz

    def elimina_paziente(self, paz_id):
        filepath = os.path.join(self.dir_pazienti, f"{paz_id}.json")
        if os.path.exists(filepath):
            os.remove(filepath)
            return True
        return False
