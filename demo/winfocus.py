"""
OS-level window focus on Windows (ctypes, no dependencies).

A browser launched from a background process (e.g. the Studio server) opens *behind* the active window, because
Windows blocks focus stealing, and Chrome still reports document.hasFocus() == true. So the recorder finds its
window by a temporary unique title, brings it to the foreground explicitly, and checks the real foreground window.
"""

import ctypes
import ctypes.wintypes as wt
import time

user32 = ctypes.windll.user32
kernel32 = ctypes.windll.kernel32
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x2
SW_SHOW = 5

_EnumWindowsProc = ctypes.WINFUNCTYPE(wt.BOOL, wt.HWND, wt.LPARAM)


def find_window(title: str, timeout: float = 8.0) -> int | None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        found: list[int] = []

        def cb(hwnd, _):
            if user32.IsWindowVisible(hwnd):
                n = user32.GetWindowTextLengthW(hwnd)
                buf = ctypes.create_unicode_buffer(n + 1)
                user32.GetWindowTextW(hwnd, buf, n + 1)
                if title in buf.value:
                    found.append(hwnd)
                    return False
            return True

        user32.EnumWindows(_EnumWindowsProc(cb), 0)
        if found:
            return found[0]
        time.sleep(0.2)
    return None


def foreground() -> int:
    return user32.GetForegroundWindow()


def bring_to_front(hwnd: int) -> bool:
    if foreground() == hwnd:
        return True
    fg_thread = user32.GetWindowThreadProcessId(foreground(), None)
    me = kernel32.GetCurrentThreadId()
    user32.AttachThreadInput(fg_thread, me, True)
    try:
        user32.ShowWindow(hwnd, SW_SHOW)
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        user32.AttachThreadInput(fg_thread, me, False)
    time.sleep(0.2)
    if foreground() == hwnd:
        return True
    # A synthetic Alt press lifts the foreground lock for this process.
    user32.keybd_event(VK_MENU, 0, 0, 0)
    user32.keybd_event(VK_MENU, 0, KEYEVENTF_KEYUP, 0)
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.3)
    return foreground() == hwnd
