# Verifica del planner e demo settembre–dicembre 2026

La demo riproducibile è in `mock_data/scenario_2026_09_12`. È una fotografia sintetica
al 27 ottobre 2026: 120 pazienti, 8 specializzandi, 88 giorni feriali e 100 interventi,
distribuiti in parti uguali sulle due sale. I 37 file della demo precedente restano
inalterati. Il modello matematico e i suoi coefficienti non sono stati modificati.

## Avvio e rigenerazione

```bash
python -m pip install -r requirements-dev.txt
python main.py --data-dir mock_data/scenario_2026_09_12

# Anteprima: nessuna scrittura.
python scripts/reset_demo_data.py --reference-date 2026-10-27 \
  --start-month 2026-09 --end-month 2026-12 --patient-count 120 \
  --data-dir mock_data/scenario_2026_09_12
```

Per rigenerare aggiungere `--write`, ad applicazione chiusa. Il comando conserva una
copia della destinazione precedente in `mock_data/.demo_backups/`. Le stesse opzioni
producono gli stessi 143 file: 140 JSON e 3 CSV. Il test
[`test_bundled_scenario.py`](tests/test_bundled_scenario.py) confronta i file pubblicati
con quelli del generatore.

## Scenari verificati

La verifica finale usa un ambiente separato con Python 3.12.14, PySide6 6.9.3,
Pyomo 6.10.1, HiGHS 1.15.1, pytest 9.1.1 e Ruff 0.16.1. `pip check` non rileva
dipendenze incompatibili. Sono state svolte anche prove preliminari con PySide6 6.10.2.

Esito finale: **455 test superati, 1 saltato, nessun fallimento**, in 42,84 secondi.
Il solo caso saltato riguarda un carattere non rappresentabile in Windows-1252.
Compilazione Python, Ruff e controllo delle dipendenze sono passati. Non restano
test marcati come fallimenti attesi.

| Area | Verifica |
| --- | --- |
| Dati | 38 completati, 62 pianificati, 20 in attesa; ID e riferimenti validi; somma delle durate delle procedure uguale al totale. |
| Calendari | Rotazione di sette ruoli fra otto specializzandi, assenza di doppi incarichi, continuità delle settimane fra mesi. |
| Sale e libretti | Capacità, pause di 11 minuti, assenza di sovrapposizioni, prenotazioni univoche e attività effettive senza duplicati. |
| Ottimizzazione | Tutte le 16 settimane complete dal 7 settembre al 21 dicembre; obiettivo e ammissibilità ricalcolati dalle assegnazioni. |
| Ottimo noto | 32 piccole istanze confrontate con un'enumerazione indipendente delle alternative. |
| Stati del solver | Ottimo, infeasible, annullamento e limite temporale con e senza soluzione ammissibile. I limiti temporali e alcuni errori sono simulati con risposte controllate del backend. |
| Salvataggio | Aggiornamento fra novembre e dicembre, rollback degli errori, conservazione dei periodi convalidati e rifiuto di risultati divenuti obsoleti. |
| GUI | Quattro sezioni, filtri sui 120 pazienti, versioni dei calendari, libretti e worker HiGHS reale con eventi Qt attivi. |

Le prove GUI usano Qt `offscreen`: costruiscono e mostrano le finestre su quel backend,
esercitano il layout e invocano i controller. Non costituiscono una prova manuale su
tutte le combinazioni di display e sistema operativo. Le scritture dei test avvengono
esclusivamente in copie temporanee dei dati.

Lo smoke test eseguibile senza modificare i dati è:

```bash
python -m src.optimization.platform_cli --week 2026-10-26 \
  --data-dir mock_data/scenario_2026_09_12
```

Risultato verificato: stato `optimal`, 26 candidati pianificati, 56 prenotazioni di
altre settimane escluse, obiettivo e bound pari a 2828, gap zero e `written: false`.
Il Previsto della settimana è già convalidato: questo comando è solo una verifica
in memoria e non autorizza a sostituirlo.

Per rieseguire i controlli:

```bash
python -m compileall src tests scripts
python -m pytest
python -m ruff check .
```

Le dipendenze sono fissate in `requirements.txt` e `requirements-dev.txt`. Ruff controlla
script, test e moduli del planner modificati; la sua configurazione non richiede una
riscrittura dei file GUI preesistenti.

## Problemi corretti durante la verifica

- **Dati modificati durante il calcolo.** Il caricamento confronta un'impronta dei JSON
  prima e dopo la lettura. Il piano conserva quell'impronta e il writer la ricontrolla
  sotto il proprio lock. Una variazione richiede di ripetere la pianificazione.
  Dopo una scrittura riuscita, il servizio restituisce la revisione appena salvata,
  consentendo modifiche successive senza riutilizzare una revisione obsoleta.
- **Prenotazioni concorrenti.** Prima di scrivere vengono ricontrollati pazienti,
  prenotazioni delle altre settimane ed Effettivi già inizializzati. Il controllo
  comprende i vecchi slot JSON oltre all'elenco `operazioni`.
- **Durate incoerenti.** Quando è presente un dettaglio delle procedure, ogni durata
  deve essere un intero positivo e la somma deve coincidere con `durata_intervento`.
  I record legacy privi del dettaglio continuano a usare il totale.
- **Soluzioni al limite temporale.** Il solver verifica valori, integralità e vincoli
  prima dell'estrazione. Equità, interventi senza specializzando e obiettivo vengono
  ricalcolati dal risultato. Valori ammissibili non stretti delle variabili ausiliarie
  non causano più un rifiuto o un totale incoerente. Un bound incompatibile con il
  risultato viene dichiarato indisponibile, insieme al gap.

Questi controlli conservano il comportamento del modello; non aggiungono vincoli o
criteri clinici. I test di regressione derivati dal precedente checkout sono stati
adattati ai messaggi italiani e al controllo delle durate, mantenendo le verifiche
sul comportamento.

## Limiti del caso dimostrativo

Novembre e dicembre hanno lo scadenzario Previsto in bozza: va convalidato prima di
usare il planner. Per una settimana fra due mesi, entrambi devono essere convalidati.
Le prove del solver effettuano questa preparazione su copie temporanee.

Il periodo contiene soltanto settembre–dicembre. Il 31 agosto e il 1 gennaio non sono
generati implicitamente; le due settimane estreme incomplete non sono scenari di solve
pronti. Anche nelle settimane storiche, il dry-run usa lo stato corrente della lista
d'attesa: non ricostruisce la lista storica e non sostituisce un piano convalidato.

Il calendario applicativo considera feriali tutti i giorni da lunedì a venerdì,
comprese le festività infrasettimanali. La matrice di qualifica del modello impone
l'assegnazione quando lo specializzando di turno è compatibile, ma non introduce un
divieto generale per le altre compatibilità. La demo precaricata rispetta comunque la
matrice. Modificare questa regola richiederebbe una decisione sulla formulazione.

Il lock coordina le scritture del planner. Il controllo dell'impronta intercetta
modifiche intervenute durante il calcolo, ma non trasforma i JSON in un database con
transazioni fra processi arbitrari. Va mantenuto il normale uso con una sola istanza
dell'applicazione, senza editor esterni che scrivano durante il salvataggio.
