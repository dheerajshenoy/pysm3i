import healpy as hp
import numpy as np
from matplotlib import colors
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import pyqtSignal

XSIZE = 1000
EXTENT = (-2.0, 2.0, -1.0, 1.0)  # Mollweide plane: x in [-2, 2], y in [-1, 1]


class MapCanvas(FigureCanvasQTAgg):
    """Mollweide view of a HEALPix map. Emits (lon, lat) in degrees on click."""

    pixel_clicked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(Figure(figsize=(8, 4.5), layout="constrained"))
        self.setParent(parent)
        self._projector = hp.projector.MollweideProj(xsize=XSIZE)
        self._data: np.ndarray | None = None
        self._selected: tuple[float, float] | None = None
        self.mpl_connect("button_press_event", self._on_press)

    def value_at(self, lon: float, lat: float) -> float | None:
        if self._data is None:
            return None
        nside = hp.npix2nside(self._data.size)
        return float(self._data[hp.ang2pix(nside, lon, lat, lonlat=True)])

    def set_selected(self, lon: float, lat: float):
        self._selected = (lon, lat)

    def show_map(self, data: np.ndarray, label: str, cmap: str,
                 symmetric: bool, stretch: str):
        """Draw `data` (one HEALPix map). `stretch` is 'linear' or 'asinh'."""
        self._data = data
        nside = hp.npix2nside(data.size)
        image = self._projector.projmap(
            data, lambda x, y, z: hp.vec2pix(nside, x, y, z)
        )
        image = np.where(np.isfinite(image), image, np.nan)  # outside the ellipse

        finite = data[np.isfinite(data)]
        if symmetric:
            vmax = float(np.percentile(np.abs(finite), 99)) or 1.0
            vmin = -vmax
        else:
            vmin, vmax = (float(v) for v in np.percentile(finite, [1, 99]))
            if vmin == vmax:
                vmax = vmin + 1.0
        if stretch == "asinh":
            norm = colors.AsinhNorm(linear_width=0.1 * (vmax - vmin), vmin=vmin, vmax=vmax)
        else:
            norm = colors.Normalize(vmin=vmin, vmax=vmax)

        self.figure.clear()
        ax = self.figure.add_subplot()
        shown = ax.imshow(image, origin="lower", extent=EXTENT, cmap=cmap,
                          norm=norm, interpolation="nearest")
        ax.set_axis_off()
        ax.set_aspect("equal")
        if self._selected is not None:
            x, y = self._projector.ang2xy(*self._selected, lonlat=True)
            ax.plot(x, y, "+", color="k", markersize=14, markeredgewidth=2)
        self.figure.colorbar(shown, ax=ax, location="left",
                             fraction=0.025, shrink=0.6, pad=0.01, label=label)
        self.draw_idle()

    def _on_press(self, event):
        if event.inaxes is None or event.xdata is None or self._data is None:
            return
        x, y = event.xdata, event.ydata
        if (x / 2) ** 2 + y**2 > 1:  # outside the Mollweide ellipse
            return
        lon, lat = self._projector.xy2ang(x, y, lonlat=True)
        if not (np.isfinite(lon) and np.isfinite(lat)):
            return
        lon = float(lon) % 360
        self._selected = (lon, float(lat))
        self.pixel_clicked.emit(lon, float(lat))
