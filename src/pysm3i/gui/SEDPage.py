import threading

import healpy as hp
import numpy as np
import pysm3.units as u
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from pysm3i.core.skymodel import UNITS, SkyModel
from pysm3i.models import load_registry
from .BusyBar import BusyBar
from .ScaleControls import ScaleControls
from .jobs import Job

SED_NSIDE = 32  # coarse on purpose: a spectrum needs one map per frequency
FREQS_GHZ = np.logspace(1, 3, 25)  # 10 to 1000 GHz
STOKES = ["I", "P"]
CMB_RMS_UK = 100.0  # rough rms of CMB temperature anisotropies, in uK_CMB
DEBOUNCE_MS = 200


class SEDPage(QWidget):
    """Spectrum of the active components at one sky pixel."""

    def __init__(self, model: SkyModel, get_presets):
        super().__init__()
        self._model = model
        self._get_presets = get_presets  # callable returning the active preset names
        self._registry = load_registry()
        self._data: dict[str, np.ndarray] = {}  # preset -> (3, nfreq) in uK_RJ
        self._request_id = 0
        self._cancel = threading.Event()
        self._dirty = True  # recompute the next time the page is shown
        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._debounce.timeout.connect(self._request)
        self._init_ui()

    # ---- UI --------------------------------------------------------------

    def _init_ui(self):
        self.canvas = FigureCanvasQTAgg(Figure(figsize=(8, 5), layout="constrained"))
        self.lon = self._angle_box(0.0, 360.0, 0.0)
        self.lat = self._angle_box(-90.0, 90.0, 45.0)
        self.stokes_combo = QComboBox()
        self.stokes_combo.addItems(STOKES)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(UNITS)
        self.status = QLabel()
        self.busy = BusyBar()
        self.busy.stop_requested.connect(self._stop)

        self.lon.valueChanged.connect(self._schedule)
        self.lat.valueChanged.connect(self._schedule)
        self.scales = ScaleControls()
        self.stokes_combo.currentIndexChanged.connect(self._redraw)
        self.unit_combo.currentIndexChanged.connect(self._redraw)
        self.scales.changed.connect(self._redraw)

        controls = QHBoxLayout()
        for text, widget in [("l", self.lon), ("b", self.lat),
                             ("Stokes", self.stokes_combo), ("Units", self.unit_combo)]:
            controls.addWidget(QLabel(text))
            controls.addWidget(widget)
        controls.addWidget(self.scales)
        controls.addStretch(1)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, stretch=1)
        status_row.addWidget(self.busy)

        root = QVBoxLayout(self)
        root.addWidget(self.canvas, stretch=1)
        root.addLayout(controls)
        root.addLayout(status_row)

    @staticmethod
    def _angle_box(low: float, high: float, value: float) -> QDoubleSpinBox:
        box = QDoubleSpinBox()
        box.setRange(low, high)
        box.setDecimals(1)
        box.setSuffix("°")
        box.setValue(value)
        return box

    # ---- inputs from other pages ----------------------------------------

    def set_pixel(self, lon: float, lat: float):
        for box, value in ((self.lon, lon), (self.lat, lat)):
            box.blockSignals(True)
            box.setValue(value)
            box.blockSignals(False)
        self._invalidate()

    def invalidate(self):
        """The active presets changed elsewhere."""
        self._invalidate()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._schedule()

    # ---- computing -------------------------------------------------------

    def _invalidate(self):
        self._dirty = True
        if self.isVisible():
            self._schedule()

    def _schedule(self, *_):
        self._dirty = True
        self._debounce.start()

    def _request(self):
        presets = self._get_presets()
        if not presets:
            self._cancel.set()
            self._data = {}
            self._dirty = False
            self.busy.hide()
            self._redraw()
            return
        self._cancel.set()  # skip remaining work of any job this one supersedes
        self._cancel = threading.Event()
        self._request_id += 1
        self.status.clear()
        self.busy.show()
        model, cancel = self._model, self._cancel
        pixel = int(hp.ang2pix(SED_NSIDE, self.lon.value(), self.lat.value(), lonlat=True))
        job = Job(self._request_id,
                  lambda: model.sed(presets, SED_NSIDE, FREQS_GHZ, pixel, cancel))
        job.signals.done.connect(self._on_ready)
        job.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(job)

    def _on_ready(self, request_id: int, data: dict):
        if request_id != self._request_id:
            return
        self._data = data
        self._dirty = False
        self.busy.hide()
        self._redraw()

    def _on_failed(self, request_id: int, message: str):
        if request_id == self._request_id:
            self.busy.hide()
            self.status.setText(f"Failed: {message}")

    def _stop(self):
        self._debounce.stop()
        self._cancel.set()
        self._request_id += 1  # a late result from the cancelled job is now stale
        self.busy.hide()
        self.status.setText("Stopped.")

    # ---- drawing ---------------------------------------------------------

    def _redraw(self, *_):
        stokes = self.stokes_combo.currentText()
        unit_label = self.unit_combo.currentText()
        unit = u.Unit(UNITS[unit_label])
        equivalencies = u.cmb_equivalencies(FREQS_GHZ * u.GHz)

        def to_unit(values: np.ndarray) -> np.ndarray:
            return (values * u.uK_RJ).to(unit, equivalencies).value

        def select(iqu: np.ndarray) -> np.ndarray:
            # abs(): CMB anisotropies can be negative and would vanish on a log axis
            return np.abs(to_unit(iqu[0])) if stokes == "I" else np.hypot(to_unit(iqu[1]), to_unit(iqu[2]))

        self.canvas.figure.clear()
        ax = self.canvas.figure.add_subplot()
        if not self._data:
            ax.text(0.5, 0.5, "Enable components on the Sky page", ha="center",
                    va="center", transform=ax.transAxes)
            ax.set_axis_off()
            self.canvas.draw_idle()
            return

        empty = []
        for preset, iqu in self._data.items():
            label = f"{self._component_name(preset)} ({preset})"
            curve = select(iqu)
            if not curve.any():  # all zero, e.g. free-free has no polarization
                empty.append(label)
                continue
            ax.plot(FREQS_GHZ, curve, linewidth=2, label=label)
        self.status.setText(f"No {stokes} emission: {', '.join(empty)}" if empty else "")
        total = sum(self._data.values())
        if len(self._data) > 1:
            ax.plot(FREQS_GHZ, select(total), "k--", label="Total", linewidth=1.5)
        if stokes == "I":
            cmb = (np.full(FREQS_GHZ.shape, CMB_RMS_UK) * u.uK_CMB).to(unit, equivalencies).value
            ax.plot(FREQS_GHZ, cmb, ":", color="gray",
                      label=f"CMB anisotropy, rms ≈ {CMB_RMS_UK:.0f} µK_CMB")
        ax.set_xlabel("Frequency [GHz]")
        ax.set_ylabel(f"{'|I|' if stokes == 'I' else 'P'} [{unit_label}]")
        ax.set_title(f"Spectrum at l = {self.lon.value():.1f}°, b = {self.lat.value():.1f}° "
                     f"(nside {SED_NSIDE})")
        self.scales.apply(ax)
        ax.grid(True, which="both", alpha=0.3)
        ax.legend(fontsize=9)
        self.canvas.draw_idle()

    def _component_name(self, preset: str) -> str:
        key = self._registry[preset].component
        return next(c.name for c in self._registry.components if c.key == key)
