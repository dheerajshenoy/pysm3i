import threading

import numpy as np
from PyQt6.QtCore import QObject, QRunnable, Qt, QThreadPool, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel,
    QProgressBar, QPushButton, QSlider, QVBoxLayout, QWidget,
)

from pysm3i.core.skymodel import UNITS, Cancelled, SkyModel
from pysm3i.models import load_registry
from .MapCanvas import MapCanvas

# Components shown on this page, in display order, with a cheap default preset.
COMPONENTS = ["dust", "synchrotron", "free_free", "ame", "cmb"]
DEFAULT_PRESET = {"dust": "d1", "synchrotron": "s1", "free_free": "f1",
                  "ame": "a1", "cmb": "c1"}
DEFAULT_ENABLED = {"dust", "synchrotron", "free_free"}

STOKES = ["I", "Q", "U", "P"]
DEFAULT_NSIDE = 64
MAX_NSIDE = 1024  # 2048 needs ~1.2 GB per component map
NSIDES = [2**k for k in range(MAX_NSIDE.bit_length())]  # 1, 2, 4, ... MAX_NSIDE
FREQ_MIN_LOG, FREQ_MAX_LOG = 1.0, 3.0  # 10 GHz to 1000 GHz
SLIDER_STEPS = 1000
DEBOUNCE_MS = 150


def slider_to_ghz(value: int) -> float:
    return 10 ** (FREQ_MIN_LOG + (FREQ_MAX_LOG - FREQ_MIN_LOG) * value / SLIDER_STEPS)


def ghz_to_slider(freq: float) -> int:
    return round((np.log10(freq) - FREQ_MIN_LOG) / (FREQ_MAX_LOG - FREQ_MIN_LOG) * SLIDER_STEPS)


def is_large(config: dict) -> bool:
    """Presets that need high-resolution templates trigger big downloads."""
    return "available_nside" in config or config.get("max_nside", 0) >= 2048


class _JobSignals(QObject):
    done = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)


class _Job(QRunnable):
    def __init__(self, request_id, model, presets, nside, freq_ghz, unit, cancel):
        super().__init__()
        self.signals = _JobSignals()
        self._args = (model, presets, nside, freq_ghz, unit, cancel)
        self._id = request_id

    def run(self):
        model, presets, nside, freq_ghz, unit, cancel = self._args
        try:
            maps = model.emission(presets, nside, freq_ghz, unit, cancel)
        except Cancelled:
            return  # the page already moved on; nothing to report
        except Exception as exc:  # shown in the status line, not a crash
            self.signals.failed.emit(self._id, f"{type(exc).__name__}: {exc}")
        else:
            self.signals.done.emit(self._id, maps)


class SkyPage(QWidget):
    """Full-sky map with frequency, component and display controls."""

    pixel_selected = pyqtSignal(float, float)  # lon, lat in degrees

    def __init__(self):
        super().__init__()
        self._model = SkyModel()
        self._registry = load_registry()
        self._maps: np.ndarray | None = None
        self._request_id = 0
        self._cancel = threading.Event()
        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._debounce.timeout.connect(self._request_maps)
        self._init_ui()
        self._request_maps()

    # ---- UI construction -------------------------------------------------

    def _init_ui(self):
        self.canvas = MapCanvas()
        self.canvas.pixel_clicked.connect(self._on_pixel_clicked)
        self.status = QLabel("Ready")
        self.progress = QProgressBar()
        self.progress.setRange(0, 0)  # indeterminate: PySM3 reports no progress
        self.progress.setTextVisible(False)
        self.progress.setFixedWidth(160)
        self.stop_button = QPushButton("Stop")
        self.stop_button.setToolTip("Stop computing. A preset already in progress finishes in the background.")
        self.stop_button.clicked.connect(self._stop)
        self.busy = QWidget()  # progress bar + stop button, shown while computing
        busy_row = QHBoxLayout(self.busy)
        busy_row.setContentsMargins(0, 0, 0, 0)
        busy_row.addWidget(self.progress)
        busy_row.addWidget(self.stop_button)
        self.busy.hide()

        root = QVBoxLayout(self)
        root.addWidget(self.canvas, stretch=1)
        root.addLayout(self._build_frequency_row())
        controls = QHBoxLayout()
        controls.addWidget(self._build_components_box(), stretch=2)
        controls.addWidget(self._build_display_box(), stretch=1)
        root.addLayout(controls)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, stretch=1)
        status_row.addWidget(self.busy)
        root.addLayout(status_row)

    def _build_frequency_row(self) -> QHBoxLayout:
        self.freq_slider = QSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setRange(0, SLIDER_STEPS)
        self.freq_slider.setValue(ghz_to_slider(353))
        self.freq_label = QLabel()
        self.freq_label.setMinimumWidth(90)
        self.freq_slider.valueChanged.connect(self._on_frequency_changed)
        self._update_freq_label()
        row = QHBoxLayout()
        row.addWidget(QLabel("Frequency"))
        row.addWidget(self.freq_slider, stretch=1)
        row.addWidget(self.freq_label)
        return row

    def _build_components_box(self) -> QGroupBox:
        box = QGroupBox("Components")
        grid = QGridLayout(box)
        self._checks: dict[str, QCheckBox] = {}
        self._combos: dict[str, QComboBox] = {}
        by_key = {c.key: c for c in self._registry.components}
        for row, key in enumerate(COMPONENTS):
            component = by_key[key]
            check = QCheckBox(component.name)
            check.setChecked(key in DEFAULT_ENABLED)
            check.setToolTip(component.summary)
            combo = QComboBox()
            for preset in component.presets:
                label = f"{preset.name} (large download)" if is_large(preset.config) else preset.name
                combo.addItem(label, preset.name)
                combo.setItemData(combo.count() - 1, preset.summary, Qt.ItemDataRole.ToolTipRole)
            combo.setCurrentIndex(combo.findData(DEFAULT_PRESET[key]))
            check.toggled.connect(self._schedule)
            combo.currentIndexChanged.connect(self._schedule)
            grid.addWidget(check, row, 0)
            grid.addWidget(combo, row, 1)
            self._checks[key], self._combos[key] = check, combo
        grid.setColumnStretch(0, 1)
        return box

    def _build_display_box(self) -> QGroupBox:
        box = QGroupBox("Display")
        form = QGridLayout(box)
        self.stokes_combo = QComboBox()
        self.stokes_combo.addItems(STOKES)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(UNITS)
        self.stretch_combo = QComboBox()
        self.stretch_combo.addItems(["linear", "asinh"])
        self.nside_combo = QComboBox()
        for n in NSIDES:
            self.nside_combo.addItem(str(n), n)
        self.nside_combo.setCurrentIndex(NSIDES.index(DEFAULT_NSIDE))
        for row, (name, widget) in enumerate([
            ("Stokes", self.stokes_combo), ("Units", self.unit_combo),
            ("Stretch", self.stretch_combo), ("Nside", self.nside_combo),
        ]):
            form.addWidget(QLabel(name), row, 0)
            form.addWidget(widget, row, 1)
        # Display-only changes just redraw. Units and nside need new maps.
        self.stokes_combo.currentIndexChanged.connect(self._redraw)
        self.stretch_combo.currentIndexChanged.connect(self._redraw)
        self.unit_combo.currentIndexChanged.connect(self._schedule)
        self.nside_combo.currentIndexChanged.connect(self._schedule)
        return box

    # ---- state -----------------------------------------------------------

    def _active_presets(self) -> list[str]:
        return [self._combos[k].currentData() for k in COMPONENTS if self._checks[k].isChecked()]

    def _update_freq_label(self):
        self.freq_label.setText(f"{slider_to_ghz(self.freq_slider.value()):.1f} GHz")

    # ---- computing -------------------------------------------------------

    def _on_frequency_changed(self):
        self._update_freq_label()
        self._schedule()

    def _schedule(self, *_):
        self._debounce.start()

    def _request_maps(self):
        self._cancel.set()  # skip remaining work of any job this one supersedes
        self._cancel = threading.Event()
        self._request_id += 1
        self.status.clear()
        self.busy.show()
        job = _Job(
            self._request_id, self._model, self._active_presets(),
            self.nside_combo.currentData(), slider_to_ghz(self.freq_slider.value()),
            UNITS[self.unit_combo.currentText()], self._cancel,
        )
        job.signals.done.connect(self._on_maps_ready)
        job.signals.failed.connect(self._on_maps_failed)
        QThreadPool.globalInstance().start(job)

    def _on_maps_ready(self, request_id: int, maps: np.ndarray):
        if request_id != self._request_id:  # a newer request superseded this one
            return
        self._maps = maps
        self.busy.hide()
        self.status.setText("Click the map to pick a pixel.")
        self._redraw()

    def _on_maps_failed(self, request_id: int, message: str):
        if request_id == self._request_id:
            self.busy.hide()
            self.status.setText(f"Failed: {message}")

    def _stop(self):
        self._debounce.stop()  # also drop a request still waiting on the debounce
        self._cancel.set()
        self._request_id += 1  # any result from the cancelled job is now stale
        self.busy.hide()
        self.status.setText("Stopped. The map shows the previous settings.")

    # ---- drawing ---------------------------------------------------------

    def _redraw(self, *_):
        if self._maps is None:
            return
        stokes = self.stokes_combo.currentText()
        if stokes == "P":
            data = np.hypot(self._maps[1], self._maps[2])
        else:
            data = self._maps[STOKES.index(stokes)]
        unit = self.unit_combo.currentText()
        self.canvas.show_map(
            data, f"{stokes} [{unit}]",
            cmap="RdBu_r" if stokes in ("Q", "U") else "viridis",
            symmetric=stokes in ("Q", "U"),
            stretch=self.stretch_combo.currentText(),
        )

    def _on_pixel_clicked(self, lon: float, lat: float):
        value = self.canvas.value_at(lon, lat)
        unit = self.unit_combo.currentText()
        self.status.setText(f"l = {lon:.1f}°, b = {lat:.1f}°: {self.stokes_combo.currentText()} = {value:.4g} {unit}")
        self.pixel_selected.emit(lon, lat)
        self._redraw()
