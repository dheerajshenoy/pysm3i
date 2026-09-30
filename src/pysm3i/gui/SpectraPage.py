import threading

import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget,
)

from pysm3i.core.spectra import SPECTRA, SpectraModel
from pysm3i.models import load_registry
from .BusyBar import BusyBar
from .ScaleControls import ScaleControls
from .jobs import Job

NSIDES = [16, 32, 64, 128, 256, 512]
DEFAULT_NSIDE = 128
B_CUTS_DEG = [0, 20, 30, 40, 60]


def fsky(b_cut_deg: float) -> float:
    """Fraction of the sphere with |b| > b_cut, before the mask edge is smoothed."""
    return 1.0 - np.sin(np.radians(b_cut_deg))


def fsky_label(b_cut_deg: float) -> str:
    cut = "full sky" if b_cut_deg == 0 else f"|b| > {b_cut_deg:g}°"
    return f"{fsky(b_cut_deg):.2f} ({cut})"


FSKY_CHOICES = {fsky_label(b): float(b) for b in B_CUTS_DEG}  # label -> latitude cut in degrees
DEFAULT_FSKY = fsky_label(30)
REFERENCE_PRESET = "c1"  # lensed CMB, drawn when no CMB component is active
N_BINS = 24
DEBOUNCE_MS = 250


def log_bins(lmax: int) -> np.ndarray:
    """Integer bin edges from ell = 2, roughly logarithmic."""
    return np.unique(np.geomspace(2, lmax + 1, N_BINS + 1).astype(int))


def bin_spectrum(dl: np.ndarray, edges: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Mean ell and mean D_ell in each bin."""
    ell = np.arange(dl.size)
    centres, values = [], []
    for low, high in zip(edges[:-1], edges[1:]):
        sel = (ell >= low) & (ell < high)
        if sel.any():
            centres.append(ell[sel].mean())
            values.append(dl[sel].mean())
    return np.array(centres), np.array(values)


class SpectraPage(QWidget):
    """Angular power spectra of the active components, compared with the CMB."""

    def __init__(self, model: SpectraModel, get_presets):
        super().__init__()
        self._model = model
        self._get_presets = get_presets  # callable returning the active preset names
        self._registry = load_registry()
        self._result = None
        self._request_id = 0
        self._cancel = threading.Event()
        self._dirty = True  # recompute the next time the page is shown
        self._debounce = QTimer(self, singleShot=True, interval=DEBOUNCE_MS)
        self._debounce.timeout.connect(self._request)
        self._init_ui()

    # ---- UI --------------------------------------------------------------

    def _init_ui(self):
        self.canvas = FigureCanvasQTAgg(Figure(figsize=(8, 5), layout="constrained"))
        self.spectrum_combo = QComboBox()
        self.spectrum_combo.addItems(SPECTRA)
        self.spectrum_combo.setCurrentText("BB")
        self.freq = QDoubleSpinBox()
        self.freq.setRange(10.0, 1000.0)
        self.freq.setDecimals(1)
        self.freq.setSuffix(" GHz")
        self.freq.setValue(100.0)
        self.fsky_combo = QComboBox()
        self.fsky_combo.addItems(FSKY_CHOICES)
        self.fsky_combo.setToolTip("Fraction of the sky kept by a Galactic latitude cut, before the mask edge is smoothed")
        self.fsky_combo.setCurrentText(DEFAULT_FSKY)
        self.nside_combo = QComboBox()
        for n in NSIDES:
            self.nside_combo.addItem(str(n), n)
        self.nside_combo.setCurrentIndex(NSIDES.index(DEFAULT_NSIDE))
        self.status = QLabel()
        self.busy = BusyBar()
        self.busy.stop_requested.connect(self._stop)
        note = QLabel(
            "Pseudo-C_ℓ with an apodized Galactic mask, divided by the mean squared mask. "
            "Mode coupling is ignored, so low multipoles are approximate."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")

        self.scales = ScaleControls()
        self.scales.changed.connect(self._redraw)
        self.spectrum_combo.currentIndexChanged.connect(self._redraw)
        self.freq.valueChanged.connect(self._schedule)
        self.fsky_combo.currentIndexChanged.connect(self._schedule)
        self.nside_combo.currentIndexChanged.connect(self._schedule)

        controls = QHBoxLayout()
        for text, widget in [("Spectrum", self.spectrum_combo), ("Frequency", self.freq),
                             ("f_sky", self.fsky_combo), ("Nside", self.nside_combo)]:
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
        root.addWidget(note)
        root.addLayout(status_row)

    # ---- inputs from other pages ----------------------------------------

    def invalidate(self):
        """The active presets changed elsewhere."""
        self._dirty = True
        if self.isVisible():
            self._schedule()

    def showEvent(self, event):
        super().showEvent(event)
        if self._dirty:
            self._schedule()

    # ---- computing -------------------------------------------------------

    def _schedule(self, *_):
        self._dirty = True
        self._debounce.start()

    def _reference(self, presets: list[str]) -> str | None:
        has_cmb = any(self._registry[p].component == "cmb" for p in presets)
        return None if has_cmb else REFERENCE_PRESET

    def _request(self):
        self._cancel.set()  # skip remaining work of any job this one supersedes
        self._cancel = threading.Event()
        presets = self._get_presets()
        self._request_id += 1
        self.status.clear()
        self.busy.show()
        model, cancel = self._model, self._cancel
        nside = self.nside_combo.currentData()
        freq = self.freq.value()
        b_cut = FSKY_CHOICES[self.fsky_combo.currentText()]
        reference = self._reference(presets)
        job = Job(self._request_id,
                  lambda: model.spectra(presets, nside, freq, b_cut, reference, cancel))
        job.signals.done.connect(self._on_ready)
        job.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(job)

    def _on_ready(self, request_id: int, result):
        if request_id != self._request_id:
            return
        self._result = result
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
        result = self._result
        self.canvas.figure.clear()
        ax = self.canvas.figure.add_subplot()
        if result is None or not result.curves:
            ax.text(0.5, 0.5, "Enable components on the Sky page", ha="center",
                    va="center", transform=ax.transAxes)
            ax.set_axis_off()
            self.canvas.draw_idle()
            return

        index = SPECTRA.index(self.spectrum_combo.currentText())
        name = SPECTRA[index]
        edges = log_bins(result.ell[-1])

        def plot(dl, **style) -> bool:
            if not dl[index].any():  # e.g. free-free has no polarization
                return False
            ax.plot(*bin_spectrum(dl[index], edges), **style)
            return True

        empty = []
        for preset, dl in result.curves.items():
            label = f"{self._component_name(preset)} ({preset})"
            if not plot(dl, marker="o", markersize=3, linewidth=2, label=label):
                empty.append(label)
        if result.total is not None:
            plot(result.total, color="k", linestyle="--", linewidth=1.5, label="Total")
        if result.reference is not None:
            plot(result.reference, color="gray", linestyle=":", linewidth=2,
                 label="Lensed CMB (c1)")
        self.status.setText(f"No {name} emission: {', '.join(empty)}" if empty else "")

        ax.set_xlabel(r"Multipole $\ell$")
        ax.set_ylabel(rf"$D_\ell^{{{name}}} = \ell(\ell+1)C_\ell/2\pi\ \ [\mu K_{{CMB}}^2]$")
        ax.set_title(f"{name} power spectrum at {self.freq.value():.0f} GHz, "
                     f"f_sky = {fsky(FSKY_CHOICES[self.fsky_combo.currentText()]):.2f} (nside {self.nside_combo.currentData()})")
        self.scales.apply(ax)
        ax.grid(True, which="both", alpha=0.3)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=9)
        self.canvas.draw_idle()

    def _component_name(self, preset: str) -> str:
        key = self._registry[preset].component
        return next(c.name for c in self._registry.components if c.key == key)
