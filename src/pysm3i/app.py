import os
import re
import sys
from pathlib import Path

from PyQt6.QtCore import QT_VERSION_STR, QCoreApplication
from PyQt6.QtWidgets import QApplication

from pysm3i.gui import MainWindow

# Where Linux distributions install Qt 6 plugins (styles such as Kvantum, platform themes such as qt6ct).
SYSTEM_QT_PLUGIN_DIRS = [
    "/usr/lib/qt6/plugins",
    "/usr/lib64/qt6/plugins",
    "/usr/lib/x86_64-linux-gnu/qt6/plugins",
    "/usr/lib/aarch64-linux-gnu/qt6/plugins",
]


def system_qt_version(plugin_dir: str) -> tuple[int, int] | None:
    """(major, minor) of the Qt that owns this plugin folder, or None if it cannot be told.

    Read from the real file name behind libQt6Core.so.6, e.g. libQt6Core.so.6.11.2.
    """
    core = Path(plugin_dir).parents[1] / "libQt6Core.so.6"
    try:
        match = re.fullmatch(r"libQt6Core\.so\.(\d+)\.(\d+)\.\d+", core.resolve().name)
    except OSError:
        return None
    return (int(match[1]), int(match[2])) if match else None


def add_system_qt_plugins(plugin_dirs: list[str] = SYSTEM_QT_PLUGIN_DIRS) -> list[str]:
    """Let the pip-installed Qt find the system's style and theme plugins.

    The PyQt6 wheel bundles its own Qt, which only looks in its own plugin folder. That
    has just the Windows and Fusion styles, so system themes such as Kvantum (and the
    qt6ct platform theme that selects them) are never found. The system folders are
    appended, so the bundled plugins keep priority and only plugins the wheel lacks are
    picked up.

    Plugins use Qt internals, so a folder is only used when its Qt has the same
    major.minor version as the wheel's. Otherwise mixing the two could misbehave.

    Must run before the QApplication is created. Set PYSM3I_NO_SYSTEM_QT_PLUGINS=1 to skip.
    Returns the folders that were added.
    """
    if not sys.platform.startswith("linux") or os.environ.get("PYSM3I_NO_SYSTEM_QT_PLUGINS"):
        return []
    bundled = tuple(int(part) for part in QT_VERSION_STR.split(".")[:2])
    paths = QCoreApplication.libraryPaths()
    seen = {Path(p).resolve() for p in paths}  # /usr/lib64 is often a symlink to /usr/lib
    added = []
    for directory in plugin_dirs:
        if not Path(directory).is_dir() or Path(directory).resolve() in seen:
            continue
        seen.add(Path(directory).resolve())
        version = system_qt_version(directory)
        if version != bundled:
            found = ".".join(map(str, version)) if version else "unknown"
            print(f"pysm3i: not using system Qt plugins in {directory}: system Qt {found} "
                  f"differs from the bundled Qt {QT_VERSION_STR}", file=sys.stderr)
            continue
        added.append(directory)
    if added:
        QCoreApplication.setLibraryPaths(paths + added)
    return added


def main() -> int:
    add_system_qt_plugins()
    app = QApplication([])
    app.setApplicationName("PySM3i")
    window = MainWindow()
    window.show()
    return app.exec()
