from PyQt6.QtWidgets import QMainWindow, QApplication, QPushButton, QVBoxLayout, QWidget, QStackedWidget
from PyQt6.QtCore import Qt
from .SkyPage import SkyPage
from .SideBar import SideBar


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        self.setWindowTitle("PySMi")
        self.init_central_widget()
        self.init_sidebar()

    def init_central_widget(self):
        # Create a central widget and set the layout
        self.stack_widget = QStackedWidget()
        self.stack_widget.addWidget(SkyPage())
        self.setCentralWidget(self.stack_widget)

    def init_sidebar(self):
        # Create a sidebar and add it to the main window
        self.sidebar = SideBar()
        self.addDockWidget(Qt.DockWidgetArea.LeftDockWidgetArea, self.sidebar)
        self.sidebar.page_changed.connect(self.change_page)

    def change_page(self, page_index):
        # Change the central widget's page based on the sidebar selection
        self.stack_widget.setCurrentIndex(page_index)
