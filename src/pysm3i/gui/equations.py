from functools import lru_cache
from io import BytesIO

from matplotlib.figure import Figure
from PyQt6.QtGui import QPixmap

BASE_DPI = 100  # matplotlib's reference dpi; the device ratio scales it back down


@lru_cache(maxsize=256)
def latex_to_pixmap(latex: str, size: float = 16, color: str = "black", dpi: int = 200) -> QPixmap:
    """Render a matplotlib-mathtext string to a tight, transparent pixmap."""
    fig = Figure()
    fig.text(0, 0, f"${latex}$", fontsize=size, color=color)
    buf = BytesIO()
    fig.savefig(buf, format="png", dpi=dpi, transparent=True,
                bbox_inches="tight", pad_inches=0.05)
    pixmap = QPixmap()
    pixmap.loadFromData(buf.getvalue())
    pixmap.setDevicePixelRatio(dpi / BASE_DPI)  # crisp, at a sensible on-screen size
    return pixmap
