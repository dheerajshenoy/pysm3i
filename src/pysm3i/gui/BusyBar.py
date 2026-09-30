from PyQt6.QtCore import pyqtSignal
from PyQt6.QtWidgets import QHBoxLayout, QProgressBar, QPushButton, QSizePolicy, QWidget


class BusyBar(QWidget):
    """Indeterminate progress bar with a Stop button. Hidden until shown."""

    stop_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate: PySM3 reports no progress
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(160)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip(
            "Stop computing. A preset already in progress finishes in the background."
        )
        self.stop_button.clicked.connect(self.stop_requested)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(self.progress)
        layout.addWidget(self.stop_button)
        # Keep the space when hidden, so the layout does not jump on start/finish
        policy = self.sizePolicy()
        policy.setRetainSizeWhenHidden(True)
        self.setSizePolicy(policy)
        self.hide()
