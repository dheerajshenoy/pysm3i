import healpy as hp
import numpy as np
import pysm3.units as u
from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PyQt6.QtCore import Qt, QThreadPool, QTimer
from PyQt6.QtWidgets import (
    QCheckBox, QComboBox, QGroupBox, QHBoxLayout, QLabel, QPushButton, QScrollArea,
    QSizePolicy, QSlider, QSplitter, QVBoxLayout, QWidget,
)

from pysm3i.core.playground import (
    COMPONENTS, DEFAULTS, PARAMETERS, TEMPLATE_PRESET, component_maps, load_templates,
    model_preset, pixel_spectra,
)
from pysm3i.core.skymodel import UNITS
from pysm3i.models import load_registry
from .BusyBar import BusyBar
from .MapCanvas import MapCanvas
from .ParamSlider import ParamSlider
from .ScaleControls import ScaleControls
from .jobs import Job

NSIDE = 64
SED_FREQS_GHZ = np.logspace(1, 3, 80)
FREQ_MIN_LOG, FREQ_MAX_LOG, SLIDER_STEPS = 1.0, 3.0, 1000
DEFAULT_FREQ_GHZ = 100.0
DEFAULT_PIXEL = (0.0, 45.0)  # l, b in degrees
STOKES = ["I", "Q", "U", "P"]
UPDATE_DELAY_MS = 15  # coalesces the many events of a slider drag into one redraw
CURVE_COLORS = {"dust": "tab:blue", "synchrotron": "tab:orange", "free_free": "tab:green"}


def slider_to_ghz(value: int) -> float:
    return 10 ** (FREQ_MIN_LOG + (FREQ_MAX_LOG - FREQ_MIN_LOG) * value / SLIDER_STEPS)


def ghz_to_slider(freq: float) -> int:
    return round((np.log10(freq) - FREQ_MIN_LOG) / (FREQ_MAX_LOG - FREQ_MIN_LOG) * SLIDER_STEPS)


def describe(component: str, params: dict[str, float]) -> str:
    """The component's current parameter values, for the legend."""
    if component == "dust":
        return f"β_d = {params['beta_d']:.2f}, T_d = {params['temp_d']:.1f} K"
    if component == "synchrotron":
        curvature = f", C = {params['curv_s']:.3f}" if params["curv_s"] else ""
        return f"β_s = {params['beta_s']:.2f}{curvature}"
    return f"β_ff = {params['beta_ff']:.2f}"


class PlaygroundPage(QWidget):
    """Change spectral parameters and watch the sky and the spectrum respond."""

    def __init__(self):
        super().__init__()
        self._templates = None
        self._loading = False
        self._registry = load_registry()
        self._params = dict(DEFAULTS)
        self._enabled = {component: True for component in COMPONENTS}
        self._pixel_lonlat = DEFAULT_PIXEL
        self._locked_limits: tuple[float, float] | None = None
        self._timer = QTimer(self, singleShot=True, interval=UPDATE_DELAY_MS)
        self._timer.timeout.connect(self._update)
        self._init_ui()

    # ---- UI --------------------------------------------------------------

    def _init_ui(self):
        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(self._build_parameter_panel())
        splitter.addWidget(self._build_views())
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _build_parameter_panel(self) -> QScrollArea:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        intro = QLabel("Move a slider to change a model's spectral parameters. "
                       "Untick a component to leave it out.")
        intro.setWordWrap(True)
        intro.setStyleSheet("color: gray;")
        layout.addWidget(intro)

        self._sliders: dict[str, ParamSlider] = {}
        self._groups: dict[str, QGroupBox] = {}
        self._model_labels: dict[str, QLabel] = {}
        for component, title in COMPONENTS.items():
            group = QGroupBox(title)
            group.setCheckable(True)
            group.setChecked(True)
            group.toggled.connect(lambda on, c=component: self._on_component_toggled(c, on))
            box = QVBoxLayout(group)
            model_label = QLabel()  # which PySM3 model this is, kept up to date in _update_model_names
            model_label.setStyleSheet("color: gray;")
            model_label.setWordWrap(True)
            box.addWidget(model_label)
            self._model_labels[component] = model_label
            for parameter in (p for p in PARAMETERS if p.component == component):
                slider = ParamSlider(parameter)
                slider.changed.connect(self._on_parameter_changed)
                box.addWidget(slider)
                self._sliders[parameter.key] = slider
            reset = QPushButton("Reset")
            reset.setToolTip("Back to the PySM3 preset values")
            reset.clicked.connect(lambda _=False, c=component: self._reset(c))
            box.addWidget(reset, alignment=Qt.AlignmentFlag.AlignRight)
            layout.addWidget(group)
            self._groups[component] = group

        reset_all = QPushButton("Reset all")
        reset_all.clicked.connect(lambda: self._reset(None))
        layout.addWidget(reset_all)
        layout.addStretch(1)
        self._update_model_names()

        scroll = QScrollArea()
        scroll.setWidget(panel)
        scroll.setWidgetResizable(True)
        scroll.setMinimumWidth(330)
        scroll.setMaximumWidth(420)
        return scroll

    def _build_views(self) -> QWidget:
        self.map_canvas = MapCanvas()
        self.map_canvas.pixel_clicked.connect(self._on_pixel_clicked)
        self.map_canvas.set_selected(*DEFAULT_PIXEL)
        self.sed_canvas = FigureCanvasQTAgg(Figure(figsize=(8, 4), layout="constrained"))

        self.freq_slider = QSlider(Qt.Orientation.Horizontal)
        self.freq_slider.setRange(0, SLIDER_STEPS)
        self.freq_slider.setValue(ghz_to_slider(DEFAULT_FREQ_GHZ))
        self.freq_slider.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.freq_label = QLabel()
        self.freq_label.setMinimumWidth(90)
        self.stokes_combo = QComboBox()
        self.stokes_combo.addItems(STOKES)
        self.unit_combo = QComboBox()
        self.unit_combo.addItems(UNITS)
        self.stretch_combo = QComboBox()
        self.stretch_combo.addItems(["linear", "asinh"])
        self.lock_check = QCheckBox("Lock colour scale")
        self.lock_check.setChecked(True)
        self.lock_check.setToolTip("Keep the colour range fixed while you change parameters, "
                                   "so brightness changes stay visible")
        self.defaults_check = QCheckBox("Show preset curves")
        self.defaults_check.setChecked(True)
        self.defaults_check.setToolTip("Draw the spectra for the PySM3 preset values as thin dotted lines")
        self.scales = ScaleControls()
        self.status = QLabel("")
        self.busy = BusyBar()
        self.busy.stop_button.hide()  # loading the templates cannot be cancelled usefully

        self.freq_slider.valueChanged.connect(self._on_view_setting_changed)
        self.stokes_combo.currentIndexChanged.connect(self._on_view_setting_changed)
        self.unit_combo.currentIndexChanged.connect(self._on_view_setting_changed)
        self.stretch_combo.currentIndexChanged.connect(self._schedule)
        self.lock_check.toggled.connect(self._on_view_setting_changed)
        self.defaults_check.toggled.connect(self._schedule)
        self.scales.changed.connect(self._schedule)
        self._update_freq_label()

        top = QHBoxLayout()
        top.addWidget(QLabel("Frequency"))
        top.addWidget(self.freq_slider, stretch=1)
        top.addWidget(self.freq_label)
        options = QHBoxLayout()
        for text, widget in (("Stokes", self.stokes_combo), ("Units", self.unit_combo),
                             ("Stretch", self.stretch_combo)):
            options.addWidget(QLabel(text))
            options.addWidget(widget)
        options.addWidget(self.lock_check)
        options.addStretch(1)
        sed_options = QHBoxLayout()
        sed_options.addWidget(self.defaults_check)
        sed_options.addStretch(1)
        sed_options.addWidget(self.scales)
        status_row = QHBoxLayout()
        status_row.addWidget(self.status, stretch=1)
        status_row.addWidget(self.busy)

        views = QWidget()
        layout = QVBoxLayout(views)
        layout.addLayout(top)
        layout.addWidget(self.map_canvas, stretch=3)
        layout.addLayout(options)
        layout.addWidget(self.sed_canvas, stretch=2)
        layout.addLayout(sed_options)
        layout.addLayout(status_row)
        return views

    # ---- loading ---------------------------------------------------------

    def showEvent(self, event):
        super().showEvent(event)
        if self._templates is None and not self._loading:
            self._loading = True
            self.status.setText("Loading template maps…")
            self.busy.show()
            job = Job(0, lambda: load_templates(NSIDE))
            job.signals.done.connect(self._on_loaded)
            job.signals.failed.connect(self._on_load_failed)
            QThreadPool.globalInstance().start(job)

    def _on_loaded(self, _request_id: int, templates):
        self._templates = templates
        self._loading = False
        self.busy.hide()
        self.status.clear()
        self._update()

    def _on_load_failed(self, _request_id: int, message: str):
        self._loading = False
        self.busy.hide()
        self.status.setText(f"Could not load the template maps: {message}")

    # ---- reacting to controls --------------------------------------------

    def _on_parameter_changed(self, key: str, value: float):
        self._params[key] = value
        self._update_model_names()
        self._schedule()

    def _model_title(self, component: str) -> str:
        """Name of the model in use, e.g. 'Modified blackbody'."""
        preset = self._registry[model_preset(component, self._params)]
        return self._registry.equations_for(preset)[0].title

    def _update_model_names(self):
        for component, label in self._model_labels.items():
            label.setText(f"{self._model_title(component)} · template from {TEMPLATE_PRESET[component]}")

    def _on_component_toggled(self, component: str, on: bool):
        self._enabled[component] = on
        self._locked_limits = None  # the brightness range is about to change
        self._schedule()

    def _on_view_setting_changed(self, *_):
        self._locked_limits = None  # a new frequency, Stokes or unit needs a new range
        self._update_freq_label()
        self._schedule()

    def _on_pixel_clicked(self, lon: float, lat: float):
        self._pixel_lonlat = (lon, lat)
        self._schedule()

    def _reset(self, component: str | None):
        for parameter in PARAMETERS:
            if component is None or parameter.component == component:
                self._sliders[parameter.key].set_value(parameter.default, emit=False)
                self._params[parameter.key] = parameter.default
        self._update_model_names()
        self._schedule()

    def _update_freq_label(self):
        self.freq_label.setText(f"{slider_to_ghz(self.freq_slider.value()):.1f} GHz")

    def _schedule(self, *_):
        self._timer.start()

    # ---- drawing ---------------------------------------------------------

    def _unit(self):
        label = self.unit_combo.currentText()
        return label, u.Unit(UNITS[label])

    def _select(self, iqu: np.ndarray) -> np.ndarray:
        """The chosen Stokes parameter from an (3, ...) array, as a positive quantity for P."""
        stokes = self.stokes_combo.currentText()
        if stokes == "P":
            return np.hypot(iqu[1], iqu[2])
        return iqu[STOKES.index(stokes)]

    def _update(self):
        if self._templates is None:
            return
        freq = slider_to_ghz(self.freq_slider.value())
        unit_label, unit = self._unit()
        self._draw_map(freq, unit_label, unit)
        self._draw_sed(freq, unit_label, unit)

    def _draw_map(self, freq: float, unit_label: str, unit):
        maps = component_maps(self._templates, self._params, self._enabled, freq)
        total = sum(maps.values()) if maps else np.zeros((3, 12 * NSIDE**2))
        # the conversion is linear, so one factor converts the whole map
        factor = (1.0 * u.uK_RJ).to(unit, u.cmb_equivalencies(freq * u.GHz)).value
        stokes = self.stokes_combo.currentText()
        use_lock = self.lock_check.isChecked() and self._locked_limits is not None
        self.map_canvas.show_map(
            self._select(total) * factor, f"{stokes} [{unit_label}]",
            cmap="RdBu_r" if stokes in ("Q", "U") else "viridis",
            symmetric=stokes in ("Q", "U"),
            stretch=self.stretch_combo.currentText(),
            limits=self._locked_limits if use_lock else None,
        )
        if self.lock_check.isChecked() and self._locked_limits is None:
            self._locked_limits = self.map_canvas.last_limits
        lon, lat = self._pixel_lonlat
        value = self.map_canvas.value_at(lon, lat)
        self.status.setText(f"l = {lon:.1f}°, b = {lat:.1f}°: {stokes} = {value:.4g} {unit_label}")

    def _draw_sed(self, freq: float, unit_label: str, unit):
        pixel = int(hp.ang2pix(NSIDE, *self._pixel_lonlat, lonlat=True))
        conversion = (np.ones(SED_FREQS_GHZ.size) * u.uK_RJ).to(
            unit, u.cmb_equivalencies(SED_FREQS_GHZ * u.GHz)).value
        current = pixel_spectra(self._templates, self._params, self._enabled, pixel, SED_FREQS_GHZ)
        stokes = self.stokes_combo.currentText()

        figure = self.sed_canvas.figure
        figure.clear()
        ax = figure.add_subplot()
        if not current:
            ax.text(0.5, 0.5, "Tick a component to see its spectrum", ha="center",
                    va="center", transform=ax.transAxes)
            ax.set_axis_off()
            self.sed_canvas.draw_idle()
            return

        def curve(iqu):
            return np.abs(self._select(iqu)) * conversion

        if self.defaults_check.isChecked():
            reference = pixel_spectra(self._templates, DEFAULTS, self._enabled, pixel, SED_FREQS_GHZ)
            for component, iqu in reference.items():
                ax.plot(SED_FREQS_GHZ, curve(iqu), ":", color=CURVE_COLORS[component],
                        linewidth=1, alpha=0.7)
        for component, iqu in current.items():
            y = curve(iqu)
            if y.any():  # e.g. free-free has no polarization
                ax.plot(SED_FREQS_GHZ, y, color=CURVE_COLORS[component], linewidth=2,
                        label=f"{COMPONENTS[component]} ({self._model_title(component).lower()}): "
                              f"{describe(component, self._params)}")
        if len(current) > 1:
            ax.plot(SED_FREQS_GHZ, curve(sum(current.values())), "k--", linewidth=1.5, label="Total")
        ax.axvline(freq, color="gray", linewidth=1, alpha=0.6)
        self.scales.apply(ax)
        ax.set_xlabel("Frequency [GHz]")
        ax.set_ylabel(f"{'P' if stokes == 'P' else '|' + stokes + '|'} [{unit_label}]")
        lon, lat = self._pixel_lonlat
        ax.set_title(f"Spectrum at l = {lon:.1f}°, b = {lat:.1f}°", fontsize=10)
        ax.grid(True, which="both", alpha=0.3)
        if ax.get_legend_handles_labels()[0]:
            ax.legend(fontsize=8)
        self.sed_canvas.draw_idle()
