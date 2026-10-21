# MMSD CV — Chirurgia Vascolare

Applicazione desktop per la gestione dei medici specializzandi in Chirurgia Vascolare (UNITO):
scadenzario dei turni, libretti, lista pazienti e pianificazione delle sale operatorie.

Development environment branch. Contains the application source code and the scripts to run it
locally.

## Repository structure

```
main.py            entry point
requirements.txt   Python dependencies
src/               controllers, models, views, optimization (Pyomo + HiGHS)
asset/             styles and images
mock_data/         JSON data files
scripts/
  run.sh             launch in dev mode (Linux / macOS)
  run.bat            launch in dev mode (Windows)
  reset_demo_data.py regenerate the synthetic demo data
```

## Requirements

You need Python 3.10 or higher and pip, which comes bundled with Python by default.

On Ubuntu / Debian, make sure `python3-venv` is available:
```bash
sudo apt install python3-venv
```

On Windows, download Python from [python.org](https://www.python.org/downloads/) and check **"Add Python to PATH"** during installation. `venv` is already included.

## Quick start

The `scripts/` folder contains launchers that take care of everything automatically. The first time you run them, they set up the virtual environment and install the dependencies. From the second run onwards, they just start the application.

### Linux / macOS

Make the script executable once:
```bash
chmod +x scripts/run.sh
```

Then run it:
```bash
bash scripts/run.sh
```

The first time you will see the installation progress in the terminal. The application opens automatically when it finishes.

### Windows

Open the project folder in File Explorer and double-click `scripts\run.bat`. A terminal window will appear showing the installation progress. The application opens automatically when it finishes.

If Windows shows a security warning, click **"Run anyway"**.

## Manual setup (development)

**Linux / macOS**
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**Windows (PowerShell)**

If script execution is blocked, run this once:
```powershell
Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
```

Then:
```powershell
python -m venv venv
venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

**Windows (Command Prompt)**
```cmd
python -m venv venv
venv\Scripts\activate.bat
pip install -r requirements.txt
```

## Daily use

Activate the virtual environment, then start the application.

**Linux / macOS**
```bash
source venv/bin/activate
python3 main.py
```

**Windows (PowerShell)**
```powershell
venv\Scripts\Activate.ps1
python main.py
```

**Windows (Command Prompt)**
```cmd
venv\Scripts\activate.bat
python main.py
```

When the environment is active, the prompt shows the `(venv)` prefix.

## Deactivate the virtual environment

```bash
deactivate
```

Works on all platforms. The `venv/` folder can be deleted and recreated at any time by repeating the setup steps.

## Calendari, PDF e importazione pazienti

Lo Scadenziario mantiene nei JSON le chiavi legacy `Reparto I` e `Reparto II`, ma le mostra
come **I Reperibilità** e **II Reperibilità**. I pulsanti **Dettaglio** e **Intero mese**
permettono rispettivamente di scorrere celle ampie o di adattare tutti i giorni alla finestra.
Lo Scadenziario offre due viste dello stesso mese: **Per attività** (una riga per ruolo, con
Dettaglio e Intero mese; un click sulla cella apre l'assegnazione) e **Per specializzando** (una
riga per persona, con il totale dei turni nella prima colonna e la sigla del ruolo di ogni
giorno — R1, R2, S1, S2, GV, DH, DS; sola consultazione). In entrambe Dettaglio mostra colonne
larghe e scorrevoli, Intero mese tutto il mese in una schermata. Entrambe leggono lo stesso dato (`RosterMonth`), che
alimenta anche l'export PDF. La legenda dei tipi di guardia (118, PI, L) è nella riga degli
strumenti: il tooltip di ogni codice ne riporta la descrizione. Le Sale operatorie offrono un
riepilogo mensile in sola lettura, mentre gli spostamenti e la pianificazione restano disponibili
nella vista settimanale.

Le assegnazioni dello Scadenziario si modificano da un dialog modale, aperto con un click su
una cella modificabile (giorno feriale, mese non convalidato, modalità Corrente o
Pianificazione; nello Storico solo l'Effettivo). Il dialog degli specializzandi permette la ricerca per nome e mostra in grigio,
con il motivo, chi ha già un altro incarico nella giornata o nella settimana del giro visite;
la riga Tipo Guardia propone 118, PI e L con i colori della legenda. Entrambi permettono di
rimuovere l'assegnazione corrente.

Il giro visite ha una cella per ciascun giorno lavorativo. Le cinque celle condividono
l'assegnazione della settimana: la prima scelta riempie tutte le celle, mentre sostituzione
e cancellazione richiedono conferma. Il controllo dei conflitti considera tutti i giorni da
lunedì a venerdì, anche a cavallo di due mesi. Una settimana che comprende un mese convalidato
mantiene l'assegnazione già confermata. Nei libretti il riepilogo di orario e sede è in sola
lettura; la conferma delle singole attività resta disponibile, tranne per gli interventi
chirurgici, che si registrano con la convalida dell'Effettivo delle sale operatorie. Le sale
operatorie mostrano i codici degli interventi e conservano l'ID paziente nei dati, senza
visualizzarlo nelle schede. Se la colonna è stretta i codici restano interi e quelli che non
entrano sono contati (`+1`); la durata, già leggibile dall'orario, compare solo se c'è spazio.
Il dettaglio completo si apre facendo clic sulla scheda.

### Previsto ed Effettivo

Scadenzario e Sale operatorie hanno due versioni dello stesso calendario, scelte senza cambiare
periodo né vista dal menu **Calendario** nello Scadenzario e **Versione** nelle Sale operatorie:

- **Previsto** è il piano. I file restano in `scadenzario/AAAA-MM.json` e
  `sale_operatorie/AAAA-MM.json`: i dati esistenti sono già il Previsto, senza migrazione.
- **Effettivo** registra ciò che è avvenuto, in `scadenzario/effettivo/` e
  `sale_operatorie/effettivo/`. È una copia del Previsto convalidato: la convalida del mese
  (Scadenzario) o della settimana (Sale) la crea automaticamente; per i periodi convalidati
  prima di questa funzione c'è il pulsante **Crea Effettivo dal Previsto**. La copia si
  corregge senza toccare il Previsto, anche dallo Storico. Leggere un Effettivo mancante non
  crea file.
- Lo **Storico** contiene solo i periodi con il Previsto convalidato: i mesi nello Scadenzario,
  le settimane nelle Sale. Un periodo passato rimasto in bozza non compare e le frecce lo
  saltano. Lì il Previsto è in sola lettura; l'Effettivo si corregge finché non viene
  convalidato.
- Sala Op. I e II si sincronizzano con le Sale operatorie della stessa versione. Nell'Effettivo
  una settimana delle Sale non ancora creata non viene toccata, e una modifica che contraddice
  gli interventi già assegnati in quella sala viene rifiutata.
- Solo la convalida dell'**Effettivo** di una settimana delle Sale segna i pazienti come
  Completati e registra gli interventi nei libretti. La convalida del Previsto congela il piano.
- Il planner pianifica solo il Previsto e legge lo scadenzario Previsto; le prenotazioni dei
  pazienti tengono conto delle settimane Effettivo già create.
- PDF, badge, titoli dei dialog e nomi dei file esportati indicano la versione.

Il comando **Esporta PDF** crea un documento da stampa per l'intero mese o una singola
settimana su un foglio A4 orizzontale, con un giorno per colonna come a schermo. La tabella
occupa tutto il foglio e sabati e domeniche sono colonne strette. I nomi non vengono mai
tagliati: nel mese compaiono come cognome e iniziale su due righe, nella settimana per esteso;
il carattere è il più grande con cui tutti entrano nella colonna e un nome molto lungo viene al
più compresso in larghezza. I colori sono fissi, quindi il PDF è uguale anche con un tema scuro
del desktop. Se le righe non entrano in una pagina proseguono nella successiva con
l'intestazione ripetuta e il numero di pagina. La generazione usa Qt e non richiede dipendenze
aggiuntive.

L'inserimento multiplo riconosce sia i template nativi sia i CSV TrackCare, inclusi separatore
`;`, BOM, codifica UTF-8/Windows-1252 e intestazioni accentate o degradate come `Priorit�`
e `Prioritï¿½`. Il mapping è implementato in [`patient_csv.py`](src/importers/patient_csv.py):

| Campo applicativo | Colonna TrackCare | Trattamento |
| --- | --- | --- |
| `nome` | `Nome` | Obbligatorio. |
| `cognome` | `Cognome` | Obbligatorio. |
| `codice_diagnosi`, `descrizione_diagnosi` | `Diagnosi ICD9` | Separa il codice finale fra parentesi; un valore composto dal solo codice va nel campo codice. |
| `codice_intervento` | `codice intervento` | Mantiene codici e posizioni anche per più interventi. |
| `descrizione_intervento` | `Intervento/procedura ICD9` | Separa le procedure con `;` e ricava gli eventuali codici finali mancanti. |
| `tipo_chirurgia` | Assente | `Da classificare`; campo descrittivo, non richiesto dal solver. |
| `complessita` | Assente | `Da classificare`; da completare prima della pianificazione. |
| `urgenza` | `Priorità`, `urgenza` e varianti di codifica | A → Alta, B → Media, C/D → Bassa; valori assenti o sconosciuti → `Da classificare`, con avviso. |
| `durata_intervento` | Opzionale: `durata`, `durata_minuti`, `durata_intervento` | Minuti interi positivi; se assente propone 90 minuti e mostra un avviso. |

Il file originale non viene copiato nel repository.

Anche **Aggiungi Paziente** usa i dati disponibili nel CSV: nome, cognome, diagnosi,
codice/descrizione dell'intervento e priorità. Solo nome e cognome sono obbligatori,
come nel bulk. La diagnosi può essere descrittiva, contenere il codice fra parentesi
o essere composta dal solo codice; il campo codice separato resta facoltativo.

**Mostra dati aggiuntivi (facoltativi)** permette di impostare durata, tipo chirurgia,
complessità, stato e note. Tipo chirurgia, complessità e urgenza non specificati restano
`Da classificare`, senza attribuire automaticamente una classe clinica. La durata iniziale
è una stima di 90 minuti totali, ripartita fra le procedure e segnalata nel modulo.
La scheda nasce `In Attesa`. Quando la si riapre in modifica, i dati aggiuntivi sono visibili
e mantengono i valori salvati. Per il planner restano necessari i dati richiesti dal modello,
fra cui complessità e limite di attesa per i pazienti `I'`.

L'anteprima permette di digitare la durata totale. Se il CSV contiene più durate (`60;90`),
le conserva separatamente; una modifica del totale lo ripartisce fra le procedure, mantenendo
la somma esatta. Righe con nomi mancanti o durate non valide bloccano l'importazione fino alla
correzione. Un caricamento fallito svuota la precedente anteprima. I pazienti importati con
urgenza da classificare restano visibili in lista e hanno `attesa_massima_giorni: null`.
Modificando l'urgenza nella scheda, il data manager aggiorna l'attesa standard a 30, 60 o 180
giorni; conserva un eventuale limite personalizzato già presente.

Il paziente conserva separatamente `codice_diagnosi` e `descrizione_diagnosi`, mantenendo anche
il campo legacy `diagnosi` per compatibilità. **Data inserimento** e **Data intervento** sono
visualizzate separatamente: lo stato `Pianificato` viene derivato esclusivamente da un
collegamento esplicito tramite `id_paziente` in una bozza delle sale operatorie.

## Dati demo aggiornati

[`reset_demo_data.py`](scripts/reset_demo_data.py) genera 20 pazienti sintetici, 8 specializzandi,
tre mesi di calendari (precedente, corrente e successivo) e tre CSV di prova. Include attività
completate nella settimana precedente, operazioni pianificate vicine alla data di riferimento
e pazienti in attesa. Gli scadenzari corrente e futuro sono in bozza, così possono essere
modificati e poi convalidati prima di usare il planner.

I turni ruotano ogni settimana: sette ruoli (Reparto I e II, Sala Op. I e II, Giro Visite,
Day Hospital, Day Surgery) per otto specializzandi, quindi ogni settimana tutti scalano di un
ruolo e uno resta libero. Le settimane si contano da un lunedì fisso, così la rotazione
prosegue tra mesi e anni. Sale operatorie, interventi e libretti seguono gli stessi turni:
OR I e OR II sono Sala Op. I e II del giorno e gli interventi completati compaiono nel
libretto di chi era in sala.

Le anagrafiche sintetiche riprendono i nomi della demo precedente, fra cui Pippo VerdeScuro,
Mandringo Bello, Spirulina Alga e BAZZ JAZZ. Pino Silvestre completa il posto mancante
nell'anagrafica degli specializzandi. Questi nomi sono inclusi nel generatore, così un nuovo
reset non li sostituisce con etichette numerate. ID, riferimenti e date sono indipendenti dai nomi.

A programma chiuso, dalla radice del progetto:

```bash
venv/bin/python3 scripts/reset_demo_data.py --reference-date 2026-09-08
venv/bin/python3 scripts/reset_demo_data.py --reference-date 2026-09-08 --write
```

L'applicazione usa la data reale per il mese corrente e per la pianificazione, quindi i dati
vanno rigenerati a ridosso della demo, con quel giorno come data di riferimento (ad esempio
il giorno prima dell'esame).

Senza `--reference-date`, lo script usa la data odierna. La prima riga mostra soltanto
un'anteprima; `--write` sostituisce `mock_data` e sposta i dati precedenti in
`.demo_backups/<data>-<identificativo>/`, esclusa da Git. Per ripristinarli, chiudere
l'applicazione, conservare a parte la cartella `mock_data` corrente e rimettere il backup
al suo posto. Il reset è un comando manuale e non viene eseguito all'avvio dell'applicazione.

## Salvataggi, file danneggiati e log

- I file JSON si salvano su un file temporaneo che sostituisce l'originale solo a scrittura
  completata: un salvataggio interrotto lascia intatta la versione precedente.
- Un file danneggiato non viene mai letto come vuoto, quindi non viene sovrascritto. Se è il
  mese corrente dello scadenzario o delle sale operatorie, l'avvio si ferma con un messaggio
  che indica il file; se è un altro mese, lo scadenzario resta sul mese di partenza. Libretti e
  schede paziente danneggiati vengono saltati e segnalati nel log.
- Gli errori imprevisti compaiono in un dialog e vengono registrati in `logs/mmsd-cv.log`
  (a rotazione, 1 MB per 3 file, esclusa da Git). Il log contiene traceback e nomi dei file,
  non il contenuto dei dati.
- Per recuperare un file danneggiato: rimettere la copia da `.demo_backups/` oppure rigenerare i
  dati con `reset_demo_data.py --write` (vedi sopra).
- L'eseguibile (PyInstaller) non scrive accanto a sé: al primo avvio copia i dati demo inclusi in
  `~/.local/share/ScadenzarioCV/v2/dati` (Windows: `%APPDATA%\ScadenzarioCV\v2\dati`, macOS:
  `~/Library/Application Support/ScadenzarioCV/v2/dati`) e da lì in poi usa quella cartella; i log
  vanno in `.../ScadenzarioCV/v2/logs`. Per ripartire dai dati demo basta cancellare `dati`.
  `--data-dir` e `MMSD_DATA_DIR` restano validi anche per l'eseguibile.

## Ottimizzazione Pyomo + HiGHS

Il repository include ora un layer indipendente dalla GUI che implementa il MILP settimanale
per la selezione dei pazienti e l'assegnazione degli specializzandi descritta nel paper di
riferimento. Nel codice rimane il nome inglese `Resident`, usato dal paper, ma indica sempre uno
specializzando. Con *roster* si intende la turnazione giornaliera `Sala Op. I`/`Sala Op. II`.
Il costruttore scientifico riproduce letteralmente le equazioni stampate; changeover e turnazione
giornaliera sono estensioni applicative separate. La formulazione è implementata in
[`model.py`](src/optimization/model.py); i controlli sui dati sono in
[`validation.py`](src/optimization/validation.py).

`highspy` distribuisce i binding e la libreria HiGHS: non è necessario installare un eseguibile
separato con Homebrew. Usa Python 3.10 o superiore:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

Verifica che il solver sia disponibile ed esegui l'istanza sintetica:

```bash
python -c "from src.optimization import HighsSolver; assert HighsSolver.is_available()"
python -m src.optimization.example
```

### Pianificazione dai dati della piattaforma

Il planner può leggere i JSON applicativi reali, risolvere una settimana dal lunedì al venerdì
su due sale fisiche (`OR-1` e `OR-2`) e produrre lo stesso formato letto dalla schermata delle
sale operatorie. `Sala Op. I` alimenta il roster di `OR-1`, mentre `Sala Op. II` alimenta quello
di `OR-2`; le due sale hanno capacità e sequenze orarie indipendenti. Lo scadenzario del
mese deve essere prima completato e `CONVALIDATO`: la convalida è rifiutata finché manca
l'assegnazione di `Sala Op. I` o `Sala Op. II` in almeno un giorno lavorativo, oppure se la stessa
persona copre entrambe. Se la settimana è a cavallo di due mesi, devono essere convalidati
entrambi gli scadenzari mensili.

I JSON usano il blocco versionato `modello_ottimizzazione` per rappresentare le categorie
`I'`/`I''`/`I'''`, l'attesa massima, le compatibilità paziente-specializzando e le capacità
sala-giorno. Le qualifiche per complessità sono invece inferite dal `livello`
`Junior`/`Intermediate`/`Senior`
del libretto.

Il flusso ordinario è disponibile direttamente nella GUI:

1. compilare e convalidare lo scadenzario mensile;
2. aprire **Sale Operatorie → Pianificazione** e selezionare la settimana;
3. premere **Pianifica settimana**;
4. attendere il messaggio conclusivo oppure usare **Annulla pianificazione**.

Pyomo costruisce il modello e `highspy` esegue HiGHS in un worker separato, quindi la finestra
non viene bloccata. Durante il calcolo sono sospesi navigazione e modifica del piano. La
cancellazione è cooperativa e non salva risultati parziali. Se HiGHS restituisce una soluzione
ammissibile, il servizio la valida, aggiorna atomicamente i JSON delle sale operatorie, invalida
la cache applicativa e ricarica subito la tabella. La rigenerazione di una bozza esistente
richiede una conferma esplicita; settimane o mesi delle sale operatorie già `CONVALIDATO` non
sono mai sovrascritti.

Lo stesso flusso resta disponibile dalla CLI, utile per sviluppo e diagnostica. Per eseguire un
dry-run, che non modifica alcun file:

```bash
python -m src.optimization.platform_cli --week 2026-09-14 --project-root .
```

La scrittura è esplicita. `--overwrite` è necessario se la settimana in stato `BOZZA` contiene
già operazioni; una settimana o un mese `CONVALIDATO` viene sempre rifiutato:

```bash
python -m src.optimization.platform_cli \
  --week 2026-09-14 \
  --project-root . \
  --write \
  --overwrite
```

Il comando risolve e valida tutto in memoria prima della persistenza, crea un backup privato e
sostituisce atomicamente soltanto i cinque giorni interessati. L'output del comando contiene
solo conteggi e diagnostica aggregata, non dati clinici. Le regole di mapping adottate sono
implementate in [`platform_mapping.py`](src/optimization/platform_mapping.py).
