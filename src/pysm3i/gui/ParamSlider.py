from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import QDoubleSpinBox, QHBoxLayout, QLabel, QSlider, QWidget

from pysm3i.core.playground import Parameter


class ParamSlider(QWidget):
    """A label, a slider and a number box that stay in sync. Emits (key, value)."""

    changed = pyqtSignal(str, float)

    def __init__(self, parameter: Parameter, parent=None):
        super().__init__(parent)
        self.parameter = parameter
        self._steps = round((parameter.high - parameter.low) / parameter.step)
        self._syncing = False

        label = QLabel(parameter.label)
        label.setMinimumWidth(34)
        self.slider = QSlider(Qt.Orientation.Horizontal)
        self.slider.setRange(0, self._steps)
        self.spin = QDoubleSpinBox()
        self.spin.setRange(parameter.low, parameter.high)
        self.spin.setSingleStep(parameter.step)
        self.spin.setDecimals(len(f"{parameter.step:g}".split(".")[1]) if "." in f"{parameter.step:g}" else 0)
        self.spin.setSuffix(parameter.suffix)
        for widget in (self, label, self.slider, self.spin):
            widget.setToolTip(parameter.tooltip)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(label)
        layout.addWidget(self.slider, stretch=1)
        layout.addWidget(self.spin)
        self.slider.valueChanged.connect(self._from_slider)
        self.spin.valueChanged.connect(self._from_spin)
        self.set_value(parameter.default, emit=False)

    def value(self) -> float:
        return self.spin.value()

    def set_value(self, value: float, emit: bool = True):
        self._syncing = True
        self.spin.setValue(value)
        self.slider.setValue(round((self.spin.value() - self.parameter.low) / self.parameter.step))
        self._syncing = False
        if emit:
            self.changed.emit(self.parameter.key, self.spin.value())

    def _from_slider(self, position: int):
        if not self._syncing:
            self.set_value(self.parameter.low + position * self.parameter.step)

    def _from_spin(self, value: float):
        if not self._syncing:
            self.set_value(value)
