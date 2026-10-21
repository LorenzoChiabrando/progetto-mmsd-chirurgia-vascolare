from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Callable
from logging.handlers import RotatingFileHandler
from pathlib import Path
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QStackedWidget
from PySide6.QtCore import QLoggingCategory

from src.data_paths import PROJECT_ROOT, resolve_data_directory
from src.models.json_files import CorruptedDataError
from src.views.components import messages
from src.views.components.error_handler import install_exception_hook
from src.controllers.controller_sale_operatorie import ControllerSaleOperatorie
from src.models.data_manager_sale_operatorie import DataManagerSaleOperatorie
from src.views.view_sidebar import Sidebar
from src.views.view_scadenzario import ViewScadenzario
from src.views.view_pazienti import ViewPazienti
from src.views.view_sale_operatorie import ViewSaleOperatorie
from src.views.view_libretto import ViewLibretto
from src.models.data_manager import DataManager
from src.controllers.controller_scadenzario import ControllerScadenzario
from src.models.data_manager_libretto import DataManagerLibretto
from src.controllers.controller_libretto import ControllerLibretto
from src.models.data_manager_pazienti import DataManagerPazienti
from src.controllers.controller_pazienti import ControllerPazienti

_LOGGER = logging.getLogger("mmsd_cv")

LOG_FILE = PROJECT_ROOT / "logs" / "mmsd-cv.log"
_LOG_MAX_BYTES = 1_000_000
_LOG_BACKUPS = 3
_LOG_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"


def configure_logging(log_file: Path = LOG_FILE) -> Path | None:
    """Configura il logging dell'applicazione (solo qui, al punto d'ingresso).

    Scrive tutto da INFO in su in ``log_file`` (a rotazione: 1 MB per 3 file) e mostra
    sul terminale gli avvisi. Restituisce il file di log, oppure ``None`` se non è
    scrivibile: in quel caso l'app parte comunque, con i soli avvisi sul terminale.
    """
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    console = logging.StreamHandler()
    console.setLevel(logging.WARNING)
    console.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(console)
    try:
        log_file.parent.mkdir(parents=True, exist_ok=True)
        file_handler = RotatingFileHandler(
            log_file, maxBytes=_LOG_MAX_BYTES, backupCount=_LOG_BACKUPS, encoding="utf-8"
        )
    except OSError:
        _LOGGER.warning("Log su file non disponibile: %s", log_file.name)
        return None
    file_handler.setFormatter(logging.Formatter(_LOG_FORMAT))
    root.addHandler(file_handler)
    return log_file


def open_main_window(create_window: Callable[[], QMainWindow]) -> QMainWindow | None:
    """Crea la finestra principale; con dati danneggiati avvisa e restituisce ``None``.

    Un file danneggiato non viene mai letto come vuoto (vedi ``read_json_object``):
    meglio fermarsi spiegando quale file sistemare che lavorare su dati incompleti.
    Gli altri errori proseguono verso il gestore globale.
    """
    try:
        return create_window()
    except CorruptedDataError as error:
        _LOGGER.error("Avvio interrotto: file danneggiato %s", error.path.name)
        messages.show_message(
            None,
            "Impossibile avviare l'applicazione",
            str(error),
            section="generale",
            kind="error",
        )
        return None


class MainWindow(QMainWindow):
    def __init__(self, data_directory: str | Path | None = None):
        super().__init__()
        self.data_directory = resolve_data_directory(data_directory)

        self.view_scad = None
        self.controller_scad = None
        self.data_manager = None
        
        self.view_libretto = None
        self.controller_libretto = None
        self.data_manager_libretto = None

        self.view_pazienti = None
        self.controller_pazienti = None
        self.data_manager_pazienti = None

        self.view_sale_operatorie = None
        self.controller_sale_operatorie = None
        self.data_manager_sale_operatorie = None

        self.setWindowTitle("MMSD CV - Demo Mockup")
        self.resize(1024, 768)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        self.sidebar = Sidebar()
        main_layout.addWidget(self.sidebar)

        self.body_stack = QStackedWidget()
        main_layout.addWidget(self.body_stack)

        self.init_pages()

        self.sidebar.currentRowChanged.connect(self._cambia_sezione)
        self.sidebar.setCurrentRow(0)

    def _cambia_sezione(self, nuovo_idx):
        """Resetta la sezione corrente e aggiorna i dati della nuova prima di mostrarla."""
        vecchio_view = self.body_stack.currentWidget()
        if hasattr(vecchio_view, 'stacked_widget'):
            vecchio_view.stacked_widget.setCurrentIndex(0)
        self.body_stack.setCurrentIndex(nuovo_idx)
        self._aggiorna_sezione(nuovo_idx)

    def _aggiorna_sezione(self, idx):
        if idx == 3 and self.controller_pazienti:
            self.controller_pazienti.aggiorna_lista()
        elif idx == 1 and self.controller_libretto:
            self.controller_libretto.aggiorna_lista()

    def init_pages(self):
        self.data_manager = DataManager(self.data_directory / "scadenzario")
        self.data_manager_libretto = DataManagerLibretto(self.data_directory / "libretti")
        self.data_manager_pazienti = DataManagerPazienti(self.data_directory / "pazienti")
        self.data_manager_sale_operatorie = DataManagerSaleOperatorie(
            self.data_directory / "sale_operatorie"
        )

        self.view_scad = ViewScadenzario()
        self.controller_scad = ControllerScadenzario(
            self.view_scad,
            self.data_manager,
            model_sale_operatorie=self.data_manager_sale_operatorie,
        )

        self.view_libretto = ViewLibretto()
        self.controller_libretto = ControllerLibretto(
            self.view_libretto,
            self.data_manager_libretto,
            model_scadenzario=self.data_manager,
            model_sale_operatorie=self.data_manager_sale_operatorie,
        )

        self.view_pazienti = ViewPazienti()
        self.controller_pazienti = ControllerPazienti(
            self.view_pazienti,
            self.data_manager_pazienti,
            model_sale_operatorie=self.data_manager_sale_operatorie,
        )

        self.view_sale_operatorie = ViewSaleOperatorie()
        self.controller_sale_operatorie = ControllerSaleOperatorie(
            self.view_sale_operatorie,
            self.data_manager_sale_operatorie,
            model_scadenzario=self.data_manager,
            model_pazienti=self.data_manager_pazienti,
            model_libretto=self.data_manager_libretto,
            data_directory=self.data_directory,
        )
        self.controller_sale_operatorie.planning_busy_changed.connect(
            self.sidebar.setDisabled
        )
        self.controller_sale_operatorie.planning_busy_changed.connect(
            self.view_scad.combo_versione.setDisabled
        )

        self.body_stack.addWidget(self.view_scad)
        self.body_stack.addWidget(self.view_libretto)
        self.body_stack.addWidget(self.view_sale_operatorie)
        self.body_stack.addWidget(self.view_pazienti)

    def closeEvent(self, event):
        """Cooperatively stop an active optimization before closing Qt."""
        controller = self.controller_sale_operatorie
        if controller is not None and not controller.shutdown_planning():
            event.ignore()
            return
        super().closeEvent(event)

def main() -> int:
    parser = argparse.ArgumentParser(description="MMSD CV")
    parser.add_argument("--data-dir", type=Path, help="Cartella dati condivisa da GUI e planner")
    args, qt_args = parser.parse_known_args()
    log_file = configure_logging()
    app = QApplication([sys.argv[0], *qt_args])
    QLoggingCategory.setFilterRules("qt.qpa.wayland.textinput=false")
    app.setStyle("Fusion")
    install_exception_hook(log_file)

    window = open_main_window(lambda: MainWindow(data_directory=args.data_dir))
    if window is None:
        return 1
    window.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
