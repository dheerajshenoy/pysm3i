from PyQt6.QtGui import QDoubleValidator, QFontDatabase, QGuiApplication
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView, QComboBox, QDoubleSpinBox, QFileDialog, QGridLayout, QGroupBox,
    QHBoxLayout, QHeaderView, QLabel, QLineEdit, QPlainTextEdit, QPushButton, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget,
)

from pysm3i.core.convert import UNIT_CHOICES, convert
from pysm3i.core.export import default_filename, sky_snippet, write_fits
from .equations import latex_to_pixmap

# Nominal Planck band centres, a familiar set of frequencies for the factor table.
TABLE_FREQS_GHZ = [30, 44, 70, 100, 143, 217, 353, 545, 857]
TABLE_TARGETS = ["µK_RJ", "MJy/sr"]

EQUATIONS = [
    r"x = \frac{h\nu}{k\,T_{\mathrm{CMB}}}",
    r"\Delta T_{\mathrm{RJ}} = \Delta T_{\mathrm{CMB}}\,\frac{x^2 e^{x}}{(e^{x}-1)^2}",
    r"\Delta I_\nu = \frac{2k\nu^2}{c^2}\,\Delta T_{\mathrm{RJ}}",
]


class ToolsPage(QWidget):
    """Small utilities: unit converter, reference table, and export of the Sky page's map."""

    def __init__(self, get_snapshot=lambda: None):
        super().__init__()
        self._get_snapshot = get_snapshot  # callable returning the exportable SkySnapshot
        layout = QVBoxLayout(self)
        layout.addWidget(self._build_converter())
        layout.addWidget(self._build_export())
        layout.addWidget(self._build_table(), stretch=1)
        self._update()

    def showEvent(self, event):
        super().showEvent(event)
        self._refresh_export()  # the Sky page may have changed since last time

    # ---- export ----------------------------------------------------------

    def _build_export(self) -> QGroupBox:
        box = QGroupBox("Export the map on the Sky page")
        self.export_summary = QLabel()
        self.export_summary.setWordWrap(True)
        self.snippet = QPlainTextEdit()
        self.snippet.setReadOnly(True)
        self.snippet.setFont(QFontDatabase.systemFont(QFontDatabase.SystemFont.FixedFont))
        self.snippet.setFixedHeight(210)
        self.save_button = QPushButton("Save map as FITS…")
        self.copy_button = QPushButton("Copy Python snippet")
        self.export_status = QLabel()
        self.export_status.setStyleSheet("color: gray;")
        self.save_button.clicked.connect(self._save_fits)
        self.copy_button.clicked.connect(self._copy_snippet)

        buttons = QHBoxLayout()
        buttons.addWidget(self.save_button)
        buttons.addWidget(self.copy_button)
        buttons.addWidget(self.export_status, stretch=1)
        layout = QVBoxLayout(box)
        layout.addWidget(self.export_summary)
        layout.addWidget(self.snippet)
        layout.addLayout(buttons)
        return box

    def _refresh_export(self):
        snapshot = self._get_snapshot()
        self.export_status.clear()
        self.save_button.setEnabled(snapshot is not None)
        self.copy_button.setEnabled(snapshot is not None)
        if snapshot is None:
            self.export_summary.setText("Nothing to export yet. Enable a component on the Sky page "
                                        "and wait for the map to finish computing.")
            self.snippet.clear()
            return
        self.export_summary.setText(
            f"{', '.join(snapshot.presets)} at {snapshot.freq_ghz:.1f} GHz, nside {snapshot.nside}, "
            f"{snapshot.unit_label}. This is the map currently displayed (I, Q and U)."
        )
        self.snippet.setPlainText(sky_snippet(snapshot))

    def _save_fits(self):
        snapshot = self._get_snapshot()
        if snapshot is None:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Save map as FITS", default_filename(snapshot), "FITS files (*.fits *.fit)"
        )
        if not path:
            return
        if not path.lower().endswith((".fits", ".fit")):
            path += ".fits"
        try:
            write_fits(path, snapshot)
        except Exception as exc:  # e.g. a read-only folder: report it, do not crash
            self.export_status.setText(f"Could not save: {exc}")
        else:
            self.export_status.setText(f"Saved {path}")

    def _copy_snippet(self):
        snapshot = self._get_snapshot()
        if snapshot is not None:
            QGuiApplication.clipboard().setText(sky_snippet(snapshot))
            self.export_status.setText("Copied to the clipboard.")

    # ---- converter -------------------------------------------------------

    def _build_converter(self) -> QGroupBox:
        box = QGroupBox("Unit converter")
        self.value = QLineEdit("1")
        self.value.setValidator(QDoubleValidator())  # accepts 1e3 and negatives
        self.value.setMaximumWidth(140)
        self.from_combo = QComboBox()
        self.from_combo.addItems(UNIT_CHOICES)
        self.to_combo = QComboBox()
        self.to_combo.addItems(UNIT_CHOICES)
        self.to_combo.setCurrentText("MJy/sr")
        self.swap = QPushButton("⇄")
        self.swap.setToolTip("Swap the two units")
        self.swap.setFixedWidth(36)
        self.freq = QDoubleSpinBox()
        self.freq.setRange(0.1, 10000.0)
        self.freq.setDecimals(3)
        self.freq.setSuffix(" GHz")
        self.freq.setValue(143.0)
        self.result = QLabel()
        self.result.setStyleSheet("font-size: 20px; font-weight: bold;")
        self.result.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)

        row = QHBoxLayout()
        for widget in (self.value, self.from_combo, self.swap, self.to_combo):
            row.addWidget(widget)
        row.addWidget(QLabel("at"))
        row.addWidget(self.freq)
        row.addStretch(1)

        grid = QGridLayout(box)
        grid.addLayout(row, 0, 0)
        grid.addWidget(self.result, 1, 0)
        grid.addLayout(self._equation_column(), 2, 0)

        self.value.textChanged.connect(self._update)
        self.from_combo.currentIndexChanged.connect(self._update)
        self.to_combo.currentIndexChanged.connect(self._update)
        self.freq.valueChanged.connect(self._update)
        self.swap.clicked.connect(self._swap_units)
        return box

    def _equation_column(self) -> QVBoxLayout:
        column = QVBoxLayout()
        color = self.palette().windowText().color().name()
        for latex in EQUATIONS:
            label = QLabel()
            label.setPixmap(latex_to_pixmap(latex, color=color))
            column.addWidget(label)
        note = QLabel(
            "Valid for small fluctuations around the CMB temperature, at a single frequency. "
            "Real instruments average over a bandpass, so their published factors differ slightly."
        )
        note.setWordWrap(True)
        note.setStyleSheet("color: gray;")
        column.addWidget(note)
        return column

    def _swap_units(self):
        first, second = self.from_combo.currentText(), self.to_combo.currentText()
        self.from_combo.setCurrentText(second)
        self.to_combo.setCurrentText(first)

    def _update(self, *_):
        try:
            value = float(self.value.text())
        except ValueError:
            self.result.setText("")
            return
        source, target = self.from_combo.currentText(), self.to_combo.currentText()
        result = convert(value, source, target, self.freq.value())
        self.result.setText(f"{value:g} {source} = {result:.6g} {target}")

    # ---- factor table ----------------------------------------------------

    def _build_table(self) -> QGroupBox:
        box = QGroupBox("What 1 µK_CMB is at common frequencies")
        table = QTableWidget(len(TABLE_FREQS_GHZ), 1 + len(TABLE_TARGETS))
        table.setHorizontalHeaderLabels(["Frequency [GHz]"] + [f"in {t}" for t in TABLE_TARGETS])
        table.verticalHeader().hide()
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        for i, freq in enumerate(TABLE_FREQS_GHZ):
            table.setItem(i, 0, QTableWidgetItem(f"{freq}"))
            for j, target in enumerate(TABLE_TARGETS, start=1):
                table.setItem(i, j, QTableWidgetItem(f"{convert(1.0, 'µK_CMB', target, freq):.4g}"))
        layout = QVBoxLayout(box)
        layout.addWidget(table)
        return box
