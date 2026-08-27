"""Native folder-selection adapter for the local desktop application."""

from __future__ import annotations

import sys
import threading
from pathlib import Path
from typing import Protocol


class FolderPicker(Protocol):
    def pick(self) -> Path | None: ...


class WindowsFolderPicker:
    _lock = threading.Lock()

    def pick(self) -> Path | None:
        if sys.platform != "win32":
            raise RuntimeError("native folder selection requires Windows")

        import tkinter
        from tkinter import filedialog

        with self._lock:
            root = tkinter.Tk()
            root.withdraw()
            root.attributes("-topmost", True)
            try:
                selected = filedialog.askdirectory(parent=root, mustexist=True)
            finally:
                root.destroy()

        return Path(selected).resolve() if selected else None
