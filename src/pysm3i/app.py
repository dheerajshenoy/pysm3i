import sys

from PyQt6.QtWidgets import QApplication, QMainWindow
from pysm3i.gui import MainWindow

def main() -> int:
    app = QApplication([])
    app.setApplicationName("PySM3i")
    window = MainWindow()
    window.show()
    return app.exec()
