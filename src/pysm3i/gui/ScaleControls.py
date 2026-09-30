from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QWidget

SCALES = ["log", "linear"]


class ScaleControls(QWidget):
    """Independent log/linear choices for the x and y axes of a plot."""

    changed = pyqtSignal()

    def __init__(self, x: str = "log", y: str = "log", parent=None):
        super().__init__(parent)
        self.x_combo = QComboBox()
        self.y_combo = QComboBox()
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        for label, combo, initial in (("X scale", self.x_combo, x), ("Y scale", self.y_combo, y)):
            combo.addItems(SCALES)
            combo.setCurrentText(initial)
            combo.currentIndexChanged.connect(self.changed)
            layout.addWidget(QLabel(label))
            layout.addWidget(combo)

    def apply(self, ax):
        ax.set_xscale(self.x_combo.currentText())
        ax.set_yscale(self.y_combo.currentText())
