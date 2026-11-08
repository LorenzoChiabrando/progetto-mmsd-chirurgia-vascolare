"""Pannello con l'esito della pianificazione: valore del modello e valore del piano attuale."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QVBoxLayout

from src.optimization.results import ObjectiveBreakdown, SolveStatus


def _numero(valore: float, decimali: int = 2) -> str:
    testo = f"{valore:,.{decimali}f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return testo.rstrip("0").rstrip(",") if "," in testo else testo


def _percento(frazione: float | None) -> str:
    if frazione is None:
        return "—"
    return f"{_numero(frazione * 100, 2)}%"


def _secondi(secondi: float | None) -> str:
    if secondi is None:
        return "—"
    if secondi < 0.1:
        return "meno di 0,1 s"
    if secondi < 60:
        return f"{_numero(secondi, 1)} s"
    minuti, resto = divmod(int(round(secondi)), 60)
    return f"{minuti} min {resto} s" if resto else f"{minuti} min"


def _componenti(efficienza: float, equita: Any, non_assegnati: Any) -> str:
    return f"efficienza {_numero(efficienza, 2)} · equità {equita} · non assegnati {non_assegnati}"


class RiepilogoOttimizzazione(QFrame):
    """Valore del piano del modello, valore del piano attuale e ritorno al modello.

    Il valore attuale si ricalcola a ogni modifica manuale; il pulsante «Ripristina
    piano del modello» emette :attr:`ripristino_richiesto`.
    """

    ripristino_richiesto = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("RiepilogoOttimizzazione")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        colonna = QVBoxLayout(self)
        colonna.setContentsMargins(18, 10, 18, 10)
        colonna.setSpacing(6)

        riga = QHBoxLayout()
        riga.setSpacing(34)
        self.lbl_modello, self.lbl_componenti_modello = self._valore(riga, "Piano del modello")
        self.lbl_attuale, self.lbl_componenti_attuale = self._valore(riga, "Piano attuale")
        self.lbl_differenza = QLabel()
        self.lbl_differenza.setObjectName("DifferenzaObiettivo")
        riga.addWidget(self.lbl_differenza, 0, Qt.AlignmentFlag.AlignVCenter)
        riga.addStretch(1)

        destra = QVBoxLayout()
        destra.setSpacing(4)
        self.lbl_stato = QLabel()
        self.lbl_stato.setObjectName("StatoPiano")
        self.lbl_stato.setAlignment(Qt.AlignmentFlag.AlignRight)
        self.btn_ripristina = QPushButton("↺  Ripristina piano del modello")
        self.btn_ripristina.setObjectName("BtnRipristinaModello")
        self.btn_ripristina.setCursor(Qt.CursorShape.PointingHandCursor)
        self.btn_ripristina.clicked.connect(self.ripristino_richiesto.emit)
        destra.addWidget(self.lbl_stato)
        destra.addWidget(self.btn_ripristina, 0, Qt.AlignmentFlag.AlignRight)
        riga.addLayout(destra)
        colonna.addLayout(riga)

        self.lbl_dettagli = QLabel()
        self.lbl_dettagli.setObjectName("NotaRiepilogo")
        self.lbl_dettagli.setWordWrap(True)
        colonna.addWidget(self.lbl_dettagli)
        self.hide()

    @staticmethod
    def _valore(riga, titolo: str) -> tuple[QLabel, QLabel]:
        blocco = QVBoxLayout()
        blocco.setSpacing(1)
        lbl_titolo = QLabel(titolo.upper())
        lbl_titolo.setObjectName("TitoloRiepilogo")
        valore = QLabel("—")
        valore.setObjectName("ValoreObiettivo")
        dettaglio = QLabel()
        dettaglio.setObjectName("DettaglioRiepilogo")
        for etichetta in (lbl_titolo, valore, dettaglio):
            blocco.addWidget(etichetta)
        riga.addLayout(blocco)
        return valore, dettaglio

    def mostra(
        self,
        riepilogo: dict[str, Any] | None,
        *,
        attuale: ObjectiveBreakdown | None = None,
        errore_attuale: str = "",
        modificato: bool = False,
        originale_disponibile: bool = True,
        ripristinabile: bool = False,
        motivo_non_ripristinabile: str = "",
    ) -> None:
        """Mostra l'esito della pianificazione e il confronto con il piano attuale.

        Senza ``riepilogo`` (la settimana non è mai stata pianificata dal modello) il
        pannello resta nascosto.
        """

        if not riepilogo:
            self.hide()
            return
        modello = riepilogo.get("valore_obiettivo")
        self.lbl_modello.setText(_numero(modello, 3) if modello is not None else "—")
        componenti = riepilogo.get("componenti") or {}
        self.lbl_componenti_modello.setText(
            _componenti(
                componenti.get("efficienza_trattamento", 0),
                componenti.get("equita_minima", "—"),
                componenti.get("non_assegnati", "—"),
            ) if componenti else ""
        )

        if attuale is not None:
            self.lbl_attuale.setText(_numero(attuale.weighted_total, 3))
            self.lbl_componenti_attuale.setText(_componenti(
                attuale.treatment_efficiency, attuale.fairness_floor, attuale.unassigned_count
            ))
            self.lbl_attuale.setToolTip("")
        else:
            self.lbl_attuale.setText("non calcolabile")
            self.lbl_componenti_attuale.setText(errore_attuale)
        self._mostra_differenza(modello, attuale)

        if not originale_disponibile:
            # Pianificazione salvata prima che esistesse il piano del modello a parte.
            self.lbl_stato.setText("Piano originale non disponibile")
        else:
            self.lbl_stato.setText(
                "Modificato a mano" if modificato else "Uguale al piano del modello"
            )
        self.lbl_stato.setProperty("modificato", modificato or not originale_disponibile)
        self.lbl_stato.style().unpolish(self.lbl_stato)
        self.lbl_stato.style().polish(self.lbl_stato)
        self.btn_ripristina.setVisible(modificato)
        self.btn_ripristina.setEnabled(ripristinabile)
        self.btn_ripristina.setToolTip(
            "Rimette gli interventi come li ha pianificati il modello"
            if ripristinabile else motivo_non_ripristinabile
        )

        try:
            esito = SolveStatus(riepilogo.get("esito")).label
        except ValueError:
            esito = str(riepilogo.get("esito") or "—")
        parametri = riepilogo.get("parametri") or {}
        try:
            quando = datetime.fromisoformat(riepilogo.get("calcolato_il")).strftime(
                "%d/%m/%Y alle %H:%M"
            )
        except (TypeError, ValueError):
            quando = "—"
        self.lbl_dettagli.setText(
            f"Pianificazione del {quando} · esito {esito} · gap ottenuto "
            f"{_percento(riepilogo.get('gap_ottenuto'))} · calcolo "
            f"{_secondi(riepilogo.get('tempo_secondi'))}"
            + (
                f" · parametri: limite {_secondi(parametri.get('limite_tempo_secondi'))}, "
                f"gap {_percento(parametri.get('gap_relativo'))}" if parametri else ""
            )
        )
        self.show()

    def _mostra_differenza(self, modello: float | None, attuale: ObjectiveBreakdown | None) -> None:
        if modello is None or attuale is None:
            self.lbl_differenza.hide()
            return
        differenza = attuale.weighted_total - modello
        if abs(differenza) < 1e-9:
            testo, tono = "= uguale", "uguale"
        else:
            freccia = "▲" if differenza > 0 else "▼"
            relativa = differenza / abs(modello) if modello else None
            testo = f"{freccia} {_numero(abs(differenza), 3)}"
            if relativa is not None:
                testo += f"  ({'+' if differenza > 0 else '−'}{_numero(abs(relativa) * 100, 1)}%)"
            tono = "meglio" if differenza > 0 else "peggio"
        self.lbl_differenza.setText(testo)
        self.lbl_differenza.setProperty("tono", tono)
        self.lbl_differenza.style().unpolish(self.lbl_differenza)
        self.lbl_differenza.style().polish(self.lbl_differenza)
        self.lbl_differenza.show()
