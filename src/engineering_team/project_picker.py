"""Native, local folder-selection adapters for macOS and Windows.

The web app calls this module from a FastAPI worker. Neither supported adapter
creates a Python GUI: macOS runs an AppKit ``NSOpenPanel`` through ``osascript``
and Windows runs the built-in WinForms folder dialog in a hidden STA PowerShell
process. This keeps Cocoa/Tk out of the Python worker and avoids activating
Python Launcher on macOS.
"""

from __future__ import annotations

import base64
import logging
import subprocess
import sys
import threading
from pathlib import Path
from typing import Protocol

_PICKER_TIMEOUT_SECONDS = 120
_MAX_STDERR_LOG_CHARS = 400
_LOGGER = logging.getLogger(__name__)

_MACOS_DIALOG_SCRIPT = r"""
ObjC.import('AppKit');

const app = $.NSApplication.sharedApplication;
app.setActivationPolicy($.NSApplicationActivationPolicyAccessory);
app.activateIgnoringOtherApps(true);

const panel = $.NSOpenPanel.openPanel;
panel.setCanChooseFiles(false);
panel.setCanChooseDirectories(true);
panel.setAllowsMultipleSelection(false);
panel.setCanCreateDirectories(false);
panel.setTitle($('Select project folder'));
panel.setMessage($('Choose the project directory to change.'));
panel.setPrompt($('Select'));
panel.center;

if (Number(panel.runModal) === 1) {
  const path = ObjC.unwrap(panel.URL.path);
  const data = $(path + '\n').dataUsingEncoding($.NSUTF8StringEncoding);
  $.NSFileHandle.fileHandleWithStandardOutput.writeData(data);
}
"""

_WINDOWS_DIALOG_SCRIPT = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
using System.Windows.Forms;

public sealed class NativeFolderPickerOwner : IWin32Window
{
    [DllImport("user32.dll")]
    private static extern IntPtr GetForegroundWindow();

    private readonly IntPtr _handle = GetForegroundWindow();

    public IntPtr Handle { get { return _handle; } }
}
'@ -ReferencedAssemblies System.Windows.Forms

$dialog = New-Object System.Windows.Forms.FolderBrowserDialog
$dialog.Description = 'Select project folder'
if ($dialog.PSObject.Properties.Name -contains 'AutoUpgradeEnabled') {
    $dialog.AutoUpgradeEnabled = $true
}
$dialog.ShowNewFolderButton = $false

try {
    $owner = New-Object NativeFolderPickerOwner
    if ($dialog.ShowDialog($owner) -eq [System.Windows.Forms.DialogResult]::OK) {
        [Console]::OutputEncoding = New-Object -TypeName System.Text.UTF8Encoding -ArgumentList $false
        [Console]::WriteLine($dialog.SelectedPath)
    }
}
finally {
    $dialog.Dispose()
}
"""


class FolderPicker(Protocol):
    def pick(self) -> Path | None: ...


class PickerBusyError(RuntimeError):
    """Raised when a second picker request arrives while one dialog is open."""


def _bounded_stderr(stderr: str | bytes | None) -> str:
    if isinstance(stderr, bytes):
        text = stderr.decode("utf-8", errors="replace")
    else:
        text = stderr or ""
    text = " ".join(text.split()) or "<no stderr>"
    if len(text) > _MAX_STDERR_LOG_CHARS:
        return f"{text[:_MAX_STDERR_LOG_CHARS]}… [truncated]"
    return text


class _SubprocessFolderPicker:
    _lock = threading.Lock()

    def pick(self) -> Path | None:
        if not self._lock.acquire(blocking=False):
            raise PickerBusyError("A folder picker is already open.")
        try:
            return self._pick()
        finally:
            self._lock.release()

    def _pick(self) -> Path | None:
        raise NotImplementedError

    @staticmethod
    def _run(command: list[str], *, creationflags: int = 0) -> Path | None:
        try:
            result = subprocess.run(
                command,
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
                timeout=_PICKER_TIMEOUT_SECONDS,
                **({"creationflags": creationflags} if creationflags else {}),
            )
        except subprocess.TimeoutExpired as exc:
            raise RuntimeError(
                f"Native folder picker timed out after {_PICKER_TIMEOUT_SECONDS} seconds."
            ) from exc
        except OSError as exc:
            raise RuntimeError("Native folder picker could not be started.") from exc
        except subprocess.CalledProcessError as exc:
            _LOGGER.warning(
                "Native folder picker command failed (exit %s): %s",
                exc.returncode,
                _bounded_stderr(exc.stderr),
            )
            raise RuntimeError("Native folder picker failed.") from exc

        selected = result.stdout.rstrip("\r\n")
        return Path(selected).expanduser().resolve() if selected else None


class MacOSFolderPicker(_SubprocessFolderPicker):
    """Present AppKit's directory-only open panel through JXA."""

    def _pick(self) -> Path | None:
        return self._run(["osascript", "-l", "JavaScript", "-e", _MACOS_DIALOG_SCRIPT])


class WindowsFolderPicker(_SubprocessFolderPicker):
    """Present the upgraded built-in folder dialog in a hidden STA process."""

    def _pick(self) -> Path | None:
        encoded_script = base64.b64encode(_WINDOWS_DIALOG_SCRIPT.encode("utf-16-le")).decode("ascii")
        return self._run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-STA",
                "-ExecutionPolicy",
                "Bypass",
                "-EncodedCommand",
                encoded_script,
            ],
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )


class NativeFolderPicker:
    """Dispatch to the OS-native adapter without importing or opening Tk."""

    def pick(self) -> Path | None:
        if sys.platform == "darwin":
            return MacOSFolderPicker().pick()
        if sys.platform == "win32":
            return WindowsFolderPicker().pick()
        raise RuntimeError("Native folder selection requires macOS or Windows.")
