from PyQt6.QtCore import QObject, QRunnable, pyqtSignal

from pysm3i.core.skymodel import Cancelled


class JobSignals(QObject):
    done = pyqtSignal(int, object)
    failed = pyqtSignal(int, str)


class Job(QRunnable):
    """Run `fn()` on the thread pool and report the result tagged with request_id."""

    def __init__(self, request_id: int, fn):
        super().__init__()
        self.signals = JobSignals()
        self._id = request_id
        self._fn = fn

    def run(self):
        try:
            result = self._fn()
        except Cancelled:
            return  # the page already moved on; nothing to report
        except Exception as exc:  # shown in the status line, not a crash
            self.signals.failed.emit(self._id, f"{type(exc).__name__}: {exc}")
        else:
            self.signals.done.emit(self._id, result)
