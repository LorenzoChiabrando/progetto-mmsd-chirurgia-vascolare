import sys
from PySide6.QtWidgets import QApplication, QMainWindow, QWidget, QHBoxLayout, QStackedWidget

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

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

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
        """Resetta la sezione corrente alla sua pagina iniziale prima di cambiarla."""
        vecchio_view = self.body_stack.currentWidget()
        if hasattr(vecchio_view, 'stacked_widget'):
            vecchio_view.stacked_widget.setCurrentIndex(0)
        self.body_stack.setCurrentIndex(nuovo_idx)

    def init_pages(self):
        self.data_manager = DataManager()
        self.data_manager_libretto = DataManagerLibretto()
        self.data_manager_pazienti = DataManagerPazienti()
        self.data_manager_sale_operatorie = DataManagerSaleOperatorie()

        self.view_scad = ViewScadenzario()
        self.controller_scad = ControllerScadenzario(
            self.view_scad,
            self.data_manager,
            model_sale_operatorie=self.data_manager_sale_operatorie,
        )

        self.view_libretto = ViewLibretto()
        self.controller_libretto = ControllerLibretto(self.view_libretto, self.data_manager_libretto)

        self.view_pazienti = ViewPazienti()
        self.controller_pazienti = ControllerPazienti(self.view_pazienti, self.data_manager_pazienti)

        self.view_sale_operatorie = ViewSaleOperatorie()
        self.controller_sale_operatorie = ControllerSaleOperatorie(
            self.view_sale_operatorie,
            self.data_manager_sale_operatorie,
            model_scadenzario=self.data_manager,
            model_pazienti=self.data_manager_pazienti,
            model_libretto=self.data_manager_libretto,
        )

        self.body_stack.addWidget(self.view_scad)
        self.body_stack.addWidget(self.view_sale_operatorie)
        self.body_stack.addWidget(self.view_libretto)
        self.body_stack.addWidget(self.view_pazienti)

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setStyle("Fusion")

    window = MainWindow()
    window.show()

    sys.exit(app.exec())
