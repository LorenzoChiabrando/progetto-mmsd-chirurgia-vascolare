"""Descrizioni in italiano degli errori di sistema mostrati all'utente."""

from __future__ import annotations

import errno

_OS_ERROR_DESCRIPTIONS = {
    errno.EACCES: "Permesso negato",
    errno.EPERM: "Operazione non consentita",
    errno.ENOENT: "Il file o la cartella non esiste",
    errno.ENOSPC: "Spazio su disco esaurito",
    errno.EROFS: "Il disco è in sola lettura",
    errno.EISDIR: "Il percorso indicato è una cartella",
    errno.ENOTDIR: "Una parte del percorso non è una cartella",
    errno.EEXIST: "Il file esiste già",
    errno.ENAMETOOLONG: "Il nome del file è troppo lungo",
    errno.EBUSY: "Il file è in uso da un altro programma",
}


def describe_os_error(error: OSError) -> str:
    """Restituisce una descrizione italiana di ``error``, con il percorso se noto.

    Il testo di sistema (``strerror``) dipende dalla lingua del sistema operativo;
    per i casi non previsti si usa un messaggio generico con il codice di errore.
    """

    description = _OS_ERROR_DESCRIPTIONS.get(error.errno)
    if description is None:
        code = f" (codice {error.errno})" if error.errno is not None else ""
        description = f"Errore di sistema{code}"
    return f"{description}: {error.filename}" if error.filename else description


def describe_error(error: BaseException) -> str:
    """Testo da mostrare per ``error``: traduce gli errori di sistema, il resto è già italiano."""

    return describe_os_error(error) if isinstance(error, OSError) else str(error)
