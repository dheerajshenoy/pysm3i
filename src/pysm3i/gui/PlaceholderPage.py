from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QLabel, QVBoxLayout, QWidget


class PlaceholderPage(QWidget):
    """Stand-in for a page that has not been built yet."""

    def __init__(self, title: str):
        super().__init__()
        label = QLabel(f"{title}\n\nComing soon")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout = QVBoxLayout(self)
        layout.addWidget(label)
