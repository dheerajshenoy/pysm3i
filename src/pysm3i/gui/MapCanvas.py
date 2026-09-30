import healpy as hp
import numpy as np
from matplotlib import colors
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import pyqtSignal

XSIZE = 1000
ZOOM_XSIZE = 800
PROJECTIONS = {
    "Mollweide": hp.projector.MollweideProj,
    "Cartesian": hp.projector.CartesianProj,
    "Orthographic": hp.projector.OrthographicProj,  # two hemispheres side by side
}
ZOOM = "Zoom"  # gnomonic view centred on a chosen pixel
PROJECTION_NAMES = [*PROJECTIONS, ZOOM]


class MapCanvas(FigureCanvasQTAgg):
    """Projected view of a HEALPix map. Emits (lon, lat) in degrees on click."""

    pixel_clicked = pyqtSignal(float, float)

    def __init__(self, parent=None):
        super().__init__(Figure(figsize=(8, 4.5), layout="constrained"))
        self.setParent(parent)
        self._projectors: dict[str, hp.projector.SphericalProj] = {}
        self._projection = "Mollweide"
        self._fov_deg = 20.0
        self._zoom_center: tuple[float, float] | None = None  # None: use the picked pixel
        self._data: np.ndarray | None = None
        self._selected: tuple[float, float] | None = None
        self.last_limits: tuple[float, float] | None = None  # colour range of the last draw
        self.mpl_connect("button_press_event", self._on_press)

    def _projector(self, name: str | None = None):
        name = name or self._projection
        if name == ZOOM:
            lon, lat = self._zoom_center or (0.0, 0.0)
            key = (ZOOM, lon, lat, self._fov_deg)
            if key not in self._projectors:
                self._projectors = {k: v for k, v in self._projectors.items() if k[0] != ZOOM}
                self._projectors[key] = hp.projector.GnomonicProj(
                    rot=(lon, lat, 0.0), xsize=ZOOM_XSIZE, reso=self._fov_deg * 60 / ZOOM_XSIZE
                )
            return self._projectors[key]
        if name not in self._projectors:
            self._projectors[name] = PROJECTIONS[name](xsize=XSIZE)
        return self._projectors[name]

    def value_at(self, lon: float, lat: float) -> float | None:
        if self._data is None:
            return None
        nside = hp.npix2nside(self._data.size)
        return float(self._data[hp.ang2pix(nside, lon, lat, lonlat=True)])

    def set_selected(self, lon: float, lat: float):
        self._selected = (lon, lat)

    def show_map(self, data: np.ndarray, label: str, cmap: str,
                 symmetric: bool, stretch: str, projection: str = "Mollweide",
                 fov_deg: float = 20.0, limits: tuple[float, float] | None = None):
        """Draw `data` (one HEALPix map). `stretch` is 'linear' or 'asinh'.

        The zoom view centres on the picked pixel when you switch to it, and keeps
        that centre until you leave it or double-click somewhere else.
        """
        self._data = data
        self._projection = projection
        self._fov_deg = fov_deg
        if projection != ZOOM:
            self._zoom_center = None
        elif self._zoom_center is None:
            self._zoom_center = self._selected or (0.0, 0.0)
        projector = self._projector()
        nside = hp.npix2nside(data.size)
        image = projector.projmap(
            data, lambda x, y, z: hp.vec2pix(nside, x, y, z)
        )
        image = np.where(np.isfinite(image), image, np.nan)  # outside the map area

        finite = data[np.isfinite(data)]
        if limits is not None:  # fixed by the caller, e.g. to compare maps on one scale
            vmin, vmax = limits
        elif symmetric:
            vmax = float(np.percentile(np.abs(finite), 99)) or 1.0
            vmin = -vmax
        else:
            vmin, vmax = (float(v) for v in np.percentile(finite, [1, 99]))
            if vmin == vmax:
                vmax = vmin + 1.0
        self.last_limits = (vmin, vmax)
        if stretch == "asinh":
            norm = colors.AsinhNorm(linear_width=0.1 * (vmax - vmin), vmin=vmin, vmax=vmax)
        else:
            norm = colors.Normalize(vmin=vmin, vmax=vmax)

        self.figure.clear()
        ax = self.figure.add_subplot()
        shown = ax.imshow(image, origin="lower", extent=projector.get_extent(), cmap=cmap,
                          norm=norm, interpolation="nearest")
        ax.set_axis_off()
        ax.set_aspect("equal")
        if self._selected is not None:
            x, y = projector.ang2xy(*self._selected, lonlat=True)
            ax.plot(x, y, "+", color="k", markersize=14, markeredgewidth=2)
            ax.set_xlim(projector.get_extent()[:2])  # a marker off-screen must not rescale
            ax.set_ylim(projector.get_extent()[2:])
        self.figure.colorbar(shown, ax=ax, location="left",
                             fraction=0.025, shrink=0.6, pad=0.01, label=label)
        self.draw_idle()

    def _on_press(self, event):
        if event.inaxes is None or event.xdata is None or self._data is None:
            return
        with np.errstate(all="ignore"):  # NaN outside the map area is expected
            lon, lat = self._projector().xy2ang(event.xdata, event.ydata, lonlat=True)
        if not (np.isfinite(lon) and np.isfinite(lat)):
            return  # clicked outside the map area
        lon = float(lon) % 360
        self._selected = (lon, float(lat))
        if self._projection == ZOOM and event.dblclick:
            self._zoom_center = self._selected  # recentre the zoom on this point
        self.pixel_clicked.emit(lon, float(lat))
