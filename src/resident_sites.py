"""Sede di assegnazione degli specializzandi: le strutture convenzionate, l'estero, lo storico.

Lo ``stato`` del libretto (``Molinette``, ``Altra Sede``, ``Storico``) resta quello usato da
Scadenzario e pianificazione: si ricava dalla sede (:func:`stato_da_sede`). La sede
precisa sta nel campo ``sede``; per l'estero il testo libero ``sede_estero`` si vede solo
nella scheda dello specializzando.
"""

from __future__ import annotations

from collections.abc import Mapping

MOLINETTE = "Ospedale Molinette (Torino)"
ESTERO = "Estero"
STORICO = "Storico"

STRUTTURE_CONVENZIONATE: tuple[tuple[str, str], ...] = (
    (MOLINETTE, "Molinette"),
    ("Ospedale Mauriziano (Torino)", "Mauriziano"),
    ("Ospedale San Giovanni Bosco (Torino)", "S. Giovanni Bosco"),
    ("Ospedale Santa Croce e Carle (Cuneo)", "S. Croce e Carle"),
    ("Ospedale Maggiore della Carità (Novara)", "Maggiore della Carità"),
    ("Ospedale degli Infermi (Biella)", "Degli Infermi"),
    ("Ospedale SS. Antonio e Biagio e Cesare Arrigo (Alessandria)", "SS. Antonio e Biagio"),
    ("Ospedale Umberto Parini (Aosta)", "Umberto Parini"),
    ("ASL AT (Asti)", "ASL AT"),
)
"""Strutture italiane convenzionate: nome completo e nome breve per l'elenco."""

SEDI: tuple[str, ...] = (*(nome for nome, _breve in STRUTTURE_CONVENZIONATE), ESTERO, STORICO)
"""Scelte del menu «Sede attuale», nell'ordine."""

_BREVI = dict(STRUTTURE_CONVENZIONATE)


def stato_da_sede(sede: str) -> str:
    """Stato del libretto per la sede: Molinette, Storico o Altra Sede."""
    if sede == MOLINETTE:
        return "Molinette"
    if sede == STORICO:
        return "Storico"
    return "Altra Sede"


def sede_di(spec: Mapping[str, object]) -> str:
    """Sede dello specializzando; per i libretti senza ``sede`` la ricava dallo stato.

    Un vecchio «Altra Sede» senza struttura restituisce stringa vuota (da specificare).
    """
    sede = str(spec.get("sede") or "")
    if sede:
        return sede
    stato = spec.get("stato")
    if stato == "Molinette":
        return MOLINETTE
    if stato == "Storico":
        return STORICO
    return ""


def etichetta_sede(spec: Mapping[str, object]) -> str:
    """Nome breve per l'elenco: la struttura, «Estero», «Storico» o «Altra Sede»."""
    sede = sede_di(spec)
    if not sede:
        return str(spec.get("stato") or "Altra Sede")
    return _BREVI.get(sede, sede)


def descrizione_sede(spec: Mapping[str, object]) -> str:
    """Sede per la scheda dello specializzando, con il dettaglio dell'estero."""
    sede = sede_di(spec)
    if sede == ESTERO:
        dettaglio = str(spec.get("sede_estero") or "").strip()
        return f"{ESTERO} · {dettaglio}" if dettaglio else ESTERO
    return sede or str(spec.get("stato") or "N/D")
