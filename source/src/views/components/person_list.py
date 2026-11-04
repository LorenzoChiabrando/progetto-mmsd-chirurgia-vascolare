"""Elemento degli elenchi di persone, uguale in Libretto Carriere e Lista Pazienti."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QListWidgetItem, QVBoxLayout

ALTEZZA_ELEMENTO = 70
_LATO_AVATAR = 42


def iniziali(cognome: str, nome: str) -> str:
    """«ALGA», «Spirulina» -> «AS»; con un solo nome, le sue prime due lettere."""

    parti = [p for p in (cognome.strip(), nome.strip()) if p]
    if len(parti) == 2:
        return (parti[0][0] + parti[1][0]).upper()
    return parti[0][:2].upper() if parti else "–"


def pillola(testo: str, sfondo: str, colore: str) -> QLabel:
    """Etichetta colorata larga quanto il suo testo (mai tagliata)."""

    etichetta = QLabel(testo or "–")
    etichetta.setObjectName("PillolaElenco")
    etichetta.setAlignment(Qt.AlignmentFlag.AlignCenter)
    etichetta.setFixedHeight(24)
    etichetta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    etichetta.setStyleSheet(
        f"background-color:{sfondo}; color:{colore}; font-weight:bold; font-size:11px; "
        f"padding:0 12px; border-radius:12px; border:1px solid {colore}40;"
    )
    return etichetta


def crea_elemento_elenco(
    *,
    cognome: str,
    nome: str,
    sottotitolo: str,
    etichette: list[tuple[str, str, str]],
    accento: str,
    tinta: str,
) -> tuple[QListWidgetItem, QFrame]:
    """Riga dell'elenco: iniziali nel colore della sezione, nome, sottotitolo, etichette.

    ``etichette`` sono ``(testo, sfondo, colore)`` mostrate a destra, nell'ordine dato.
    Restituisce l'elemento della lista e il widget da assegnargli con ``setItemWidget``.
    """

    scheda = QFrame()
    scheda.setObjectName("ItemCard")
    scheda.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
    riga = QHBoxLayout(scheda)
    riga.setContentsMargins(14, 10, 16, 10)
    riga.setSpacing(14)

    avatar = QLabel(iniziali(cognome, nome))
    avatar.setObjectName("AvatarElenco")
    avatar.setFixedSize(_LATO_AVATAR, _LATO_AVATAR)
    avatar.setAlignment(Qt.AlignmentFlag.AlignCenter)
    avatar.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
    avatar.setStyleSheet(
        f"background-color:{tinta}; color:{accento}; font-weight:bold; font-size:14px; "
        f"border-radius:{_LATO_AVATAR // 2}px;"
    )
    riga.addWidget(avatar)

    testi = QVBoxLayout()
    testi.setSpacing(2)
    lbl_nome = QLabel(f"{cognome} {nome}".strip())
    lbl_nome.setObjectName("ItemNome")
    lbl_sotto = QLabel(sottotitolo)
    lbl_sotto.setObjectName("ItemMatricola")
    for etichetta in (lbl_nome, lbl_sotto):
        etichetta.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        testi.addWidget(etichetta)
    riga.addLayout(testi, 1)

    for testo, sfondo, colore in etichette:
        riga.addWidget(pillola(testo, sfondo, colore), 0, Qt.AlignmentFlag.AlignVCenter)

    elemento = QListWidgetItem()
    elemento.setSizeHint(QSize(0, ALTEZZA_ELEMENTO))
    return elemento, scheda
