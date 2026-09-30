from PyQt6.QtWidgets import QMainWindow, QMessageBox, QStackedWidget
from PyQt6.QtCore import Qt
from pysm3i.models import load_registry
from .CatalogPage import CatalogPage
from .PlaceholderPage import PlaceholderPage
from .SkyPage import SkyPage
from .SideBar import PAGES, SideBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PySMi")
        self.init_central_widget()
        self.init_sidebar()

    def init_central_widget(self):
        # One page per sidebar entry, in the same order as PAGES
        self.sky_page = SkyPage()
        self.catalog_page = CatalogPage(can_show_on_sky=self.sky_page.can_show)
        self.catalog_page.show_on_sky.connect(self.show_preset_on_sky)
        built = {"Sky": self.sky_page, "Catalog": self.catalog_page}

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
