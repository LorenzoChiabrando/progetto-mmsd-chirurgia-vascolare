"""Parametri del risolutore scelti a ogni pianificazione: limiti, predefiniti, riepilogo.

I limiti stanno in ``asset/config/ottimizzazione.json``; se il file manca o non è valido
si usano i valori di :data:`CONFIGURAZIONE_PREDEFINITA`, gli stessi dell'esempio.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from src.data_paths import PROJECT_ROOT

from .results import SolveResult
from .solver import HighsConfig

_LOGGER = logging.getLogger(__name__)
FILE_CONFIGURAZIONE = PROJECT_ROOT / "asset" / "config" / "ottimizzazione.json"
_SCALA_125 = (1, 2, 5)


@dataclass(frozen=True, slots=True)
class Intervallo:
    """Valori ammessi di un parametro: estremi, predefinito e (facoltativo) passo."""

    minimo: float
    massimo: float
    predefinito: float
    passo: float | None = None

    def __post_init__(self) -> None:
        valori = (self.minimo, self.massimo, self.predefinito)
        if not all(isinstance(v, (int, float)) and math.isfinite(v) for v in valori):
            raise ValueError("minimo, massimo e predefinito devono essere numeri finiti.")
        if not 0 < self.minimo <= self.predefinito <= self.massimo:
            raise ValueError("Serve 0 < minimo <= predefinito <= massimo.")
        if self.passo is not None and not (math.isfinite(self.passo) and self.passo > 0):
            raise ValueError("Il passo deve essere positivo.")


@dataclass(frozen=True, slots=True)
class ParametriPianificazione:
    """Parametri di una pianificazione: limite di tempo (s) e gap relativo (frazione)."""

    limite_tempo_secondi: float
    gap_relativo: float

    def come_config_solver(self) -> HighsConfig:
        return HighsConfig(
            time_limit_seconds=self.limite_tempo_secondi,
            mip_relative_gap=self.gap_relativo,
        )

    def come_dizionario(self) -> dict[str, float]:
        return {
            "limite_tempo_secondi": self.limite_tempo_secondi,
            "gap_relativo": self.gap_relativo,
        }

    @classmethod
    def da_dizionario(cls, dati: Any) -> ParametriPianificazione | None:
        """Parametri salvati con un piano; ``None`` se mancano o non sono validi."""
        try:
            parametri = cls(
                float(dati["limite_tempo_secondi"]), float(dati["gap_relativo"])
            )
            parametri.come_config_solver()  # stessi controlli del risolutore
        except (KeyError, TypeError, ValueError):
            return None
        return parametri


@dataclass(frozen=True, slots=True)
class ConfigurazioneParametri:
    """Limiti dei due slider della finestra di pianificazione."""

    tempo: Intervallo
    gap_percento: Intervallo

    def __post_init__(self) -> None:
        if self.gap_percento.massimo >= 100:
            raise ValueError("Il gap relativo deve restare sotto il 100%.")

    def predefiniti(self) -> ParametriPianificazione:
        return ParametriPianificazione(
            self.tempo.predefinito, self.gap_percento.predefinito / 100
        )

    def valori_tempo(self) -> tuple[float, ...]:
        """Posizioni dello slider del tempo: da minimo a massimo con il passo indicato."""
        passo = self.tempo.passo or max(1.0, (self.tempo.massimo - self.tempo.minimo) / 100)
        valori = []
        valore = self.tempo.minimo
        while valore < self.tempo.massimo - 1e-9:
            valori.append(round(valore, 6))
            valore += passo
        valori.append(self.tempo.massimo)
        return _con_predefinito(valori, self.tempo.predefinito)

    def valori_gap_percento(self) -> tuple[float, ...]:
        """Posizioni dello slider del gap: scala 1-2-5 (0,01 · 0,02 · 0,05 · 0,1 …).

        Con una scala lineare i valori piccoli, i più usati, sarebbero irraggiungibili.
        """
        minimo, massimo = self.gap_percento.minimo, self.gap_percento.massimo
        valori = {minimo, massimo}
        esponente = math.floor(math.log10(minimo))
        while 10 ** esponente <= massimo:
            for fattore in _SCALA_125:
                valore = round(fattore * 10 ** esponente, 10)
                if minimo <= valore <= massimo:
                    valori.add(valore)
            esponente += 1
        return _con_predefinito(sorted(valori), self.gap_percento.predefinito)


def _con_predefinito(valori: list[float], predefinito: float) -> tuple[float, ...]:
    if not any(math.isclose(v, predefinito) for v in valori):
        valori = sorted([*valori, predefinito])
    return tuple(valori)


CONFIGURAZIONE_PREDEFINITA = ConfigurazioneParametri(
    tempo=Intervallo(minimo=10, massimo=1800, predefinito=300, passo=10),
    gap_percento=Intervallo(minimo=0.01, massimo=10, predefinito=0.01),
)


def carica_configurazione(percorso: str | Path = FILE_CONFIGURAZIONE) -> ConfigurazioneParametri:
    """Legge i limiti dal file; se manca o non è valido usa quelli predefiniti."""

    try:
        dati = json.loads(Path(percorso).read_text(encoding="utf-8"))
        tempo = dati["limite_tempo_secondi"]
        gap = dati["gap_relativo_percento"]
        return ConfigurazioneParametri(
            tempo=Intervallo(
                float(tempo["minimo"]), float(tempo["massimo"]), float(tempo["predefinito"]),
                float(tempo["passo"]) if tempo.get("passo") is not None else None,
            ),
            gap_percento=Intervallo(
                float(gap["minimo"]), float(gap["massimo"]), float(gap["predefinito"]),
            ),
        )
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as errore:
        _LOGGER.warning(
            "Configurazione dell'ottimizzazione non valida (%s): uso i valori predefiniti.",
            errore,
        )
        return CONFIGURAZIONE_PREDEFINITA


def riepilogo_risultato(
    risultato: SolveResult, parametri: ParametriPianificazione | None
) -> dict[str, Any]:
    """Esito di una pianificazione da salvare con il piano della settimana.

    Contiene i parametri usati (per riproporli alla pianificazione successiva) e il
    valore della funzione obiettivo con le sue componenti.
    """

    obiettivo = risultato.objective
    return {
        "parametri": parametri.come_dizionario() if parametri is not None else None,
        "esito": risultato.status.value,
        "valore_obiettivo": obiettivo.weighted_total if obiettivo is not None else None,
        "componenti": (
            {
                "efficienza_trattamento": obiettivo.treatment_efficiency,
                "equita_minima": obiettivo.fairness_floor,
                "non_assegnati": obiettivo.unassigned_count,
            }
            if obiettivo is not None else None
        ),
        "gap_ottenuto": risultato.relative_gap,
        "tempo_secondi": round(risultato.elapsed_seconds, 2),
        "interventi": len(risultato.schedule),
        "calcolato_il": datetime.now().isoformat(timespec="seconds"),
    }
