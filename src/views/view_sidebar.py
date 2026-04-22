import os
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QLabel, QFrame, QHBoxLayout, QSizePolicy
)
from PySide6.QtGui import QPixmap
from PySide6.QtCore import Qt, Signal


_VOCI_MENU = [
    ("Scadenzario Mensile",  "Turni e pianificazione mensile"),
    ("Sale Operatorie",      "Programma operatorio"),
    ("Libretto Carriere",    "Anagrafica specializzandi"),
    ("Lista Pazienti",       "Gestione lista pazienti"),
]

_COLORI_SEZIONE = [
    "#6366f1",   # Scadenzario  — indigo
    "#10b981",   # Sale Op.     — emerald
    "#a855f7",   # Libretto     — violet
    "#38bdf8",   # Pazienti     — sky
]


class Sidebar(QWidget):
    # Segnale pubblico — compatibile con main.py (.connect / .disconnect)
    currentRowChanged = Signal(int)

    def __init__(self):
        super().__init__()
        self.setObjectName("SidebarMain")
        self.setFixedWidth(280)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        self._nav_frames = []   # QFrame per sezione, per aggiornare lo stile

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        root.addWidget(self._build_header())
        root.addWidget(self._build_separator("SidebarSeparator"))
        root.addSpacing(4)
        root.addWidget(self._build_nav_label("NAVIGAZIONE"))
        root.addWidget(self._build_nav(), stretch=1)   # ← prende tutto lo spazio libero
        root.addWidget(self._build_separator("SidebarSeparator"))
        root.addWidget(self._build_footer())

        self.load_styles()

    # ─── Sezioni del layout ────────────────────────────────────────────────────

    def _build_header(self):
        header = QWidget()
        header.setObjectName("SidebarHeader")
        hl = QVBoxLayout(header)
        hl.setContentsMargins(20, 32, 20, 24)
        hl.setSpacing(8)

        self.logo_label = QLabel()
        logo_path = os.path.join("asset", "images", "logo_sigillo.svg")
        logo_pixmap = QPixmap(logo_path)
        if not logo_pixmap.isNull():
            scaled = logo_pixmap.scaled(
                78, 78,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            self.logo_label.setPixmap(scaled)
        self.logo_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(self.logo_label)

        hl.addSpacing(6)

        self.title_label = QLabel("MMSD · CV")
        self.title_label.setObjectName("SidebarTitle")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(self.title_label)

        sub = QLabel("Chirurgia Vascolare · UNITO")
        sub.setObjectName("SidebarSubtitle")
        sub.setAlignment(Qt.AlignmentFlag.AlignCenter)
        hl.addWidget(sub)

        return header

    def _build_separator(self, object_name="SidebarSeparator"):
        sep = QFrame()
        sep.setObjectName(object_name)
        sep.setFixedHeight(1)
        return sep

    def _build_nav_label(self, testo):
        lbl = QLabel(testo)
        lbl.setObjectName("SidebarNavLabel")
        lbl.setContentsMargins(26, 10, 0, 4)
        return lbl

    def _build_nav(self):
        """Contenitore dei bottoni di navigazione."""
        nav = QWidget()
        nav.setObjectName("SidebarNav")
        nav.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)

        vbox = QVBoxLayout(nav)
        vbox.setContentsMargins(0, 8, 0, 8)
        vbox.setSpacing(6)          # ← spazio tra sezioni (non interno)

        for i, (titolo, sottotitolo) in enumerate(_VOCI_MENU):
            frame = self._crea_nav_frame(i, titolo, sottotitolo)
            vbox.addWidget(frame)   # altezza naturale, no stretch

        vbox.addStretch()           # spazio libero va tutto in fondo

        return nav

    def _build_footer(self):
        footer = QWidget()
        footer.setObjectName("SidebarFooter")
        fl = QVBoxLayout(footer)
        fl.setContentsMargins(20, 14, 20, 18)
        fl.setSpacing(3)

        lbl_unito = QLabel("© UNITO 2026")
        lbl_unito.setObjectName("SidebarFooterText")
        lbl_unito.setAlignment(Qt.AlignmentFlag.AlignCenter)

        lbl_ver = QLabel("Demo Mockup")
        lbl_ver.setObjectName("SidebarFooterVersion")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)

        fl.addWidget(lbl_unito)
        fl.addWidget(lbl_ver)
        return footer

    # ─── Factory item di navigazione ──────────────────────────────────────────

    def _crea_nav_frame(self, idx, titolo, sottotitolo):
        colore = _COLORI_SEZIONE[idx % len(_COLORI_SEZIONE)]

        frame = QFrame()
        frame.setObjectName("NavItemFrame")
        frame.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        frame.setProperty("selected", False)
        frame.setFixedHeight(64)
        frame.setCursor(Qt.CursorShape.PointingHandCursor)

        row = QHBoxLayout(frame)
        row.setContentsMargins(26, 0, 16, 0)
        row.setSpacing(0)

        txt = QVBoxLayout()
        txt.setSpacing(4)

        lbl_titolo = QLabel(titolo)
        lbl_titolo.setObjectName("NavItemTitolo")
        lbl_titolo.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lbl_titolo.setProperty("selected", False)

        lbl_sub = QLabel(sottotitolo)
        lbl_sub.setObjectName("NavItemSottotitolo")
        lbl_sub.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        lbl_sub.setProperty("selected", False)

        txt.addWidget(lbl_titolo)
        txt.addWidget(lbl_sub)
        row.addLayout(txt)

        # Stile iniziale: barra sinistra dimmer con il colore della sezione
        r = int(colore[1:3], 16)
        g = int(colore[3:5], 16)
        b = int(colore[5:7], 16)
        frame.setStyleSheet(self._stile_non_selezionato(colore, r, g, b))

        # Click → selezione
        frame.mousePressEvent = lambda _ev, i=idx: self._seleziona(i)

        self._nav_frames.append(frame)
        return frame

    @staticmethod
    def _stile_non_selezionato(colore, r, g, b):
        return (
            f"QFrame#NavItemFrame{{"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0.000 rgba({r},{g},{b},55),stop:0.011 rgba({r},{g},{b},55),"
            f"stop:0.012 transparent,stop:1.000 transparent);}}"
            f"QFrame#NavItemFrame:hover{{"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0.000 rgba({r},{g},{b},110),stop:0.011 rgba({r},{g},{b},110),"
            f"stop:0.012 rgba(26,37,64,255),stop:1.000 rgba(26,37,64,255));}}"
        )

    @staticmethod
    def _stile_selezionato(colore, r, g, b):
        return (
            f"QFrame#NavItemFrame{{"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0.000 {colore},stop:0.011 {colore},"
            f"stop:0.012 rgba({r},{g},{b},42),stop:1.000 rgba({r},{g},{b},42));}}"
            f"QFrame#NavItemFrame:hover{{"
            f"background:qlineargradient(x1:0,y1:0,x2:1,y2:0,"
            f"stop:0.000 {colore},stop:0.011 {colore},"
            f"stop:0.012 rgba({r},{g},{b},55),stop:1.000 rgba({r},{g},{b},55));}}"
        )

    # ─── Gestione selezione ───────────────────────────────────────────────────

    def _seleziona(self, idx):
        """Aggiorna visual state di tutti gli item e notifica il cambio pagina."""
        for i, frame in enumerate(self._nav_frames):
            sel = (i == idx)
            colore = _COLORI_SEZIONE[i % len(_COLORI_SEZIONE)]
            r = int(colore[1:3], 16)
            g = int(colore[3:5], 16)
            b = int(colore[5:7], 16)

            frame.setStyleSheet(
                self._stile_selezionato(colore, r, g, b)
                if sel else
                self._stile_non_selezionato(colore, r, g, b)
            )

            frame.setProperty("selected", sel)
            frame.style().unpolish(frame)
            frame.style().polish(frame)
            frame.update()

            for child in frame.findChildren(QLabel):
                child.setProperty("selected", sel)
                child.style().unpolish(child)
                child.style().polish(child)
                child.update()

        self.currentRowChanged.emit(idx)

    # ─── Interfaccia pubblica ─────────────────────────────────────────────────

    def setCurrentRow(self, row):
        self._seleziona(row)

    # ─── Stili ────────────────────────────────────────────────────────────────

    def load_styles(self):
        style_path = os.path.join("asset", "styles", "sidebar.qss")
        if os.path.exists(style_path):
            with open(style_path, "r", encoding="utf-8") as f:
                self.setStyleSheet(self.styleSheet() + "\n" + f.read())
