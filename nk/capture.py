"""Captura da imagem do jogo direto da janela do Mupen (Windows Graphics Capture).

Por que aqui e não no Lua: no Mupen 1.5 nenhuma função Lua devolve a imagem do jogo (emu.screenshot
depende do plugin, wgui.loadscreen usa GDI e não pega OpenGL). PrintWindow também não serve: o Lua
roda na thread de interface do Mupen, que fica bloqueada esperando o Python, e o PrintWindow trava
esperando essa thread. O WGC entrega frames pelo DWM numa thread própria e funciona mesmo com a
janela coberta por outras.
"""
import ctypes
import threading
import time
from ctypes import wintypes

import cv2
import numpy as np
from windows_capture import WindowsCapture

user32 = ctypes.WinDLL("user32", use_last_error=True)
dwmapi = ctypes.WinDLL("dwmapi")
user32.SetProcessDPIAware()

DWMWA_EXTENDED_FRAME_BOUNDS = 9
WNDENUMPROC = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)

for _name, _args, _res in [
    ("EnumWindows", [WNDENUMPROC, wintypes.LPARAM], wintypes.BOOL),
    ("EnumChildWindows", [wintypes.HWND, WNDENUMPROC, wintypes.LPARAM], wintypes.BOOL),
    ("GetWindowTextW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
    ("GetClassNameW", [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int),
    ("GetWindowThreadProcessId", [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)], wintypes.DWORD),
    ("IsWindowVisible", [wintypes.HWND], wintypes.BOOL),
    ("IsWindow", [wintypes.HWND], wintypes.BOOL),
    ("GetClientRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
    ("GetWindowRect", [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL),
    ("ClientToScreen", [wintypes.HWND, ctypes.POINTER(wintypes.POINT)], wintypes.BOOL),
]:
    _fn = getattr(user32, _name)
    _fn.argtypes, _fn.restype = _args, _res


def _text(fn, hwnd):
    buf = ctypes.create_unicode_buffer(256)
    fn(hwnd, buf, 256)
    return buf.value


def find_game_window(pid):
    """Janela principal do Mupen do processo `pid` com um jogo aberto ("Mupen 64 x.y.z - ROM"), ou None."""
    found = []

    def cb(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            title = _text(user32.GetWindowTextW, hwnd)
            if title.startswith("Mupen 64") and " - " in title:
                found.append(hwnd)
        return True

    user32.EnumWindows(WNDENUMPROC(cb), 0)
    return found[0] if found else None


def _frame_bounds(hwnd):
    """Retângulo visível da janela (sem bordas invisíveis), que é o que o WGC captura."""
    r = wintypes.RECT()
    if dwmapi.DwmGetWindowAttribute(wintypes.HWND(hwnd), DWMWA_EXTENDED_FRAME_BOUNDS,
                                    ctypes.byref(r), ctypes.sizeof(r)) != 0:
        user32.GetWindowRect(hwnd, ctypes.byref(r))
    return r


def game_rect(hwnd):
    """Área do jogo (área cliente sem a barra de status), relativa ao retângulo capturado."""
    bounds = _frame_bounds(hwnd)
    client = wintypes.RECT()
    user32.GetClientRect(hwnd, ctypes.byref(client))
    origin = wintypes.POINT(0, 0)
    user32.ClientToScreen(hwnd, ctypes.byref(origin))
    left, top = origin.x - bounds.left, origin.y - bounds.top
    right, bottom = left + client.right, top + client.bottom

    def cb(child, _):
        nonlocal bottom
        if user32.IsWindowVisible(child) and _text(user32.GetClassNameW, child).lower().startswith("msctls_statusbar"):
            r = wintypes.RECT()
            user32.GetWindowRect(child, ctypes.byref(r))
            bottom = min(bottom, r.top - bounds.top)
        return True

    user32.EnumChildWindows(hwnd, WNDENUMPROC(cb), 0)
    return left, top, right, bottom


class WindowCapture:
    # O frame que o emulador acabou de mostrar só chega pelo WGC depois da composição do DWM (até ~2
    # quadros do monitor). Por isso grab() sempre espera MIN_WAIT_SECONDS e depois que a janela
    # "pare de mudar" por SETTLE_SECONDS. Sem a espera mínima, chamadas logo após um comando pegavam
    # o frame anterior: a rede via uma imagem atrasada no play, mas não na coleta (onde a busca do
    # especialista cria uma pausa de ~2 s), e as duas situações ficavam diferentes.
    MIN_WAIT_SECONDS = 0.04
    SETTLE_SECONDS = 0.012
    MAX_WAIT_SECONDS = 0.15

    def __init__(self, hwnd):
        self.hwnd = hwnd
        self._lock = threading.Lock()
        self._frame, self._frame_time = None, 0.0
        self._closed = False
        self._rect, self._rect_time = None, 0.0

        capture = WindowsCapture(cursor_capture=False, draw_border=False, window_hwnd=hwnd)

        @capture.event
        def on_frame_arrived(frame, control):
            data = frame.frame_buffer.copy()  # BGRA; o buffer nativo é reaproveitado
            with self._lock:
                self._frame, self._frame_time = data, time.perf_counter()
            if self._closed:
                control.stop()

        @capture.event
        def on_closed():
            self._closed = True

        self._control = capture.start_free_threaded()

    def alive(self):
        return not self._closed and bool(user32.IsWindow(self.hwnd))

    def close(self):
        if not self._closed:
            self._closed = True
            try:
                self._control.stop()
            except Exception:
                pass

    def _game_rect(self):
        now = time.perf_counter()
        if self._rect is None or now - self._rect_time > 1.0:  # a janela pode ser movida/redimensionada
            self._rect, self._rect_time = game_rect(self.hwnd), now
        return self._rect

    def grab(self, size=None):
        """Imagem RGB (H, W, 3) uint8 da área do jogo; `size` = (largura, altura) para redimensionar."""
        start = time.perf_counter()
        while True:
            now = time.perf_counter()
            with self._lock:
                frame, frame_time = self._frame, self._frame_time
            waited = now - start
            if frame is not None and waited >= self.MIN_WAIT_SECONDS and (
                    now - frame_time >= self.SETTLE_SECONDS or waited > self.MAX_WAIT_SECONDS):
                break
            if frame is None and now - start > 5:
                raise RuntimeError("nenhum frame recebido da janela do Mupen")
            time.sleep(0.001)

        h, w = frame.shape[:2]
        left, top, right, bottom = self._game_rect()
        img = frame[max(top, 0):min(bottom, h), max(left, 0):min(right, w), 2::-1]  # BGRA -> RGB
        if size is not None:
            img = cv2.resize(img, size, interpolation=cv2.INTER_AREA)
        return np.ascontiguousarray(img)
