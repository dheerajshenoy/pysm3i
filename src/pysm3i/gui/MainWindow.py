from PyQt6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget
from PyQt6.QtCore import Qt
from pysm3i.core.skymodel import SkyModel
from pysm3i.core.spectra import SpectraModel
from pysm3i.models import load_registry
from .CatalogPage import CatalogPage
from .PlaceholderPage import PlaceholderPage
from .SEDPage import SEDPage
from .SkyPage import SkyPage
from .SpectraPage import SpectraPage
from .ToolsPage import ToolsPage
from .SideBar import PAGES, SideBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PySMi")
        self.init_central_widget()
        self.init_sidebar()

    def init_central_widget(self):
        # One page per sidebar entry, in the same order as PAGES
        model = SkyModel()  # shared, so both pages reuse each other's computed maps
        self.sky_page = SkyPage(model)
        self.catalog_page = CatalogPage(can_show_on_sky=self.sky_page.can_show,
                                        active_presets=self.sky_page.active_presets)
        self.sky_page.presets_changed.connect(self.catalog_page.refresh_active)
        self.catalog_page.show_on_sky.connect(self.show_preset_on_sky)
        self.sed_page = SEDPage(model, self.sky_page.active_presets)
        self.sky_page.pixel_selected.connect(self.sed_page.set_pixel)
        self.sky_page.presets_changed.connect(self.sed_page.invalidate)
        self.spectra_page = SpectraPage(SpectraModel(model), self.sky_page.active_presets)
        self.sky_page.presets_changed.connect(self.spectra_page.invalidate)
        built = {"Sky": self.sky_page, "Catalog": self.catalog_page, "SED": self.sed_page,
                 "Spectra": self.spectra_page, "Tools": ToolsPage()}

        self.stack_widget = QStackedWidget()
        for name in PAGES:
            self.stack_widget.addWidget(built.get(name) or PlaceholderPage(name))
        self.setCentralWidget(self.stack_widget)

    def init_sidebar(self):
        # Create a sidebar and add it to the main window
        self.sidebar = SideBar()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar)
        self.sidebar.page_changed.connect(self.change_page)

    def change_page(self, page_index):
        # Change the central widget's page based on the sidebar selection
        self.stack_widget.setCurrentIndex(page_index)

    def show_preset_on_sky(self, name: str):
        if load_registry()[name].is_large:
            answer = QMessageBox.question(
                self, "Large download",
                f"{name} uses high-resolution templates. Showing it may download "
                "a large file the first time. Continue?",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        if self.sky_page.select_preset(name):
            self.sidebar.list_widget.setCurrentRow(PAGES.index("Sky"))
