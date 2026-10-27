# Changelog tecnico

## 2026-10-27

- Aggiunta la demo riproducibile settembre–dicembre con 120 pazienti nella cartella
  `mock_data/scenario_2026_09_12`, conservando i mock precedenti.
- Esteso il generatore con intervallo mensile, numero di pazienti e destinazione
  espliciti. Allineati Previsto, Effettivo, stato pazienti e libretti.
- Aggiunto il controllo della revisione dei dati fra caricamento e scrittura, con
  verifica delle prenotazioni sotto il lock del planner.
- Rifiutate durate discordanti fra dettaglio delle procedure e totale.
- Corretta l'estrazione di soluzioni ammissibili al limite temporale: componenti
  dell'obiettivo, totale, bound e gap ora descrivono lo stesso risultato.
- Aggiunte verifiche del solver con enumerazione indipendente, regressioni del
  planner, cicli di conferma dei calendari e prove GUI con worker HiGHS reale.
- Obiettivo e vincoli matematici invariati. Dettagli e limiti in
  [PLANNER_VERIFICATION.md](PLANNER_VERIFICATION.md).
