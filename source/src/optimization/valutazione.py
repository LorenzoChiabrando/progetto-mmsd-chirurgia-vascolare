"""Valore della funzione obiettivo di un piano qualsiasi, anche modificato a mano.

È la stessa formula del modello (vedi ``model.objective`` e ``solver._extract_objective``):

    scala · Σ urgenza dei pazienti in lista d'attesa assegnati
    + peso equità · min dei carichi degli specializzandi
    − penalità · interventi senza specializzando

calcolata direttamente sui dati della settimana, senza risolutore: costa millisecondi e
si può ripetere a ogni modifica.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Mapping
from datetime import date
from pathlib import Path
from typing import Any

from .domain import PatientCategory, SchedulingInput
from .exceptions import OptimizationError
from .platform_io import load_platform_context
from .platform_mapping import PlatformPlanningPolicy
from .results import ObjectiveBreakdown, ScheduledSurgery


class PianoNonValutabile(OptimizationError):
    """Il piano contiene qualcosa che il modello non conosce (paziente, sala, specializzando)."""


def obiettivo_del_piano(
    dati: SchedulingInput, piano: Iterable[ScheduledSurgery]
) -> ObjectiveBreakdown:
    """Componenti e totale pesato dell'obiettivo del modello per ``piano``."""

    pazienti = {paziente.patient_id: paziente for paziente in dati.patients}
    carichi = {specializzando.resident_id: 0 for specializzando in dati.residents}
    efficienza = []
    senza_specializzando = 0
    for intervento in piano:
        paziente = pazienti.get(intervento.patient_id)
        if paziente is None:
            raise PianoNonValutabile(
                f"Il paziente {intervento.patient_id} non è tra quelli pianificabili "
                "in questa settimana."
            )
        if paziente.category is PatientCategory.WAITING_LIST:
            efficienza.append(paziente.urgency)
        if intervento.resident_id is None:
            senza_specializzando += 1
            continue
        if intervento.resident_id not in carichi:
            raise PianoNonValutabile(
                f"Lo specializzando {intervento.resident_id} non è tra quelli del modello."
            )
        if paziente.category is not PatientCategory.RESCHEDULED:
            carichi[intervento.resident_id] += 1
    equita = min(carichi.values(), default=0)
    totale_efficienza = math.fsum(efficienza)
    pesi = dati.objective_weights
    return ObjectiveBreakdown(
        treatment_efficiency=totale_efficienza,
        fairness_floor=equita,
        unassigned_count=senza_specializzando,
        weighted_total=(
            dati.efficiency_scale * totale_efficienza
            + pesi.fairness * equita
            - pesi.unassigned_penalty * senza_specializzando
        ),
    )


def piano_da_operazioni(
    operazioni_per_giorno: Mapping[date, Iterable[Mapping[str, Any]]],
    sale: Iterable[str],
) -> tuple[ScheduledSurgery, ...]:
    """Gli interventi salvati nel calendario, nella forma usata dal modello."""

    sale_note = tuple(sale)
    piano = []
    for giorno, operazioni in operazioni_per_giorno.items():
        for operazione in operazioni:
            paziente = str(operazione.get("id_paziente") or "").strip()
            if not paziente:
                continue  # riga senza paziente: non è un intervento
            sala = operazione.get("sala_operatoria")
            if sala not in sale_note:
                raise PianoNonValutabile(f"Sala sconosciuta: {sala!r}.")
            specializzando = str(operazione.get("id_specializzando") or "").strip()
            piano.append(ScheduledSurgery(paziente, sala, giorno, specializzando or None))
    return tuple(piano)


def obiettivo_della_settimana(
    project_root: str | Path,
    lunedi: date,
    operazioni_per_giorno: Mapping[date, Iterable[Mapping[str, Any]]],
    *,
    data_directory: str | Path | None = None,
    policy: PlatformPlanningPolicy | None = None,
) -> ObjectiveBreakdown:
    """Obiettivo del piano della settimana con i dati attuali (pazienti, turni, pesi)."""

    politica = policy or PlatformPlanningPolicy()
    piano = piano_da_operazioni(operazioni_per_giorno, politica.room_ids)
    # I pazienti del piano entrano nei dati qualunque sia il loro stato: in una settimana
    # convalidata non sono più «pianificabili», ma il piano va valutato lo stesso.
    contesto = load_platform_context(
        project_root, lunedi, politica, data_directory=data_directory,
        evaluated_patient_ids=frozenset(intervento.patient_id for intervento in piano),
    )
    return obiettivo_del_piano(contesto.scheduling_input, piano)
