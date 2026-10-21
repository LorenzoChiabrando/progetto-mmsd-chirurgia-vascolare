"""Errori non gestiti: registrati nel log e mostrati all'utente invece di perdersi.

Senza questo hook un'eccezione sollevata in uno slot Qt viene solo stampata sul
terminale e l'azione si interrompe senza alcun avviso.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable
from pathlib import Path
from types import TracebackType

from PySide6.QtWidgets import QApplication

from src.error_messages import describe_error
from src.views.components import messages

_LOGGER = logging.getLogger(__name__)

ExceptHook = Callable[[type[BaseException], BaseException, TracebackType | None], object]

TITLE = "Errore imprevisto"
GENERIC_MESSAGE = "Si è verificato un errore imprevisto: l'operazione non è stata completata."


def _has_user_message(error: BaseException) -> bool:
    """Vero se il testo dell'errore è pensato per l'utente (di sistema o dell'app).

    I messaggi delle eccezioni di Python (``KeyError``, ``AttributeError``...) sono in
    inglese e tecnici: restano solo nel log.
    """

    return isinstance(error, OSError) or type(error).__module__.startswith("src.")


class UnexpectedErrorHandler:
    """``sys.excepthook`` dell'applicazione: registra l'errore e lo mostra in un dialog.

    Args:
        log_file: file di log da indicare all'utente; ``None`` se il log su file non è attivo.
        fallback: hook precedente, usato per Ctrl+C e quando non c'è una ``QApplication``.

    Gli errori sollevati mentre il dialog è aperto vengono solo registrati, per non
    aprire dialog a catena.
    """

    def __init__(self, log_file: Path | None, fallback: ExceptHook) -> None:
        self._log_file = log_file
        self._fallback = fallback
        self._showing = False

    def __call__(
        self,
        kind: type[BaseException],
        error: BaseException,
        traceback: TracebackType | None,
    ) -> None:
        if issubclass(kind, KeyboardInterrupt) or QApplication.instance() is None:
            self._fallback(kind, error, traceback)
            return
        _LOGGER.error("Errore non gestito", exc_info=(kind, error, traceback))
        if self._showing:
            return
        self._showing = True
        try:
            messages.show_message(
                QApplication.activeWindow(),
                TITLE,
                self.message_for(error),
                section="generale",
                kind="error",
            )
        except Exception:
            # Boundary applicativo: un dialog che non si apre non deve nascondere l'errore.
            _LOGGER.exception("Impossibile mostrare il dialog di errore")
        finally:
            self._showing = False

    def message_for(self, error: BaseException) -> str:
        """Testo del dialog: frase generica, dettaglio se leggibile, posizione del log."""

        parts = [GENERIC_MESSAGE]
        if _has_user_message(error):
            parts.append(describe_error(error))
        if self._log_file is not None:
            parts.append(f"I dettagli tecnici sono nel file:\n{self._log_file}")
        return "\n\n".join(parts)


def install_exception_hook(log_file: Path | None) -> UnexpectedErrorHandler:
    """Sostituisce ``sys.excepthook``; l'hook precedente resta come ripiego."""

    handler = UnexpectedErrorHandler(log_file, sys.excepthook)
    sys.excepthook = handler
    return handler
