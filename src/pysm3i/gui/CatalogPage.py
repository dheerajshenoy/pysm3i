from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView, QFormLayout, QHeaderView, QLabel, QLineEdit, QPushButton,
    QSplitter, QTableWidget, QTableWidgetItem, QTreeWidget, QTreeWidgetItem,
    QVBoxLayout, QWidget,
)

from pysm3i.models import Equation, Preset, load_registry
from .equations import latex_to_pixmap

ROLE_KIND = Qt.ItemDataRole.UserRole  # "component" or "preset"
ROLE_KEY = Qt.ItemDataRole.UserRole + 1  # component key or preset name


def flatten(config: dict, prefix: str = "") -> list[tuple[str, str]]:
    """Rows for the parameter table. Nested configs (d4, a1, a2) get a prefix."""
    rows = []
    for key, value in config.items():
        if isinstance(value, dict):
            rows += flatten(value, f"{prefix}{key}.")
        else:
            rows.append((f"{prefix}{key}", str(value)))
    return rows


class CatalogPage(QWidget):
    """Browse every PySM3 preset with its description and parameters."""

    show_on_sky = pyqtSignal(str)  # preset name

    def __init__(self, can_show_on_sky=lambda name: False):
        super().__init__()
        self._registry = load_registry()
        self._can_show_on_sky = can_show_on_sky
        self._current: Preset | None = None
        self._init_ui()
        self._fill_tree()
        self.tree.setCurrentItem(self.tree.topLevelItem(0).child(0))

    # ---- UI --------------------------------------------------------------

    def _init_ui(self):
        self.search = QLineEdit(placeholderText="Filter by name or description…", clearButtonEnabled=True)
        self.search.textChanged.connect(self._apply_filter)
        self.tree = QTreeWidget()
        self.tree.setHeaderHidden(True)
        self.tree.currentItemChanged.connect(self._on_selection_changed)

        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.addWidget(self.search)
        left_layout.addWidget(self.tree)

        splitter = QSplitter(Qt.Orientation.Horizontal)
        splitter.addWidget(left)
        splitter.addWidget(self._build_detail())
        splitter.setStretchFactor(0, 1)
        splitter.setStretchFactor(1, 3)
        layout = QVBoxLayout(self)
        layout.addWidget(splitter)

    def _build_detail(self) -> QWidget:
        self.title = QLabel()
        self.title.setStyleSheet("font-size: 18px; font-weight: bold;")
        self.summary = self._wrapped_label()
        self.note = self._wrapped_label()
        self.note.setStyleSheet("color: #b45309;")
        self.reference = self._wrapped_label()
        self.variation = self._wrapped_label()
        self.sed_class = self._wrapped_label()
        self.sed = self._wrapped_label()
        self.form = QFormLayout()
        self.form.addRow("SED model:", self.sed)
        self.form.addRow("PySM3 class:", self.sed_class)
        self.form.addRow("Spatial variation:", self.variation)
        self.form.addRow("Reference:", self.reference)

        self.params = QTableWidget(0, 2)
        self.params.setHorizontalHeaderLabels(["Parameter", "Value"])
        self.params.verticalHeader().hide()
        self.params.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.params.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        header = self.params.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.params_title = QLabel("Configuration")
        self.params_title.setStyleSheet("font-weight: bold;")

        self.equation_box = QVBoxLayout()  # rebuilt for each selected preset

        self.sky_button = QPushButton("Show on sky")
        self.sky_button.clicked.connect(lambda: self.show_on_sky.emit(self._current.name))

        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.addWidget(self.title)
        layout.addWidget(self.summary)
        layout.addWidget(self.note)
        layout.addLayout(self.form)
        layout.addLayout(self.equation_box)
        layout.addWidget(self.sky_button, alignment=Qt.AlignmentFlag.AlignLeft)
        layout.addWidget(self.params_title)
        layout.addWidget(self.params, stretch=1)
        return panel

    @staticmethod
    def _wrapped_label() -> QLabel:
        label = QLabel()
        label.setWordWrap(True)
        label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        return label

    # ---- tree ------------------------------------------------------------

    def _fill_tree(self):
        for component in self._registry.components:
            parent = QTreeWidgetItem([f"{component.name} ({len(component.presets)})"])
            parent.setData(0, ROLE_KIND, "component")
            parent.setData(0, ROLE_KEY, component.key)
            self.tree.addTopLevelItem(parent)
            for preset in component.presets:
                child = QTreeWidgetItem([preset.name])
                child.setData(0, ROLE_KIND, "preset")
                child.setData(0, ROLE_KEY, preset.name)
                child.setToolTip(0, preset.summary)
                parent.addChild(child)
            parent.setExpanded(True)

    def _apply_filter(self, text: str):
        needle = text.strip().lower()
        for i in range(self.tree.topLevelItemCount()):
            parent = self.tree.topLevelItem(i)
            visible = 0
            for j in range(parent.childCount()):
                child = parent.child(j)
                preset = self._registry[child.data(0, ROLE_KEY)]
                match = not needle or needle in f"{preset.name} {preset.summary}".lower()
                child.setHidden(not match)
                visible += match
            parent.setHidden(visible == 0)

    # ---- detail ----------------------------------------------------------

    def _on_selection_changed(self, item: QTreeWidgetItem | None, _previous=None):
        if item is None:
            return
        key = item.data(0, ROLE_KEY)
        if item.data(0, ROLE_KIND) == "component":
            self._show_component(key)
        else:
            self._show_preset(self._registry[key])

    def _component(self, key: str):
        return next(c for c in self._registry.components if c.key == key)

    def _show_component(self, key: str):
        component = self._component(key)
        self._current = None
        self.title.setText(component.name)
        self.summary.setText(component.summary)
        self.note.clear()
        self.sed.setText(component.sed)
        self.form.setRowVisible(self.sed, True)
        self._set_equations([], 1)
        for label in (self.sed_class, self.variation, self.reference):
            label.clear()
        self.sky_button.hide()
        self.params_title.setText("Presets")
        self._set_rows([(p.name, p.summary) for p in component.presets])

    def _show_preset(self, preset: Preset):
        component = self._component(preset.component)
        self._current = preset
        self.title.setText(f"{preset.name}: {component.name}")
        self.summary.setText(preset.summary)
        self.note.setText(
            "Uses high-resolution templates. The first use downloads a large file."
            if preset.is_large else ""
        )
        self.form.setRowVisible(self.sed, False)
        self._set_equations(self._registry.equations_for(preset), preset.n_components)
        self.sed_class.setText(preset.sed_class)
        self.variation.setText(preset.spatial_variation or "n/a")
        self.reference.setText(preset.reference or "n/a")
        self.sky_button.setVisible(self._can_show_on_sky(preset.name))
        self.params_title.setText("Configuration")
        self._set_rows(flatten(preset.config))

    def _set_equations(self, equations: list[Equation], n_components: int):
        while self.equation_box.count():
            item = self.equation_box.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.setParent(None)  # stop painting it now, not at some later event pass
                widget.deleteLater()
        color = self.palette().windowText().color().name()
        for equation in equations:
            title = QLabel(equation.title)
            title.setStyleSheet("font-weight: bold;")
            self.equation_box.addWidget(title)
            for line in equation.latex:
                label = QLabel()
                label.setPixmap(latex_to_pixmap(line, color=color))
                label.setContentsMargins(12, 2, 0, 2)
                self.equation_box.addWidget(label)
            where = equation.where
            if n_components > 1:
                where += f" This preset sums {n_components} components, each with this SED."
            self.equation_box.addWidget(self._wrapped_label_with(where))

    def _wrapped_label_with(self, text: str) -> QLabel:
        label = self._wrapped_label()
        label.setText(text)
        label.setStyleSheet("color: gray;")
        return label

    def _set_rows(self, rows: list[tuple[str, str]]):
        self.params.setRowCount(len(rows))
        for i, (key, value) in enumerate(rows):
            self.params.setItem(i, 0, QTableWidgetItem(key))
            self.params.setItem(i, 1, QTableWidgetItem(value))
        self.params.resizeRowsToContents()
