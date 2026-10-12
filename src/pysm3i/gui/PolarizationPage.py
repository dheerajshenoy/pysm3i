import healpy as hp
import numpy as np
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import QThreadPool
from PyQt6.QtWidgets import QCheckBox, QComboBox, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from pysm3i.core.polarization import eb_maps
from .BusyBar import BusyBar
from .MapCanvas import PROJECTIONS
from .jobs import Job

PANEL_XSIZE = 600  # four maps share the figure, so each can be coarser than the main map
PERCENTILE = 99


class PolarizationPage(QWidget):
    """Q, U, E and B maps of the map currently shown on the Sky page."""

    def __init__(self, get_snapshot):
        super().__init__()
        self._get_snapshot = get_snapshot  # callable returning the Sky page's SkySnapshot
        self._source: np.ndarray | None = None  # the (I, Q, U) array the E/B maps came from
        self._maps: dict[str, np.ndarray] = {}  # "Q", "U", "E", "B"
        self._snapshot = None
        self._request_id = 0
        self._projectors: dict[str, object] = {}
        self._init_ui()

    # ---- UI --------------------------------------------------------------

    def _init_ui(self):
        self.canvas = FigureCanvasQTAgg(Figure(figsize=(10, 6), layout="constrained"))
        self.projection_combo = QComboBox()
        self.projection_combo.addItems(PROJECTIONS)
        self.common_check = QCheckBox("Common colour scale")
        self.common_check.setToolTip("Use one colour range for all four maps. Off: Q and U share "
                                     "a range, while E and B each get their own.")
        self.summary = QLabel()
        self.status = QLabel()
        self.busy = BusyBar()
        self.busy.stop_requested.connect(self._stop)
        note = QLabel(
            "E and B are computed from Q and U on the full sky. E is the curl-free part of the "
            "polarization pattern and B the curl part. Gradients of a scalar field make only E."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")

        self.projection_combo.currentIndexChanged.connect(self._redraw)
        self.common_check.toggled.connect(self._redraw)

        controls = QHBoxLayout()
        controls.addWidget(QLabel("Projection"))
        controls.addWidget(self.projection_combo)
        controls.addWidget(self.common_check)
        controls.addStretch(1)
        controls.addWidget(self.summary)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, stretch=1)
        status_row.addWidget(self.busy)

        root = QVBoxLayout(self)
        root.addLayout(controls)
        root.addWidget(self.canvas, stretch=1)
        root.addWidget(note)
        root.addLayout(status_row)

    # ---- following the Sky page ------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def on_sky_maps_changed(self):
        """New Sky-page maps. Only recompute if we are on screen: E/B is costly at high nside."""
        if self.isVisible():
            self.refresh()

    def refresh(self):
        """Recompute E and B if the Sky page's maps are not the ones shown."""
        snapshot = self._get_snapshot()
        if snapshot is None:
            self._snapshot, self._source, self._maps = None, None, {}
            self.summary.clear()
            self.busy.hide()
            self._redraw()
            return
        if snapshot.maps is self._source:
            return  # already showing these maps
        self._snapshot = snapshot
        self._request_id += 1
        self.status.clear()
        self.busy.show()
        maps = snapshot.maps
        job = Job(self._request_id, lambda: eb_maps(maps))
        job.signals.done.connect(self._on_ready)
        job.signals.failed.connect(self._on_failed)
        QThreadPool.globalInstance().start(job)

    def _on_ready(self, request_id: int, result):
        if request_id != self._request_id:  # superseded or stopped
            return
        e_map, b_map = result
        iqu = self._snapshot.maps
        self._source = iqu
        self._maps = {"Q": iqu[1], "U": iqu[2], "E": e_map, "B": b_map}
        self.busy.hide()
        snapshot = self._snapshot
        self.summary.setText(f"{', '.join(snapshot.presets)} at {snapshot.freq_ghz:.1f} GHz, "
                             f"nside {snapshot.nside}")
        self._redraw()

    def _on_failed(self, request_id: int, message: str):
        if request_id == self._request_id:
            self.busy.hide()
            self.status.setText(f"Failed: {message}")

    def _stop(self):
        self._request_id += 1  # a late result is now stale
        self.busy.hide()
        self.status.setText("Stopped. Open the page again to recompute.")

    # ---- drawing ---------------------------------------------------------

    def _projector(self, name: str):
        if name not in self._projectors:
            self._projectors[name] = PROJECTIONS[name](xsize=PANEL_XSIZE)
        return self._projectors[name]

    @staticmethod
    def _limit(*maps: np.ndarray) -> float:
        values = np.abs(np.concatenate([m[np.isfinite(m)] for m in maps]))
        return float(np.percentile(values, PERCENTILE)) or 1.0

    def _redraw(self, *_):
        figure = self.canvas.figure
        figure.clear()
        if not self._maps:
            ax = figure.add_subplot()
            ax.text(0.5, 0.5, "Enable a component on the Sky page and let its map finish computing",
                    ha="center", va="center", transform=ax.transAxes)
            ax.set_axis_off()
            self.canvas.draw_idle()
            return

        unit = self._snapshot.unit_label
        projector = self._projector(self.projection_combo.currentText())
        nside = hp.npix2nside(self._maps["Q"].size)
        axes = figure.subplots(2, 2)
        panels = [("Q", axes[0, 0]), ("U", axes[0, 1]), ("E", axes[1, 0]), ("B", axes[1, 1])]

        if self.common_check.isChecked():
            limits = {name: self._limit(*self._maps.values()) for name, _ in panels}
        else:
            qu = self._limit(self._maps["Q"], self._maps["U"])
            limits = {"Q": qu, "U": qu, "E": self._limit(self._maps["E"]),
                      "B": self._limit(self._maps["B"])}

        images = {}
        for name, ax in panels:
            data = self._maps[name]
            image = projector.projmap(data, lambda x, y, z: hp.vec2pix(nside, x, y, z))
            image = np.where(np.isfinite(image), image, np.nan)  # outside the map area
            images[name] = ax.imshow(
                image, origin="lower", extent=projector.get_extent(), cmap="RdBu_r",
                vmin=-limits[name], vmax=limits[name], interpolation="nearest",
            )
            ax.set_axis_off()
            ax.set_aspect("equal")
            rms = float(np.sqrt(np.mean(data**2)))
            ax.set_title(f"{name}   (rms {rms:.3g} {unit})", fontsize=10)

        if self.common_check.isChecked():
            figure.colorbar(images["Q"], ax=axes.ravel().tolist(), location="right",
                            shrink=0.7, label=f"[{unit}]")
        else:
            figure.colorbar(images["U"], ax=list(axes[0]), location="right", shrink=0.85, label=f"Q, U [{unit}]")
            figure.colorbar(images["E"], ax=axes[1, 0], location="right", shrink=0.85, label=f"E [{unit}]")
            figure.colorbar(images["B"], ax=axes[1, 1], location="right", shrink=0.85, label=f"B [{unit}]")
        self.canvas.draw_idle()
