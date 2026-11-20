"""Formato uniforme dei nomi degli specializzandi: COGNOME tutto maiuscolo, Nome con le
iniziali maiuscole, qualunque sia il modo in cui sono stati digitati."""

from __future__ import annotations


def format_surname(value: str) -> str:
    """``"de luca "`` → ``"DE LUCA"``: maiuscolo, spazi superflui tolti."""

    return " ".join(value.split()).upper()


def format_given_name(value: str) -> str:
    """``"MARIA  grazia"`` → ``"Maria Grazia"``.

    Maiuscola anche dopo il trattino e l'apostrofo (``"Anna-Maria"``), il resto in
    minuscolo.
    """

    return " ".join(value.split()).title()
