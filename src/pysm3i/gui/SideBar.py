from PyQt6.QtWidgets import QDockWidget, QListWidget, QWidget
from PyQt6.QtCore import pyqtSignal

PAGES = ["Sky", "Catalog", "SED", "Spectra", "Tools"]

class SideBar(QDockWidget):
    page_changed = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__("Navigation", parent)
        self.setFeatures(QDockWidget.DockWidgetFeature.NoDockWidgetFeatures)  # Disable docking features
        self.setTitleBarWidget(QWidget())  # Remove the title bar
        self.setFixedWidth(200)  # Set a fixed width for the sidebar

        self.list_widget = QListWidget()
        self.list_widget.addItems(PAGES)

        # Forward the list's row change straight out as our own signal
        self.list_widget.currentRowChanged.connect(self.page_changed)
        self.setWidget(self.list_widget)
        self.list_widget.setCurrentRow(0)  # Set the default selected page to "Sky"
