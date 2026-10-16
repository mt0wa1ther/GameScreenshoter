"""
Game Screenshoter — автоматический захват окна GTA5.exe / Majestic.exe.
v1.1.1 — настраиваемый интервал автоснимков.
"""
import os
import re
import sys
import json
import time
import queue
import shutil
import ctypes
import logging
import threading
import subprocess
import urllib.request
import webbrowser
import tkinter as tk
from ctypes import wintypes
from datetime import datetime, timedelta
from io import BytesIO
from tkinter import messagebox

import customtkinter as ctk
import psutil
import keyboard
import pystray
from pystray import MenuItem as Item
from PIL import Image, ImageDraw, ImageGrab, ImageTk

try:
    import winsound
    SOUND_AVAILABLE = True
except ImportError:
    SOUND_AVAILABLE = False

try:
    import win32clipboard
    CLIPBOARD_AVAILABLE = True
except ImportError:
    CLIPBOARD_AVAILABLE = False

try:
    import win32gui, win32ui, win32process, win32con
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

APP_VERSION = "1.0.0"
GITHUB_REPO_DEFAULT = "mt0wa1ther/GameScreenshoter"

if getattr(sys, "frozen", False):
    APP_DIR    = os.path.dirname(sys.executable)
    BUNDLE_DIR = getattr(sys, "_MEIPASS", APP_DIR)
else:
    APP_DIR    = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = APP_DIR


def _test_writable(path: str) -> bool:
    try:
        os.makedirs(path, exist_ok=True)
        probe = os.path.join(path, ".write_probe")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return True
    except Exception:
        return False


if _test_writable(APP_DIR):
    DATA_DIR = APP_DIR
else:
    DATA_DIR = os.path.join(os.path.expanduser("~"),
                            "Documents", "GameScreenshoter")
    os.makedirs(DATA_DIR, exist_ok=True)

BASE_DIR    = os.path.join(DATA_DIR, "Screenshots")
LOG_DIR     = os.path.join(DATA_DIR, "Logs")
ASSETS_DIR  = os.path.join(DATA_DIR, "assets")
LOG_FILE    = os.path.join(LOG_DIR, "screenshoter.log")
ICON_PATH   = os.path.join(ASSETS_DIR, "icon.ico")
CONFIG_FILE = os.path.join(DATA_DIR, "config.json")

os.makedirs(LOG_DIR, exist_ok=True)
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(BASE_DIR, exist_ok=True)

MANUAL_SUBFOLDER = "manual"

# ============ ТЕМЫ ============
ACCENTS = {
    "purple": {"name": "Фиолет",    "accent": "#7c3aed", "accent_h": "#6d28d9", "accent_glow": "#a855f7"},
    "blue":   {"name": "Синий",     "accent": "#2563eb", "accent_h": "#1d4ed8", "accent_glow": "#3b82f6"},
    "green":  {"name": "Зелёный",   "accent": "#10b981", "accent_h": "#059669", "accent_glow": "#34d399"},
    "pink":   {"name": "Розовый",   "accent": "#ec4899", "accent_h": "#db2777", "accent_glow": "#f472b6"},
    "orange": {"name": "Оранжевый", "accent": "#f97316", "accent_h": "#ea580c", "accent_glow": "#fb923c"},
}


DEFAULT_CONFIG = {
    "hotkey":             "print screen",
    "monitor_index":      0,
    "interval_minutes":   20,       # интервал автоснимков (мин)
    "update_check":       True,
    "github_repo":        GITHUB_REPO_DEFAULT,
    "window_width":       400,
    "window_height":      900,
    "window_x":           None,
    "window_y":           None,
    "overlay_x":          None,
    "overlay_y":          20,
    "copy_to_clipboard":  True,
    "play_sound":         True,
    "overlay_auto_hide":  True,
    "show_toast":         True,
    "flash_effect":       True,
    "accent_theme":       "purple",
}


def load_config() -> dict:
    cfg = dict(DEFAULT_CONFIG)
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                cfg.update(data)
    except Exception:
        logging.exception("load_config")
    return cfg


def save_config(cfg: dict) -> None:
    try:
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(cfg, f, ensure_ascii=False, indent=2)
    except Exception:
        logging.exception("save_config")


def apply_accent(name: str, cfg: dict):
    theme = ACCENTS.get(name, ACCENTS["purple"])
    C["accent"]      = theme["accent"]
    C["accent_h"]    = theme["accent_h"]
    C["accent_glow"] = theme["accent_glow"]
    cfg["accent_theme"] = name


JPEG_QUALITY           = 90
RETAIN_DAYS            = 14
GAME_PROCESSES         = {"gta5.exe", "majestic.exe"}
GAME_SCAN_INTERVAL     = 2
FALLBACK_TO_FULLSCREEN = True
AUTO_START_ON_GAME     = True
AUTO_ONLY_IF_GAME      = True

CAPTURE_ATTEMPTS       = 3
CAPTURE_RETRY_DELAY    = 0.12
POST_HIDE_DELAY        = 0.25

STATS_REFRESH_SEC      = 10
COUNTDOWN_REFRESH_MS   = 800
OVERLAY_TOP_REFRESH_MS = 900
RESIZE_DEBOUNCE_MS     = 220

C = {
    "bg":          "#0b0b18",
    "card":        "#16162c",
    "card_hover":  "#1e1e3c",
    "border":      "#2a2a52",
    "border_soft": "#1f1f3c",
    "text":        "#f5f5ff",
    "text2":       "#9d9dc4",
    "text3":       "#5a5a85",
    "accent":      "#7c3aed",
    "accent_h":    "#6d28d9",
    "accent_glow": "#a855f7",
    "blue":        "#4f46e5",
    "blue_h":      "#4338ca",
    "green":       "#10b981",
    "green_h":     "#059669",
    "red":         "#ef4444",
    "red_h":       "#dc2626",
    "orange":      "#f59e0b",
    "yellow":      "#fbbf24",
}

OVERLAY_KEY          = "#FF00FE"
OVERLAY_TEXT         = "#FFFFFF"
OVERLAY_SHADOW       = "#000000"
OVERLAY_WARN         = "#fbbf24"
OVERLAY_ALERT        = "#f87171"
OVERLAY_W             = 120
OVERLAY_H             = 34
OVERLAY_TOP_MARGIN    = 20
OVERLAY_RIGHT_MARGIN  = 170
OVERLAY_FONT          = ("Segoe UI", 16, "bold")

TOAST_W               = 260
TOAST_H               = 78
TOAST_MARGIN_RIGHT    = 24
TOAST_MARGIN_BOTTOM   = 24
TOAST_DURATION_MS     = 3000

PREVIEW_W             = 140
PREVIEW_H             = 80

logging.basicConfig(
    filename=LOG_FILE, level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s", encoding="utf-8",
)
logging.info("=== Запуск Game Screenshoter v%s ===", APP_VERSION)


_user32 = ctypes.windll.user32 if WIN32_AVAILABLE else None
if WIN32_AVAILABLE:
    _user32.PrintWindow.argtypes = [wintypes.HWND, wintypes.HDC, wintypes.UINT]
    _user32.PrintWindow.restype  = wintypes.BOOL
    _user32.SetWindowPos.argtypes = [
        wintypes.HWND, wintypes.HWND,
        ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
        wintypes.UINT,
    ]
    _user32.SetWindowPos.restype = wintypes.BOOL

PW_RENDERFULLCONTENT = 0x02


# ============ УТИЛИТЫ ============
def play_shutter_sound():
    if not SOUND_AVAILABLE:
        return
    try:
        winsound.PlaySound("SystemAsterisk",
                           winsound.SND_ALIAS | winsound.SND_ASYNC)
    except Exception:
        try:
            winsound.Beep(900, 60)
        except Exception:
            pass


def copy_image_to_clipboard(image):
    if not CLIPBOARD_AVAILABLE or image is None:
        return False
    try:
        output = BytesIO()
        image.convert("RGB").save(output, "BMP")
        data = output.getvalue()[14:]
        output.close()
        win32clipboard.OpenClipboard()
        try:
            win32clipboard.EmptyClipboard()
            win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
        finally:
            win32clipboard.CloseClipboard()
        return True
    except Exception:
        logging.exception("copy_image_to_clipboard")
        return False


def enumerate_monitors() -> list:
    if not WIN32_AVAILABLE:
        return [{"x": 0, "y": 0, "width": 1920, "height": 1080}]
    monitors = []
    RECT = wintypes.RECT
    MonitorEnumProc = ctypes.WINFUNCTYPE(
        ctypes.c_int, ctypes.c_ulong, ctypes.c_ulong,
        ctypes.POINTER(RECT), ctypes.c_double)

    def _cb(hMonitor, hdcMonitor, lprcMonitor, dwData):
        r = lprcMonitor.contents
        monitors.append({
            "x": r.left, "y": r.top,
            "width": r.right - r.left,
            "height": r.bottom - r.top,
        })
        return True

    try:
        _user32.EnumDisplayMonitors(0, 0, MonitorEnumProc(_cb), 0)
    except Exception:
        logging.exception("enumerate_monitors")
    if not monitors:
        monitors = [{"x": 0, "y": 0, "width": 1920, "height": 1080}]
    return monitors


def grab_screen(monitor_index: int) -> Image.Image:
    try:
        if monitor_index > 0:
            mons = enumerate_monitors()
            if monitor_index <= len(mons):
                m = mons[monitor_index - 1]
                bbox = (m["x"], m["y"],
                        m["x"] + m["width"], m["y"] + m["height"])
                return ImageGrab.grab(bbox=bbox, all_screens=True)
        return ImageGrab.grab(all_screens=True)
    except Exception:
        logging.exception("grab_screen")
        return ImageGrab.grab(all_screens=True)


def count_screenshots() -> dict:
    today_name = datetime.now().strftime("%Y-%m-%d")
    today_count = 0
    total_count = 0
    if not os.path.isdir(BASE_DIR):
        return {"today": 0, "total": 0}
    try:
        for entry in os.listdir(BASE_DIR):
            full = os.path.join(BASE_DIR, entry)
            if not os.path.isdir(full):
                continue
            cnt = 0
            for _, _, files in os.walk(full):
                for f in files:
                    if f.lower().endswith(".jpg"):
                        cnt += 1
            total_count += cnt
            if entry == today_name:
                today_count = cnt
    except Exception:
        logging.exception("count_screenshots")
    return {"today": today_count, "total": total_count}


def list_today_screenshots() -> list:
    paths = []
    try:
        day = get_day_folder()
        for root, _, files in os.walk(day):
            for f in files:
                if f.lower().endswith(".jpg"):
                    paths.append(os.path.join(root, f))
    except Exception:
        logging.exception("list_today_screenshots")
    paths.sort(key=lambda p: os.path.getmtime(p), reverse=True)
    return paths


def _version_tuple(v: str):
    v = (v or "").lstrip("vV")
    try:
        return tuple(int(x) for x in v.split("."))
    except Exception:
        return (0,)


def check_for_updates(repo: str, timeout: int = 5):
    if not repo:
        return None
    try:
        url = f"https://api.github.com/repos/{repo}/releases/latest"
        req = urllib.request.Request(url, headers={
            "User-Agent":   f"GameScreenshoter/{APP_VERSION}",
            "Accept":       "application/vnd.github+json",
        })
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        tag = (data.get("tag_name") or "").strip()
        if not tag:
            return None
        if _version_tuple(tag) > _version_tuple(APP_VERSION):
            return {
                "version": tag.lstrip("vV"),
                "url":     data.get("html_url", ""),
                "notes":   (data.get("body") or "")[:400],
            }
    except Exception:
        logging.exception("check_for_updates")
    return None


_INDEX_RE = re.compile(r"_(\d{3,5})\.jpg$", re.IGNORECASE)


def _next_index(folder: str) -> int:
    if not os.path.isdir(folder):
        return 1
    max_n = 0
    try:
        for name in os.listdir(folder):
            m = _INDEX_RE.search(name)
            if m:
                try:
                    n = int(m.group(1))
                    if n > max_n:
                        max_n = n
                except ValueError:
                    continue
    except Exception:
        logging.exception("_next_index")
    return max_n + 1


def build_filename(folder: str) -> str:
    idx = _next_index(folder)
    stamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    return f"{stamp}_{idx:03d}.jpg"


def generate_icon(path: str, color: str = "#7c3aed"):
    S = 256
    img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    c_rgb = tuple(int(color.lstrip("#")[i:i+2], 16) for i in (0, 2, 4))
    for i in range(S):
        t = i / S
        r = int(c_rgb[0] + (0xff - c_rgb[0]) * t)
        g = int(c_rgb[1] + (0xcc - c_rgb[1]) * t)
        b = int(c_rgb[2] + (0xff - c_rgb[2]) * t)
        d.line([(0, i), (S, i)], fill=(r, g, b, 255))
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle([0, 0, S, S], radius=56, fill=255)
    img.putalpha(mask)
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([46, 88, 210, 194], radius=26, fill="white")
    d.ellipse([102, 118, 154, 170], fill=color)
    d.ellipse([114, 130, 142, 158], fill="#ffffff")
    d.rounded_rectangle([100, 70, 156, 92], radius=8, fill="white")
    img.save(path, format="ICO",
             sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def ensure_icon(color: str = "#7c3aed") -> str:
    if os.path.exists(ICON_PATH):
        return ICON_PATH
    bundled = os.path.join(BUNDLE_DIR, "assets", "icon.ico")
    if os.path.exists(bundled) and bundled != ICON_PATH:
        try:
            os.makedirs(ASSETS_DIR, exist_ok=True)
            shutil.copy2(bundled, ICON_PATH)
            return ICON_PATH
        except Exception:
            logging.exception("copy icon")
    try:
        generate_icon(ICON_PATH, color)
    except Exception:
        logging.exception("gen icon")
    return ICON_PATH


def get_day_folder() -> str:
    folder = os.path.join(BASE_DIR, datetime.now().strftime("%Y-%m-%d"))
    os.makedirs(folder, exist_ok=True)
    return folder


def get_screenshot_folder(manual: bool = False) -> str:
    day = get_day_folder()
    if manual:
        day = os.path.join(day, MANUAL_SUBFOLDER)
        os.makedirs(day, exist_ok=True)
    return day


def open_folder_in_explorer(folder: str):
    try:
        if sys.platform.startswith("win"):
            os.startfile(folder)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", folder])
        else:
            subprocess.Popen(["xdg-open", folder])
    except Exception as e:
        logging.error("open folder: %s", e)


def find_game_window():
    if not WIN32_AVAILABLE:
        return None
    found = {"hwnd": None, "pid": None, "title": None, "process": None}

    def cb(hwnd, _):
        if not win32gui.IsWindowVisible(hwnd):
            return True
        title = win32gui.GetWindowText(hwnd)
        if not title:
            return True
        try:
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            if not pid:
                return True
            name = psutil.Process(pid).name().lower()
        except Exception:
            return True
        if name in GAME_PROCESSES:
            l, t, r, b = win32gui.GetClientRect(hwnd)
            if (r - l) > 100 and (b - t) > 100:
                found.update(hwnd=hwnd, pid=pid, title=title, process=name)
                return False
        return True

    try:
        win32gui.EnumWindows(cb, None)
    except Exception:
        if found["hwnd"] is None:
            logging.exception("EnumWindows")
    return found if found["hwnd"] else None


def _capture_once(hwnd):
    l, t, r, b = win32gui.GetClientRect(hwnd)
    w, h = r - l, b - t
    if w <= 0 or h <= 0:
        return None
    hwnd_dc = win32gui.GetWindowDC(hwnd)
    mfc = save = bmp = None
    try:
        mfc = win32ui.CreateDCFromHandle(hwnd_dc)
        save = mfc.CreateCompatibleDC()
        bmp = win32ui.CreateBitmap()
        bmp.CreateCompatibleBitmap(mfc, w, h)
        save.SelectObject(bmp)
        hdc = save.GetSafeHdc()
        ok = _user32.PrintWindow(wintypes.HWND(hwnd),
                                 wintypes.HDC(hdc),
                                 wintypes.UINT(PW_RENDERFULLCONTENT))
        if not ok:
            _user32.PrintWindow(wintypes.HWND(hwnd),
                                wintypes.HDC(hdc),
                                wintypes.UINT(0))
        info = bmp.GetInfo()
        bits = bmp.GetBitmapBits(True)
        return Image.frombuffer("RGB",
                                (info["bmWidth"], info["bmHeight"]),
                                bits, "raw", "BGRX", 0, 1)
    except Exception:
        logging.exception("_capture_once")
        return None
    finally:
        try:
            if bmp: win32gui.DeleteObject(bmp.GetHandle())
        except Exception: pass
        try:
            if save: save.DeleteDC()
        except Exception: pass
        try:
            if mfc: mfc.DeleteDC()
        except Exception: pass
        try: win32gui.ReleaseDC(hwnd, hwnd_dc)
        except Exception: pass


def _is_mostly_black(img, threshold=0.90, step=12):
    if img is None:
        return True
    try:
        w, h = img.size
        if w <= 0 or h <= 0:
            return True
        pixels = img.load()
        total = 0
        black = 0
        for y in range(0, h, step):
            for x in range(0, w, step):
                r, g, b = pixels[x, y][:3]
                total += 1
                if r < 20 and g < 20 and b < 20:
                    black += 1
        if total == 0:
            return True
        return (black / total) >= threshold
    except Exception:
        logging.exception("_is_mostly_black")
        return False


def capture_window_with_retry(hwnd, attempts=CAPTURE_ATTEMPTS,
                              delay=CAPTURE_RETRY_DELAY):
    best = None
    for i in range(attempts):
        img = _capture_once(hwnd)
        if img is None:
            time.sleep(delay)
            continue
        if not _is_mostly_black(img):
            return img, i + 1
        best = img
        time.sleep(delay)
    return best, attempts


def _grab_game_from_screen(hwnd):
    try:
        l, t, r, b = win32gui.GetClientRect(hwnd)
        x, y = win32gui.ClientToScreen(hwnd, (l, t))
        w, h = r - l, b - t
        if w <= 0 or h <= 0:
            return None
        return ImageGrab.grab(bbox=(x, y, x + w, y + h), all_screens=True)
    except Exception:
        logging.exception("_grab_game_from_screen")
        return None


def take_screenshot(prefix="shot", only_if_game=False, manual=False,
                    monitor_index=0, copy_clipboard=False):
    game = find_game_window()
    img, source = None, "?"

    if game:
        img, tries = capture_window_with_retry(game["hwnd"])
        if img is not None and not _is_mostly_black(img):
            source = f"game:{game['process']} (try {tries})"
        else:
            logging.warning("PrintWindow не дал кадр за %d попыток", tries)
            alt = _grab_game_from_screen(game["hwnd"])
            if alt is not None and not _is_mostly_black(alt):
                img = alt
                source = f"screen:{game['process']}"

    if img is None:
        if only_if_game or not FALLBACK_TO_FULLSCREEN:
            logging.info("Игра не найдена — пропуск (%s)", prefix)
            return None
        img = grab_screen(monitor_index)
        source = "fullscreen" if monitor_index <= 0 else f"monitor{monitor_index}"

    if img.mode != "RGB":
        img = img.convert("RGB")

    folder = get_screenshot_folder(manual=manual)
    filename = build_filename(folder)
    path = os.path.join(folder, filename)

    img.save(path, "JPEG", quality=JPEG_QUALITY)

    if copy_clipboard:
        copy_image_to_clipboard(img)

    logging.info("Скриншот (%s%s): %s",
                 source, ", manual" if manual else "", path)
    return path


def _parse_date(name):
    try:    return datetime.strptime(name, "%Y-%m-%d")
    except ValueError: return None


def cleanup_old_folders(retain_days=RETAIN_DAYS):
    stats = {"deleted": [], "skipped": [], "errors": []}
    if not os.path.isdir(BASE_DIR):
        return stats
    cutoff = datetime.now() - timedelta(days=retain_days)
    for entry in os.listdir(BASE_DIR):
        full = os.path.join(BASE_DIR, entry)
        if not os.path.isdir(full):
            continue
        d = _parse_date(entry)
        if d is None:
            stats["skipped"].append(entry); continue
        if d < cutoff:
            try:
                shutil.rmtree(full)
                stats["deleted"].append(entry)
                logging.info("Удалена старая папка: %s", full)
            except Exception as e:
                stats["errors"].append((entry, str(e)))
                logging.error("Удалить %s: %s", full, e)
    return stats


# ============ TOAST ============
class ToastManager:
    def __init__(self, master: tk.Tk):
        self.master = master
        self._toasts = []
        self._offset = 0

    def show(self, title: str, subtitle: str = "", on_click=None):
        try:
            self._offset += 1
            t = self._make_toast(title, subtitle, on_click)
            self._toasts.append(t)
            self.master.after(TOAST_DURATION_MS, lambda: self._close(t))
        except Exception:
            logging.exception("toast show")

    def _make_toast(self, title, subtitle, on_click):
        win = tk.Toplevel(self.master)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.configure(bg="#1a1a2e")
        try:
            win.attributes("-alpha", 0.0)
        except Exception:
            pass

        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        offset_y = sh - TOAST_MARGIN_BOTTOM - TOAST_H
        if self._offset > 1:
            offset_y -= (self._offset - 1) * (TOAST_H + 8)
        x = sw - TOAST_MARGIN_RIGHT - TOAST_W
        y = offset_y
        win.geometry(f"{TOAST_W}x{TOAST_H}+{x}+{y}")

        frame = tk.Frame(win, bg="#1a1a2e",
                         highlightbackground=C["accent"],
                         highlightthickness=1)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="📸", bg="#1a1a2e", fg=C["accent_glow"],
                 font=("Segoe UI Emoji", 18)
                 ).pack(side="left", padx=(12, 8))

        col = tk.Frame(frame, bg="#1a1a2e")
        col.pack(side="left", fill="both", expand=True, pady=10)

        tk.Label(col, text=title, bg="#1a1a2e", fg="#f5f5ff",
                 font=("Segoe UI", 10, "bold"), anchor="w"
                 ).pack(fill="x")

        if subtitle:
            tk.Label(col, text=subtitle, bg="#1a1a2e", fg="#9d9dc4",
                     font=("Segoe UI", 8), anchor="w"
                     ).pack(fill="x")

        if on_click:
            for w in (frame, col, win):
                w.bind("<Button-1>", lambda e: on_click())

        try:
            for i in range(1, 11):
                win.attributes("-alpha", i / 10)
                win.update_idletasks()
                time.sleep(0.012)
        except Exception:
            pass

        return win

    def _close(self, win):
        try:
            try:
                for i in range(10, 0, -1):
                    win.attributes("-alpha", i / 10)
                    win.update_idletasks()
                    time.sleep(0.012)
            except Exception:
                pass
            win.destroy()
        except Exception:
            pass
        finally:
            try:
                self._toasts.remove(win)
                self._offset = max(0, self._offset - 1)
            except Exception:
                pass


# ============ ВСПЫШКА ============
class FlashAnimation:
    def __init__(self, master: tk.Tk):
        self.master = master
        self.win = None

    def fire(self):
        try:
            self.win = tk.Toplevel(self.master)
            self.win.overrideredirect(True)
            self.win.attributes("-topmost", True)
            self.win.configure(bg="#ffffff")
            sw = self.win.winfo_screenwidth()
            sh = self.win.winfo_screenheight()
            self.win.geometry(f"{sw}x{sh}+0+0")
            try:
                self.win.attributes("-alpha", 0.45)
            except Exception:
                pass
            self.win.update_idletasks()

            def fade(i=9):
                try:
                    if i <= 0:
                        self.win.destroy()
                        self.win = None
                        return
                    self.win.attributes("-alpha", i / 20)
                    self.master.after(20, lambda: fade(i - 1))
                except Exception:
                    try:
                        self.win.destroy()
                    except Exception:
                        pass
                    self.win = None

            self.master.after(40, fade)
        except Exception:
            logging.exception("flash fire")


# ============ ОВЕРЛЕЙ ============
class OverlayTimer:
    def __init__(self, master: tk.Tk, config: dict):
        self.master = master
        self.config = config
        self.visible = False
        self.enabled = True
        self._hwnd_root = None
        self._last_text = None
        self._draggable = False
        self._drag_start = None

        self.win = tk.Toplevel(master)
        self.win.withdraw()
        self.win.overrideredirect(True)
        self.win.attributes("-topmost", True)
        self.win.configure(bg=OVERLAY_KEY)

        try:
            self.win.attributes("-transparentcolor", OVERLAY_KEY)
        except Exception:
            pass

        self.canvas = tk.Canvas(
            self.win, width=OVERLAY_W, height=OVERLAY_H,
            bg=OVERLAY_KEY, highlightthickness=0, bd=0,
            cursor="fleur",
        )
        self.canvas.pack()

        cx = OVERLAY_W // 2
        cy = OVERLAY_H // 2

        self.shadow_id = self.canvas.create_text(
            cx + 1, cy + 1, text="—:—",
            fill=OVERLAY_SHADOW, font=OVERLAY_FONT,
        )
        self.time_id = self.canvas.create_text(
            cx, cy, text="—:—",
            fill=OVERLAY_TEXT, font=OVERLAY_FONT,
        )

        self.canvas.bind("<Button-1>", self._on_drag_start)
        self.canvas.bind("<B1-Motion>", self._on_drag_move)
        self.canvas.bind("<ButtonRelease-1>", self._on_drag_end)

        self._position()
        self._remember_hwnd()
        self._make_click_through()
        self._keep_topmost_loop()

    def _position(self):
        sw = self.win.winfo_screenwidth()
        ox = self.config.get("overlay_x")
        oy = self.config.get("overlay_y", OVERLAY_TOP_MARGIN)
        if ox is None:
            ox = sw - OVERLAY_RIGHT_MARGIN - OVERLAY_W
        self.win.geometry(f"{OVERLAY_W}x{OVERLAY_H}+{int(ox)}+{int(oy)}")

    def _remember_hwnd(self):
        if not WIN32_AVAILABLE:
            return
        try:
            self.win.update_idletasks()
            self._hwnd_root = win32gui.GetAncestor(
                self.win.winfo_id(), win32con.GA_ROOT)
        except Exception:
            self._hwnd_root = None

    def _make_click_through(self):
        if not WIN32_AVAILABLE or not self._hwnd_root:
            return
        try:
            ex = win32gui.GetWindowLong(self._hwnd_root, win32con.GWL_EXSTYLE)
            ex |= win32con.WS_EX_LAYERED | win32con.WS_EX_TOOLWINDOW
            if not self._draggable:
                ex |= win32con.WS_EX_TRANSPARENT
            else:
                ex &= ~win32con.WS_EX_TRANSPARENT
            win32gui.SetWindowLong(self._hwnd_root, win32con.GWL_EXSTYLE, ex)
            win32gui.SetWindowPos(
                self._hwnd_root, 0, 0, 0, 0, 0,
                win32con.SWP_NOMOVE | win32con.SWP_NOSIZE |
                win32con.SWP_NOZORDER | win32con.SWP_FRAMECHANGED,
            )
        except Exception:
            logging.exception("overlay click-through")

    def set_draggable(self, enabled: bool):
        self._draggable = bool(enabled)
        self._make_click_through()

    def _on_drag_start(self, event):
        if not self._draggable:
            return
        self._drag_start = (event.x_root, event.y_root,
                            self.win.winfo_x(), self.win.winfo_y())

    def _on_drag_move(self, event):
        if not self._draggable or not self._drag_start:
            return
        sx, sy, wx, wy = self._drag_start
        nx = wx + (event.x_root - sx)
        ny = wy + (event.y_root - sy)
        self.win.geometry(f"+{nx}+{ny}")

    def _on_drag_end(self, event):
        if not self._draggable:
            return
        try:
            self.config["overlay_x"] = self.win.winfo_x()
            self.config["overlay_y"] = self.win.winfo_y()
            save_config(self.config)
        except Exception:
            logging.exception("save overlay pos")
        self._drag_start = None

    def reset_position(self):
        sw = self.win.winfo_screenwidth()
        x = sw - OVERLAY_RIGHT_MARGIN - OVERLAY_W
        y = OVERLAY_TOP_MARGIN
        self.win.geometry(f"{OVERLAY_W}x{OVERLAY_H}+{x}+{y}")
        self.config["overlay_x"] = x
        self.config["overlay_y"] = y
        save_config(self.config)

    def _force_topmost(self):
        if not WIN32_AVAILABLE or not self._hwnd_root:
            return
        try:
            _user32.SetWindowPos(
                wintypes.HWND(self._hwnd_root),
                wintypes.HWND(-1),
                0, 0, 0, 0,
                0x0002 | 0x0001 | 0x0010 | 0x0040,
            )
        except Exception:
            pass

    def _keep_topmost_loop(self):
        try:
            if self.visible and self.enabled:
                self._force_topmost()
        except Exception:
            logging.exception("keep_topmost")
        try:
            self.master.after(OVERLAY_TOP_REFRESH_MS, self._keep_topmost_loop)
        except Exception:
            pass

    def show(self):
        if not self.enabled:
            return
        try:
            self.win.deiconify()
            self.win.attributes("-topmost", True)
            self.win.lift()
            self.visible = True
            self._force_topmost()
        except Exception:
            logging.exception("overlay show")

    def hide(self):
        try: self.win.withdraw()
        except Exception: pass
        self.visible = False

    def set_enabled(self, flag: bool):
        self.enabled = flag
        if not flag: self.hide()

    def set_time(self, text: str, color: str = OVERLAY_TEXT):
        key = (text, color)
        if key == self._last_text:
            return
        self._last_text = key
        try:
            self.canvas.itemconfig(self.time_id, text=text, fill=color)
            self.canvas.itemconfig(self.shadow_id, text=text)
        except Exception:
            pass


# ============ ГАЛЕРЕЯ ============
class GalleryWindow(ctk.CTkToplevel):
    THUMB_W = 320
    THUMB_H = 180
    COLS    = 2

    def __init__(self, master, app):
        super().__init__(master)
        self.app = app

        self.title("🖼  Галерея снимков")
        self.geometry("740x680")
        self.minsize(500, 400)
        self.configure(fg_color=C["bg"])
        self.transient(master)
        try: self.iconbitmap(ensure_icon(C["accent"]))
        except Exception: pass

        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(16, 6))

        ctk.CTkLabel(
            hdr, text="🖼  Галерея снимков",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=C["text"], anchor="w",
        ).pack(side="left")

        ctk.CTkButton(
            hdr, text="📂 Папка",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            width=90, height=32, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"], border_width=1, border_color=C["border_soft"],
            command=lambda: open_folder_in_explorer(get_day_folder()),
        ).pack(side="right", padx=(6, 0))

        ctk.CTkButton(
            hdr, text="🔄 Обновить",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            width=110, height=32, corner_radius=10,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="#ffffff",
            command=self.reload,
        ).pack(side="right")

        self.counter_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            self, textvariable=self.counter_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C["text2"], anchor="w",
        ).pack(fill="x", padx=20, pady=(0, 8))

        self.scroll = ctk.CTkScrollableFrame(
            self, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        self.scroll.pack(fill="both", expand=True, padx=14, pady=(0, 14))

        for i in range(self.COLS):
            self.scroll.grid_columnconfigure(i, weight=1, uniform="col")

        self._thumbs = []
        self.reload()

    def reload(self):
        for w in self.scroll.winfo_children():
            w.destroy()
        self._thumbs.clear()

        paths = list_today_screenshots()
        self.counter_var.set(
            f"Сегодня ({datetime.now().strftime('%d.%m.%Y')}): "
            f"{len(paths)} снимков"
        )

        if not paths:
            ctk.CTkLabel(
                self.scroll, text="Пока пусто",
                font=ctk.CTkFont(family="Segoe UI", size=14),
                text_color=C["text3"],
            ).grid(row=0, column=0, columnspan=self.COLS, pady=60)
            return

        for idx, path in enumerate(paths):
            row = idx // self.COLS
            col = idx % self.COLS
            self._build_card(path, row, col)

    def _build_card(self, path: str, row: int, col: int):
        card = ctk.CTkFrame(
            self.scroll, corner_radius=14, fg_color=C["card"],
            border_width=1, border_color=C["border_soft"],
        )
        card.grid(row=row, column=col, sticky="nsew", padx=6, pady=6)

        try:
            img = Image.open(path)
            img.thumbnail((self.THUMB_W, self.THUMB_H), Image.LANCZOS)
            ctk_img = ctk.CTkImage(light_image=img, dark_image=img,
                                   size=img.size)
            self._thumbs.append(ctk_img)

            lbl = ctk.CTkLabel(card, text="", image=ctk_img, cursor="hand2")
            lbl.pack(padx=8, pady=(8, 4))
            lbl.bind("<Button-1>", lambda e, p=path: self._open(p))
        except Exception:
            ctk.CTkLabel(
                card, text="⚠️", text_color=C["red"],
                font=ctk.CTkFont(size=40),
            ).pack(pady=20)

        name = os.path.basename(path)
        try:
            size_kb = os.path.getsize(path) // 1024
            meta = f"{size_kb} КБ"
        except Exception:
            meta = ""

        info = ctk.CTkFrame(card, fg_color="transparent")
        info.pack(fill="x", padx=10, pady=(0, 2))

        ctk.CTkLabel(
            info, text=name,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=C["text"], anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            info, text=meta,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=C["text3"],
        ).pack(side="right")

        btns = ctk.CTkFrame(card, fg_color="transparent")
        btns.pack(fill="x", padx=8, pady=(4, 8))

        ctk.CTkButton(
            btns, text="📋", width=34, height=28, corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"],
            command=lambda p=path: self._copy(p),
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btns, text="📂", width=34, height=28, corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"],
            command=lambda p=path: self._open(p),
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btns, text="📁", width=34, height=28, corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"],
            command=lambda p=path: open_folder_in_explorer(
                os.path.dirname(p)),
        ).pack(side="left", padx=(0, 4))

        ctk.CTkButton(
            btns, text="🗑", width=34, height=28, corner_radius=8,
            font=ctk.CTkFont(size=12),
            fg_color=C["card_hover"], hover_color="#2a0e0e",
            text_color=C["red"],
            command=lambda p=path: self._delete(p),
        ).pack(side="right")

    def _open(self, path):
        try:
            os.startfile(path)
        except Exception:
            logging.exception("gallery open")

    def _copy(self, path):
        try:
            img = Image.open(path)
            if copy_image_to_clipboard(img):
                self.app.set_status(f"📋 {os.path.basename(path)} в буфере")
            else:
                self.app.set_status("❌ Буфер обмена недоступен")
        except Exception:
            logging.exception("gallery copy")

    def _delete(self, path):
        if not messagebox.askyesno("Удалить",
                                   f"Удалить {os.path.basename(path)}?"):
            return
        try:
            os.remove(path)
            self.reload()
            self.app.set_status("🗑 Удалено")
        except Exception:
            logging.exception("gallery delete")
            messagebox.showerror("Ошибка", "Не удалось удалить")


# ============ UI-ХЕЛПЕРЫ ============
def _make_card(parent, **kwargs):
    return ctk.CTkFrame(
        parent, corner_radius=16, fg_color=C["card"],
        border_width=1, border_color=C["border_soft"], **kwargs,
    )


def _make_primary_btn(parent, text, command, color_key="accent", **kwargs):
    opts = dict(
        text=text, command=command,
        font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
        height=48, corner_radius=14,
        fg_color=C[color_key], hover_color=C[color_key + "_h"],
        text_color="#ffffff",
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


def _make_secondary_btn(parent, text, command, **kwargs):
    opts = dict(
        text=text, command=command,
        font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
        height=42, corner_radius=12,
        fg_color=C["card_hover"], hover_color=C["border"],
        text_color=C["text"], border_width=1, border_color=C["border_soft"],
    )
    opts.update(kwargs)
    return ctk.CTkButton(parent, **opts)


# ============ ОСНОВНОЕ ОКНО ============
class ScreenshotApp:
    def __init__(self, root: ctk.CTk):
        self.root = root

        self.config = load_config()
        apply_accent(self.config.get("accent_theme", "purple"), self.config)

        self.hotkey = self.config.get("hotkey", "print screen")
        self.monitor_index = int(self.config.get("monitor_index", 0))
        self.interval_minutes = max(1, int(self.config.get("interval_minutes", 21)))
        self.hotkey_handle = None
        self._capturing = False

        self.auto_enabled = False
        self.next_auto_time = 0.0
        self.detected_game = None
        self.action_queue = queue.Queue()
        self.icon = None
        self.update_info = None
        self.monitors = []
        self.last_screenshot_path = None
        self.gallery_win = None

        self._resizing = False
        self._resize_job = None
        self._last_countdown_text = None
        self._stats_cache = {"today": 0, "total": 0}
        self._stats_running = False
        self._preview_ctk_img = None
        self._preview_src_path = None

        self._build_ui()
        self.toast = ToastManager(self.root)
        self.flash = FlashAnimation(self.root)
        self.overlay = OverlayTimer(self.root, self.config)
        self.overlay_btn.configure(text="📺  Оверлей: ВКЛ")
        self.overlay.show()
        self.overlay.set_time("—:—", C["text3"])
        self.overlay.set_draggable(True)

        self.process_queue()
        self._update_countdown()
        self._update_statistics()
        self._update_preview()
        self.start_game_watcher()
        self.start_daily_cleanup()
        self.setup_hotkey()
        self.start_tray()
        self.cleanup_async(show_result=False)

        self.monitors = enumerate_monitors()
        threading.Thread(target=self._check_updates_worker, daemon=True).start()

    def _build_ui(self):
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("dark-blue")

        r = self.root
        r.title(f"Game Screenshoter  •  v{APP_VERSION}")
        r.minsize(360, 400)
        r.configure(fg_color=C["bg"])
        r.resizable(True, True)
        r.protocol("WM_DELETE_WINDOW", self.hide_to_tray)
        try: r.iconbitmap(ensure_icon(C["accent"]))
        except Exception: logging.exception("iconbitmap")

        self._apply_saved_geometry()
        r.bind("<Configure>", self._on_root_configure, add="+")

        self.update_banner = ctk.CTkFrame(
            r, corner_radius=12,
            fg_color="#0e2a2f", border_width=1, border_color="#0e7490",
        )
        self.banner_text = ctk.StringVar(value="")
        ctk.CTkLabel(
            self.update_banner, textvariable=self.banner_text,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#67e8f9", anchor="w", justify="left",
        ).pack(side="left", fill="x", expand=True, padx=(12, 6), pady=8)
        ctk.CTkButton(
            self.update_banner, text="Скачать",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            width=80, height=28, corner_radius=8,
            fg_color="#0891b2", hover_color="#0e7490", text_color="#ffffff",
            command=self._open_update_url,
        ).pack(side="right", padx=(0, 10), pady=8)

        hdr = ctk.CTkFrame(r, fg_color="transparent")
        hdr.pack(fill="x", padx=16, pady=(14, 4))

        title_row = ctk.CTkFrame(hdr, fg_color="transparent")
        title_row.pack(fill="x")
        ctk.CTkLabel(
            title_row, text="🎮",
            font=ctk.CTkFont(family="Segoe UI Emoji", size=22),
            text_color=C["accent_glow"],
        ).pack(side="left", padx=(0, 8))
        ctk.CTkLabel(
            title_row, text="Game Screenshoter",
            font=ctk.CTkFont(family="Segoe UI", size=20, weight="bold"),
            text_color=C["text"], anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            hdr, text="Автоматический захват игрового экрана",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C["text2"], anchor="w",
        ).pack(fill="x", pady=(2, 0))

        scroll = ctk.CTkScrollableFrame(
            r, fg_color="transparent", corner_radius=0,
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        scroll.pack(fill="both", expand=True, padx=0, pady=(4, 0))

        # HINT CARD
        hint_card = ctk.CTkFrame(
            scroll, corner_radius=14, fg_color="#2a1f0a",
            border_width=1, border_color="#4a3a12",
        )
        hint_card.pack(fill="x", padx=16, pady=(6, 6))
        hrow = ctk.CTkFrame(hint_card, fg_color="transparent")
        hrow.pack(fill="x", padx=12, pady=8)
        ctk.CTkLabel(
            hrow, text="💡",
            font=ctk.CTkFont(family="Segoe UI Emoji", size=16),
            text_color=C["yellow"],
        ).pack(side="left", padx=(0, 8), anchor="n")
        ctk.CTkLabel(
            hrow,
            text="Для корректной работы игра должна быть\n"
                 "в режиме «Оконный без рамки» (Windowed Borderless)",
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color="#f5d68a", anchor="w", justify="left",
        ).pack(side="left", fill="x", expand=True)

        # GAME CARD
        self.game_card = _make_card(scroll)
        self.game_card.pack(fill="x", padx=16, pady=(0, 6))
        inner = ctk.CTkFrame(self.game_card, fg_color="transparent")
        inner.pack(fill="x", padx=14, pady=10)

        self.dot = ctk.CTkLabel(
            inner, text="●", width=14,
            font=ctk.CTkFont(size=18), text_color=C["text3"])
        self.dot.pack(side="left", anchor="n", pady=(2, 0))

        texts = ctk.CTkFrame(inner, fg_color="transparent")
        texts.pack(side="left", fill="x", expand=True, padx=(8, 0))

        self.game_status_var = ctk.StringVar(value="Игра не найдена")
        ctk.CTkLabel(
            texts, textvariable=self.game_status_var,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            text_color=C["text"], anchor="w",
        ).pack(fill="x")

        self.game_detail_var = ctk.StringVar(
            value="Ожидание GTA5.exe / Majestic.exe")
        ctk.CTkLabel(
            texts, textvariable=self.game_detail_var,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=C["text2"], anchor="w",
            wraplength=280, justify="left",
        ).pack(fill="x", pady=(2, 0))

        # HOTKEY CARD
        hcard = _make_card(scroll)
        hcard.pack(fill="x", padx=16, pady=(0, 6))
        hrow = ctk.CTkFrame(hcard, fg_color="transparent")
        hrow.pack(fill="x", padx=14, pady=8)

        ctk.CTkLabel(
            hrow, text="⌨️",
            font=ctk.CTkFont(family="Segoe UI Emoji", size=20),
            text_color=C["accent_glow"],
        ).pack(side="left", padx=(0, 8))

        hcol = ctk.CTkFrame(hrow, fg_color="transparent")
        hcol.pack(side="left", fill="x", expand=True)

        ctk.CTkLabel(
            hcol, text="ХОТКЕЙ СКРИНШОТА",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"], anchor="w",
        ).pack(fill="x")

        self.hotkey_label_var = ctk.StringVar(
            value=self.hotkey.upper() if self.hotkey else "—")
        ctk.CTkLabel(
            hcol, textvariable=self.hotkey_label_var,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=C["text"], anchor="w",
        ).pack(fill="x")

        self.hotkey_btn = ctk.CTkButton(
            hrow, text="Изменить",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            width=96, height=32, corner_radius=10,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="#ffffff",
            command=self.start_capture_hotkey,
        )
        self.hotkey_btn.pack(side="right")

        # TIMER CARD
        tcard = _make_card(scroll)
        tcard.pack(fill="x", padx=16, pady=(0, 8))

        ctk.CTkLabel(
            tcard, text="ДО СЛЕДУЮЩЕГО СНИМКА",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(pady=(14, 0))

        self.countdown_label = ctk.CTkLabel(
            tcard, text="—:—",
            font=ctk.CTkFont(family="Segoe UI", size=42, weight="bold"),
            text_color=C["text3"],
        )
        self.countdown_label.pack(pady=(0, 2))

        self.timer_hint = ctk.CTkLabel(
            tcard, text=self._timer_hint_text(),
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=C["text2"],
        )
        self.timer_hint.pack(pady=(0, 6))

        ctk.CTkFrame(
            tcard, height=1, fg_color=C["border_soft"]
        ).pack(fill="x", padx=14, pady=(2, 0))

        self.stats_var = ctk.StringVar(value="Сегодня: 0  •  Всего: 0")
        ctk.CTkLabel(
            tcard, textvariable=self.stats_var,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=C["text2"],
        ).pack(pady=(6, 12))

        # PREVIEW CARD
        self.preview_card = ctk.CTkFrame(
            scroll, corner_radius=14, fg_color=C["card"],
            border_width=1, border_color=C["border_soft"],
        )

        prev_row = ctk.CTkFrame(self.preview_card, fg_color="transparent")
        prev_row.pack(fill="x", padx=12, pady=10)

        self.preview_thumb_lbl = ctk.CTkLabel(
            prev_row, text="📸",
            font=ctk.CTkFont(size=32),
            width=PREVIEW_W, height=PREVIEW_H,
            fg_color=C["card_hover"], corner_radius=10,
            cursor="hand2",
        )
        self.preview_thumb_lbl.pack(side="left", padx=(0, 10))
        self.preview_thumb_lbl.bind("<Button-1>",
                                     lambda e: self._open_last_screenshot())

        pcol = ctk.CTkFrame(prev_row, fg_color="transparent")
        pcol.pack(side="left", fill="both", expand=True)

        ctk.CTkLabel(
            pcol, text="ПОСЛЕДНИЙ СНИМОК",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"], anchor="w",
        ).pack(fill="x")

        self.preview_name_var = ctk.StringVar(value="—")
        ctk.CTkLabel(
            pcol, textvariable=self.preview_name_var,
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color=C["text"], anchor="w", justify="left",
            wraplength=180,
        ).pack(fill="x", pady=(2, 2))

        self.preview_time_var = ctk.StringVar(value="")
        ctk.CTkLabel(
            pcol, textvariable=self.preview_time_var,
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=C["text3"], anchor="w",
        ).pack(fill="x")

        # PRIMARY
        self.manual_btn = _make_primary_btn(
            scroll, "📸   СДЕЛАТЬ СКРИНШОТ",
            command=self.manual_shot, color_key="accent",
        )
        self.manual_btn.pack(fill="x", padx=16, pady=(2, 6))

        _make_secondary_btn(
            scroll, "🖼  Галерея снимков",
            command=self.open_gallery, height=46,
        ).pack(fill="x", padx=16, pady=(0, 6))

        row1 = ctk.CTkFrame(scroll, fg_color="transparent")
        row1.pack(fill="x", padx=16, pady=2)
        row1.grid_columnconfigure(0, weight=1)
        row1.grid_columnconfigure(1, weight=1)

        self.auto_btn = _make_primary_btn(
            row1, "▶  Авто", command=self.toggle_auto,
            color_key="green", height=42,
        )
        self.auto_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        _make_secondary_btn(
            row1, "📂  Папка", command=self.open_today_folder,
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        row2 = ctk.CTkFrame(scroll, fg_color="transparent")
        row2.pack(fill="x", padx=16, pady=2)
        row2.grid_columnconfigure(0, weight=1)
        row2.grid_columnconfigure(1, weight=1)

        self.overlay_btn = _make_secondary_btn(
            row2, "📺  Оверлей: ВКЛ", command=self.toggle_overlay,
        )
        self.overlay_btn.grid(row=0, column=0, sticky="ew", padx=(0, 3))

        _make_secondary_btn(
            row2, "📝  Логи", command=self.open_logs_folder,
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        row3 = ctk.CTkFrame(scroll, fg_color="transparent")
        row3.pack(fill="x", padx=16, pady=2)
        row3.grid_columnconfigure(0, weight=1)
        row3.grid_columnconfigure(1, weight=1)

        _make_secondary_btn(
            row3, "🧹  Очистка", command=self.cleanup_now,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))

        _make_secondary_btn(
            row3, "⚙️  Настройки", command=self.open_settings,
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        row4 = ctk.CTkFrame(scroll, fg_color="transparent")
        row4.pack(fill="x", padx=16, pady=2)
        row4.grid_columnconfigure(0, weight=1)
        row4.grid_columnconfigure(1, weight=1)

        _make_secondary_btn(
            row4, "🔍  Проверка", command=self.open_diagnostics,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))

        _make_secondary_btn(
            row4, "🔄  Обновления", command=self.check_updates_now,
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        exit_row = ctk.CTkFrame(scroll, fg_color="transparent")
        exit_row.pack(fill="x", padx=16, pady=(6, 8))
        exit_row.grid_columnconfigure(0, weight=1)
        exit_row.grid_columnconfigure(1, weight=1)

        ctk.CTkButton(
            exit_row, text="🗕  В трей",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=36, corner_radius=10,
            fg_color="transparent", hover_color=C["card_hover"],
            text_color=C["text2"], border_width=1, border_color=C["border_soft"],
            command=self.hide_to_tray,
        ).grid(row=0, column=0, sticky="ew", padx=(0, 3))

        ctk.CTkButton(
            exit_row, text="❌  Выход",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=36, corner_radius=10,
            fg_color="transparent", hover_color="#2a0e0e",
            text_color=C["red"], border_width=1, border_color=C["border_soft"],
            command=self.quit_app,
        ).grid(row=0, column=1, sticky="ew", padx=(3, 0))

        self.status_var = ctk.StringVar(value=f"Готов  •  v{APP_VERSION}")
        ctk.CTkLabel(
            r, textvariable=self.status_var,
            font=ctk.CTkFont(family="Segoe UI", size=10),
            text_color=C["text3"],
        ).pack(side="bottom", pady=(0, 8))

    def _timer_hint_text(self) -> str:
        return f"Авто каждые {self.interval_minutes} мин"

    # ---------- resize ----------
    def _on_root_configure(self, event):
        if event.widget is not self.root:
            return
        self._resizing = True
        if self._resize_job is not None:
            try:
                self.root.after_cancel(self._resize_job)
            except Exception:
                pass
        self._resize_job = self.root.after(RESIZE_DEBOUNCE_MS,
                                           self._on_resize_end)

    def _on_resize_end(self):
        self._resizing = False
        self._resize_job = None

    # ---------- геометрия ----------
    def _apply_saved_geometry(self):
        try:
            w = int(self.config.get("window_width", 400))
            h = int(self.config.get("window_height", 900))
            x = self.config.get("window_x")
            y = self.config.get("window_y")
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()

            if w < 360: w = 360
            if h < 400: h = 400
            if w > sw:  w = sw - 40
            if h > sh:  h = sh - 80

            if x is not None and y is not None:
                x, y = int(x), int(y)
                if x < 0 or x > sw - 200: x = None
                if y < 0 or y > sh - 200: y = None

            if x is not None and y is not None:
                self.root.geometry(f"{w}x{h}+{x}+{y}")
            else:
                self.root.geometry(f"{w}x{h}")
        except Exception:
            logging.exception("_apply_saved_geometry")
            self.root.geometry("400x900")

    def _save_current_geometry(self):
        try:
            if self._resizing:
                return
            self.root.update_idletasks()
            w = self.root.winfo_width()
            h = self.root.winfo_height()
            x = self.root.winfo_x()
            y = self.root.winfo_y()
            if self.root.state() == "withdrawn" or w < 50 or h < 50:
                return
            self.config["window_width"]  = w
            self.config["window_height"] = h
            self.config["window_x"]      = x
            self.config["window_y"]      = y
            save_config(self.config)
            self.set_status("✅ Размер окна сохранён")
        except Exception:
            logging.exception("_save_current_geometry")

    def _reset_window_size(self):
        try:
            w, h = 400, 900
            sw = self.root.winfo_screenwidth()
            sh = self.root.winfo_screenheight()
            x = (sw - w) // 2
            y = max(20, (sh - h) // 2 - 20)
            self.config["window_width"]  = w
            self.config["window_height"] = h
            self.config["window_x"]      = x
            self.config["window_y"]      = y
            save_config(self.config)
            self.root.geometry(f"{w}x{h}+{x}+{y}")
            self.root.update_idletasks()
            self.set_status("✅ Размер окна сброшен")
        except Exception:
            logging.exception("_reset_window_size")

    # ---------- очереди ----------
    def process_queue(self):
        try:
            while True: self.action_queue.get_nowait()()
        except queue.Empty: pass
        self.root.after(60, self.process_queue)

    def run_on_main(self, func, *args, **kwargs):
        if threading.current_thread() is threading.main_thread():
            return func(*args, **kwargs)
        box, done = [None], threading.Event()

        def wrapper():
            try:    box[0] = (func(*args, **kwargs), None)
            except Exception as e: box[0] = (None, e)
            finally: done.set()

        self.action_queue.put(wrapper)
        done.wait()
        res, err = box[0]
        if err: raise err
        return res

    def set_status(self, text):
        if threading.current_thread() is threading.main_thread():
            self.status_var.set(text)
        else:
            self.action_queue.put(lambda: self.status_var.set(text))

    # ---------- превью ----------
    def _update_preview(self):
        try:
            paths = list_today_screenshots()
            if paths:
                newest = paths[0]
                if newest != self._preview_src_path:
                    self._preview_src_path = newest
                    self._refresh_preview_card(newest)
                try:
                    mtime = datetime.fromtimestamp(os.path.getmtime(newest))
                    delta = datetime.now() - mtime
                    sec = int(delta.total_seconds())
                    if sec < 60:
                        rel = f"{sec} сек назад"
                    elif sec < 3600:
                        rel = f"{sec // 60} мин назад"
                    else:
                        rel = mtime.strftime("%H:%M:%S")
                    self.preview_time_var.set(rel)
                except Exception:
                    pass
                if not self.preview_card.winfo_ismapped():
                    self.preview_card.pack(
                        fill="x", padx=16, pady=(0, 8),
                        before=self.manual_btn)
            else:
                if self.preview_card.winfo_ismapped():
                    self.preview_card.pack_forget()
        except Exception:
            logging.exception("_update_preview")
        self.root.after(3000, self._update_preview)

    def _refresh_preview_card(self, path: str):
        try:
            img = Image.open(path)
            img.thumbnail((PREVIEW_W, PREVIEW_H), Image.LANCZOS)
            self._preview_ctk_img = ctk.CTkImage(
                light_image=img, dark_image=img, size=img.size)
            self.preview_thumb_lbl.configure(
                image=self._preview_ctk_img, text="")
        except Exception:
            logging.exception("preview thumb")
            self.preview_thumb_lbl.configure(image=None, text="📸")

        self.preview_name_var.set(os.path.basename(path))

    def _open_last_screenshot(self):
        p = self._preview_src_path or self.last_screenshot_path
        if p and os.path.isfile(p):
            try:
                os.startfile(p)
            except Exception:
                logging.exception("open last")

    # ---------- статистика ----------
    def _update_statistics(self):
        if not self._resizing and not self._stats_running:
            self._stats_running = True
            threading.Thread(target=self._stats_worker, daemon=True).start()
        self.root.after(STATS_REFRESH_SEC * 1000, self._update_statistics)

    def _stats_worker(self):
        try:
            st = count_screenshots()
            self._stats_cache = st
            text = f"Сегодня: {st['today']}  •  Всего: {st['total']}"
            self.action_queue.put(lambda: self.stats_var.set(text))
        except Exception:
            logging.exception("stats worker")
        finally:
            self._stats_running = False

    # ---------- обновления ----------
    def _check_updates_worker(self):
        try:
            if not self.config.get("update_check", True):
                return
            repo = (self.config.get("github_repo") or "").strip()
            if not repo:
                return
            info = check_for_updates(repo)
            if info:
                self.update_info = info
                self.run_on_main(self._show_update_banner, info)
        except Exception:
            logging.exception("_check_updates_worker")

    def _show_update_banner(self, info: dict):
        self.banner_text.set(
            f"🎉 Доступна новая версия: v{info['version']}")
        self.update_banner.pack(
            fill="x", padx=16, pady=(8, 0),
            before=self.root.winfo_children()[0])

    def _open_update_url(self):
        if self.update_info and self.update_info.get("url"):
            try:
                webbrowser.open(self.update_info["url"])
            except Exception:
                logging.exception("open update url")

    def check_updates_now(self):
        def worker():
            repo = (self.config.get("github_repo") or "").strip()
            if not repo:
                self.run_on_main(messagebox.showinfo, "Обновления",
                                 "GitHub-репозиторий не указан.\n"
                                 "Открой ⚙️ Настройки и укажи 'user/repo'.")
                return
            self.set_status("🔄 Проверка обновлений…")
            info = check_for_updates(repo)
            if info:
                self.update_info = info
                self.run_on_main(self._show_update_banner, info)
                self.run_on_main(
                    messagebox.showinfo, "Обновления",
                    f"Доступна новая версия: v{info['version']}")
            else:
                self.run_on_main(
                    messagebox.showinfo, "Обновления",
                    f"У вас актуальная версия v{APP_VERSION}.")
                self.set_status(f"✅ Актуальная версия v{APP_VERSION}")
        threading.Thread(target=worker, daemon=True).start()

    # ---------- галерея ----------
    def open_gallery(self):
        try:
            if self.gallery_win is not None and self.gallery_win.winfo_exists():
                self.gallery_win.reload()
                self.gallery_win.lift()
                self.gallery_win.focus_force()
                return
            self.gallery_win = GalleryWindow(self.root, self)
        except Exception:
            logging.exception("open_gallery")

    # ---------- настройки ----------
    def open_settings(self):
        win = ctk.CTkToplevel(self.root)
        win.title("⚙️ Настройки")
        win.geometry("420x980")
        win.resizable(False, False)
        win.configure(fg_color=C["bg"])
        win.transient(self.root)
        win.grab_set()
        try: win.iconbitmap(ensure_icon(C["accent"]))
        except Exception: pass

        # Скроллфрейм на всё окно — чтобы точно ничего не обрезалось
        root_scroll = ctk.CTkScrollableFrame(
            win, fg_color="transparent",
            scrollbar_button_color=C["border"],
            scrollbar_button_hover_color=C["accent"],
        )
        root_scroll.pack(fill="both", expand=True)

        ctk.CTkLabel(
            root_scroll, text="⚙️  Настройки",
            font=ctk.CTkFont(family="Segoe UI", size=18, weight="bold"),
            text_color=C["text"],
        ).pack(anchor="w", padx=20, pady=(18, 4))

        ctk.CTkLabel(
            root_scroll, text=f"Версия {APP_VERSION}",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C["text2"],
        ).pack(anchor="w", padx=20, pady=(0, 12))

        # ============ ИНТЕРВАЛ АВТОСНИМКОВ ============
        ctk.CTkLabel(
            root_scroll, text="ИНТЕРВАЛ АВТОСНИМКОВ",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(0, 4))

        # Поле ввода + подпись "минут"
        int_row = ctk.CTkFrame(root_scroll, fg_color="transparent")
        int_row.pack(fill="x", padx=20, pady=(0, 6))

        self._interval_var = ctk.StringVar(value=str(self.interval_minutes))
        interval_entry = ctk.CTkEntry(
            int_row, textvariable=self._interval_var,
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            fg_color=C["card_hover"], border_color=C["border_soft"],
            text_color=C["text"], placeholder_text="21",
            width=100, height=40, corner_radius=10,
        )
        interval_entry.pack(side="left")

        ctk.CTkLabel(
            int_row, text="минут  (мин. 1, макс. 999)",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C["text2"],
        ).pack(side="left", padx=(10, 0))

        # Быстрые кнопки
        quick_row = ctk.CTkFrame(root_scroll, fg_color="transparent")
        quick_row.pack(fill="x", padx=20, pady=(0, 6))

        for v in (5, 10, 15, 20, 30, 60):
            ctk.CTkButton(
                quick_row, text=str(v),
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                width=44, height=32, corner_radius=8,
                fg_color=C["card_hover"], hover_color=C["accent"],
                text_color=C["text"],
                command=lambda x=v: self._interval_var.set(str(x)),
            ).pack(side="left", padx=(0, 5))

        ctk.CTkLabel(
            root_scroll,
            text="Изменение интервала применится сразу после сохранения",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(0, 14))

        # ============ ТЕМА ============
        ctk.CTkLabel(
            root_scroll, text="ЦВЕТОВАЯ ТЕМА",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(0, 4))

        theme_names = [ACCENTS[k]["name"] for k in ACCENTS]
        current_key = self.config.get("accent_theme", "purple")
        current_name = ACCENTS.get(current_key, ACCENTS["purple"])["name"]

        self._theme_var = ctk.StringVar(value=current_name)
        ctk.CTkOptionMenu(
            root_scroll, values=theme_names,
            variable=self._theme_var,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=C["card_hover"], button_color=C["accent"],
            button_hover_color=C["accent_h"],
            dropdown_fg_color=C["card"],
            dropdown_hover_color=C["accent"],
            width=380, height=36, corner_radius=10,
        ).pack(padx=20, pady=(0, 6))

        ctk.CTkLabel(
            root_scroll, text="После сохранения приложение перезапустится автоматически",
            font=ctk.CTkFont(family="Segoe UI", size=9),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(0, 12))

        # ============ МОНИТОР ============
        ctk.CTkLabel(
            root_scroll, text="МОНИТОР ДЛЯ ЗАХВАТА",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20)

        monitors = enumerate_monitors()
        monitor_names = ["Все мониторы (по умолчанию)"]
        for i, m in enumerate(monitors, 1):
            monitor_names.append(f"Монитор {i} ({m['width']}×{m['height']})")

        self._settings_monitor = ctk.StringVar(
            value=monitor_names[self.monitor_index]
            if 0 <= self.monitor_index < len(monitor_names)
            else monitor_names[0])

        ctk.CTkOptionMenu(
            root_scroll, values=monitor_names,
            variable=self._settings_monitor,
            font=ctk.CTkFont(family="Segoe UI", size=11),
            dropdown_font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=C["card_hover"], button_color=C["accent"],
            button_hover_color=C["accent_h"],
            dropdown_fg_color=C["card"],
            dropdown_hover_color=C["accent"],
            width=380, height=36, corner_radius=10,
        ).pack(padx=20, pady=(4, 12))

        # ============ ТУМБЛЕРЫ ============
        ctk.CTkLabel(
            root_scroll, text="ПОВЕДЕНИЕ",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(0, 4))

        self._cb_copy = ctk.BooleanVar(
            value=bool(self.config.get("copy_to_clipboard", True)))
        self._cb_sound = ctk.BooleanVar(
            value=bool(self.config.get("play_sound", True)))
        self._cb_toast = ctk.BooleanVar(
            value=bool(self.config.get("show_toast", True)))
        self._cb_flash = ctk.BooleanVar(
            value=bool(self.config.get("flash_effect", True)))
        self._cb_autohide = ctk.BooleanVar(
            value=bool(self.config.get("overlay_auto_hide", True)))
        self._cb_update = ctk.BooleanVar(
            value=bool(self.config.get("update_check", True)))

        for var, label in [
            (self._cb_copy,     "📋 Копировать снимок в буфер обмена"),
            (self._cb_sound,    "🔊 Звук при снимке"),
            (self._cb_toast,    "🔔 Всплывающее уведомление"),
            (self._cb_flash,    "⚡ Вспышка при снимке"),
            (self._cb_autohide, "🎯 Скрывать оверлей, когда игра не запущена"),
            (self._cb_update,   "🔄 Проверять обновления при запуске"),
        ]:
            ctk.CTkCheckBox(
                root_scroll, text=label, variable=var,
                font=ctk.CTkFont(family="Segoe UI", size=11),
                text_color=C["text"],
                fg_color=C["accent"], hover_color=C["accent_h"],
                border_color=C["border"], checkmark_color="#ffffff",
                corner_radius=6, height=24,
            ).pack(anchor="w", padx=20, pady=2)

        # ============ GITHUB ============
        ctk.CTkLabel(
            root_scroll, text="GITHUB-РЕПОЗИТОРИЙ (user/repo)",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(12, 0))

        self._settings_repo = ctk.StringVar(
            value=self.config.get("github_repo", ""))
        ctk.CTkEntry(
            root_scroll, textvariable=self._settings_repo,
            placeholder_text="например: username/GameScreenshoter",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            fg_color=C["card_hover"], border_color=C["border_soft"],
            text_color=C["text"], placeholder_text_color=C["text3"],
            height=36, corner_radius=10,
        ).pack(fill="x", padx=20, pady=(4, 12))

        # ============ ОВЕРЛЕЙ ============
        ctk.CTkLabel(
            root_scroll, text="ОВЕРЛЕЙ",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(4, 4))

        ov_row = ctk.CTkFrame(root_scroll, fg_color="transparent")
        ov_row.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkButton(
            ov_row, text="↺ Вернуть в угол",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=32, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"], border_width=1, border_color=C["border_soft"],
            command=self.overlay.reset_position,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))

        ctk.CTkButton(
            ov_row, text="📋 Копировать последний",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=32, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"], border_width=1, border_color=C["border_soft"],
            command=self.copy_last_screenshot,
        ).pack(side="right", fill="x", expand=True, padx=(3, 0))

        # ============ РАЗМЕР ОКНА ============
        ctk.CTkLabel(
            root_scroll, text="РАЗМЕР ОКНА",
            font=ctk.CTkFont(family="Segoe UI", size=9, weight="bold"),
            text_color=C["text3"],
        ).pack(anchor="w", padx=20, pady=(0, 4))

        size_row = ctk.CTkFrame(root_scroll, fg_color="transparent")
        size_row.pack(fill="x", padx=20, pady=(0, 12))

        ctk.CTkButton(
            size_row, text="💾 Сохранить",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=34, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"], border_width=1, border_color=C["border_soft"],
            command=self._save_current_geometry,
        ).pack(side="left", fill="x", expand=True, padx=(0, 3))

        ctk.CTkButton(
            size_row, text="↺ Сбросить",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            height=34, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"], border_width=1, border_color=C["border_soft"],
            command=self._reset_window_size,
        ).pack(side="right", fill="x", expand=True, padx=(3, 0))

        # ============ КНОПКИ ============
        btns = ctk.CTkFrame(root_scroll, fg_color="transparent")
        btns.pack(fill="x", padx=20, pady=(8, 20))

        ctk.CTkButton(
            btns, text="Отмена",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=38, corner_radius=10,
            fg_color=C["card_hover"], hover_color=C["border"],
            text_color=C["text"],
            command=win.destroy,
        ).pack(side="left", fill="x", expand=True, padx=(0, 5))

        ctk.CTkButton(
            btns, text="Сохранить",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=38, corner_radius=10,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="#ffffff",
            command=lambda: self._save_settings(win, monitor_names, theme_names),
        ).pack(side="right", fill="x", expand=True, padx=(5, 0))

    def _restart_for_theme(self):
        try:
            if getattr(sys, "frozen", False):
                args = [sys.executable] + sys.argv[1:]
                flags = 0
                if hasattr(subprocess, "DETACHED_PROCESS"):
                    flags = subprocess.DETACHED_PROCESS
                subprocess.Popen(args, close_fds=True, creationflags=flags)
            else:
                py = sys.executable
                pyw = os.path.join(os.path.dirname(py), "pythonw.exe")
                exe = pyw if os.path.exists(pyw) else py
                script = os.path.abspath(__file__)
                args = [exe, script] + sys.argv[1:]
                subprocess.Popen(args, close_fds=True)
            logging.info("Перезапуск для применения темы")
        except Exception:
            logging.exception("_restart_for_theme launch")

        try:
            if self.icon: self.icon.stop()
        except Exception: pass
        try: keyboard.unhook_all_hotkeys()
        except Exception: pass
        try: self.overlay.hide()
        except Exception: pass
        self.auto_enabled = False
        try:
            self._save_current_geometry()
        except Exception: pass
        self.action_queue.put(self.root.destroy)

    def _save_settings(self, window, monitor_names, theme_names):
        theme_changed = False
        interval_changed = False
        try:
            # --- Интервал ---
            raw = (self._interval_var.get() or "").strip()
            try:
                new_interval = int(raw)
            except ValueError:
                messagebox.showerror(
                    "Неверный интервал",
                    "Введите целое число минут (от 1 до 999).")
                return
            if new_interval < 1 or new_interval > 999:
                messagebox.showerror(
                    "Неверный интервал",
                    "Интервал должен быть от 1 до 999 минут.")
                return
            if new_interval != self.interval_minutes:
                interval_changed = True
            self.interval_minutes = new_interval
            self.config["interval_minutes"] = new_interval

            # --- Монитор ---
            name = self._settings_monitor.get()
            idx = 0
            if name in monitor_names:
                idx = monitor_names.index(name)
            self.monitor_index = idx
            self.config["monitor_index"] = idx

            # --- Тумблеры ---
            self.config["update_check"]      = bool(self._cb_update.get())
            self.config["copy_to_clipboard"] = bool(self._cb_copy.get())
            self.config["play_sound"]        = bool(self._cb_sound.get())
            self.config["show_toast"]        = bool(self._cb_toast.get())
            self.config["flash_effect"]      = bool(self._cb_flash.get())
            self.config["overlay_auto_hide"] = bool(self._cb_autohide.get())
            self.config["github_repo"]       = self._settings_repo.get().strip()

            # --- Тема ---
            old_theme_key = self.config.get("accent_theme", "purple")
            new_theme_name = self._theme_var.get()
            new_theme_key = old_theme_key
            for k, v in ACCENTS.items():
                if v["name"] == new_theme_name:
                    new_theme_key = k
                    break
            self.config["accent_theme"] = new_theme_key
            theme_changed = (new_theme_key != old_theme_key)

            save_config(self.config)

            # --- Применяем настройки сразу ---
            # Подсказка под таймером
            try:
                self.timer_hint.configure(text=self._timer_hint_text())
            except Exception:
                pass

            # Если авто-режим активен и интервал изменился — пересчитываем таймер
            if interval_changed and self.auto_enabled:
                self.next_auto_time = time.time() + self.interval_minutes * 60
                try:
                    self.toast.show(
                        "Интервал изменён",
                        f"Следующий снимок через {self.interval_minutes} мин")
                except Exception:
                    pass

            if self.config["overlay_auto_hide"] and not self.detected_game:
                self.overlay.hide()
            elif not self.config["overlay_auto_hide"]:
                self.overlay.show()

            if interval_changed:
                self.set_status(
                    f"✅ Интервал: {self.interval_minutes} мин")
            else:
                self.set_status("✅ Настройки сохранены")

        except Exception:
            logging.exception("_save_settings")
            theme_changed = False
        finally:
            try:
                window.destroy()
            except Exception:
                pass

        if theme_changed:
            self.set_status("🎨 Применяю тему…")
            try:
                self.toast.show("Смена темы", "Перезапуск через секунду")
            except Exception:
                pass
            self.root.after(900, self._restart_for_theme)

    # ---------- диагностика ----------
    def open_diagnostics(self):
        win = ctk.CTkToplevel(self.root)
        win.title("🔍 Проверка системы")
        win.geometry("420x560")
        win.resizable(False, False)
        win.configure(fg_color=C["bg"])
        win.transient(self.root)

        ctk.CTkLabel(
            win, text="🔍  Проверка системы",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=C["text"],
        ).pack(anchor="w", padx=20, pady=(16, 4))

        ctk.CTkLabel(
            win, text="Автоматическая диагностика",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=C["text2"],
        ).pack(anchor="w", padx=20, pady=(0, 12))

        results_frame = ctk.CTkScrollableFrame(
            win, fg_color=C["card"], corner_radius=12,
            border_width=1, border_color=C["border_soft"],
        )
        results_frame.pack(fill="both", expand=True, padx=20, pady=(0, 12))

        for name, status, detail in self._run_self_tests():
            row = ctk.CTkFrame(results_frame, fg_color="transparent")
            row.pack(fill="x", padx=8, pady=3)

            if status is True:
                icon, color = "✅", C["green"]
            elif status is False:
                icon, color = "❌", C["red"]
            else:
                icon, color = "⚠️", C["yellow"]

            ctk.CTkLabel(
                row, text=icon, width=22,
                font=ctk.CTkFont(size=13),
            ).pack(side="left")

            ctk.CTkLabel(
                row, text=name,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=color, anchor="w", width=160,
            ).pack(side="left")

            ctk.CTkLabel(
                row, text=detail,
                font=ctk.CTkFont(family="Segoe UI", size=10),
                text_color=C["text2"], anchor="w",
                wraplength=170, justify="left",
            ).pack(side="left", fill="x", expand=True)

        ctk.CTkButton(
            win, text="Закрыть",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=38, corner_radius=10,
            fg_color=C["accent"], hover_color=C["accent_h"],
            text_color="#ffffff",
            command=win.destroy,
        ).pack(fill="x", padx=20, pady=(0, 16))

    def _run_self_tests(self):
        results = []

        try:
            p = os.path.join(DATA_DIR, ".test_write")
            with open(p, "w", encoding="utf-8") as f: f.write("ok")
            os.remove(p)
            results.append(("Доступ на запись", True, DATA_DIR))
        except Exception as e:
            results.append(("Доступ на запись", False, str(e)))

        try:
            get_day_folder()
            results.append(("Создание папок", True, "OK"))
        except Exception as e:
            results.append(("Создание папок", False, str(e)))

        if self.hotkey_handle:
            results.append(("Хоткей", True, self.hotkey.upper()))
        else:
            results.append(("Хоткей", False, "не зарегистрирован"))

        if WIN32_AVAILABLE:
            results.append(("Windows API", True, "pywin32 доступен"))
        else:
            results.append(("Windows API", False, "pywin32 не установлен"))

        if CLIPBOARD_AVAILABLE:
            results.append(("Буфер обмена", True, "доступен"))
        else:
            results.append(("Буфер обмена", False, "win32clipboard нет"))

        if SOUND_AVAILABLE:
            results.append(("Звук", True, "доступен"))
        else:
            results.append(("Звук", False, "winsound нет"))

        try:
            save_config(load_config())
            results.append(("Конфиг", True, CONFIG_FILE))
        except Exception as e:
            results.append(("Конфиг", False, str(e)))

        if os.path.exists(LOG_FILE):
            size_kb = max(1, os.path.getsize(LOG_FILE) // 1024)
            results.append(("Лог-файл", True, f"{size_kb} КБ"))
        else:
            results.append(("Лог-файл", False, "не создан"))

        try:
            g = find_game_window()
            if g:
                results.append(("Поиск игры", True,
                                f"{g['process']} (PID {g['pid']})"))
            else:
                results.append(("Поиск игры", None, "игра не запущена"))
        except Exception as e:
            results.append(("Поиск игры", False, str(e)))

        mons = enumerate_monitors()
        results.append(("Мониторы", True, f"найдено: {len(mons)}"))

        try:
            st = self._stats_cache
            results.append(("Статистика", True,
                            f"сегодня: {st['today']}, всего: {st['total']}"))
        except Exception as e:
            results.append(("Статистика", False, str(e)))

        results.append(("Интервал", True, f"{self.interval_minutes} мин"))

        return results

    # ---------- таймер ----------
    def _update_countdown(self):
        if self.auto_enabled and self.next_auto_time > 0:
            rem = max(0, int(self.next_auto_time - time.time()))
            mm, ss = divmod(rem, 60)
            txt = f"{mm:02d}:{ss:02d}"
            if rem < 30:
                color = C["red"]; ocolor = OVERLAY_ALERT
            elif rem < 120:
                color = C["orange"]; ocolor = OVERLAY_WARN
            else:
                color = C["accent_glow"]; ocolor = OVERLAY_TEXT
            self.overlay.set_time(txt, ocolor)
            if not self._resizing and self._last_countdown_text != txt:
                self._last_countdown_text = txt
                self.countdown_label.configure(text=txt, text_color=color)
        else:
            self.overlay.set_time("—:—", OVERLAY_TEXT)
            if not self._resizing and self._last_countdown_text != "—:—":
                self._last_countdown_text = "—:—"
                self.countdown_label.configure(text="—:—", text_color=C["text3"])
        self.root.after(COUNTDOWN_REFRESH_MS, self._update_countdown)

    # ---------- игра ----------
    def set_game_status(self, game):
        def _u():
            if game:
                self.dot.configure(text_color=C["green"])
                self.game_status_var.set(
                    game["process"].replace(".exe", "").upper())
                self.game_detail_var.set(
                    f"{game['title']}  •  PID {game['pid']}")
                self.game_card.configure(
                    fg_color=C["card"], border_color=C["green"])
                if self.config.get("overlay_auto_hide", True) and self.overlay.enabled:
                    self.overlay.show()
            else:
                self.dot.configure(text_color=C["text3"])
                self.game_status_var.set("Игра не найдена")
                self.game_detail_var.set("Ожидание GTA5.exe / Majestic.exe")
                self.game_card.configure(
                    fg_color=C["card"], border_color=C["border_soft"])
                if self.config.get("overlay_auto_hide", True):
                    self.overlay.hide()
        self.run_on_main(_u)

    def start_game_watcher(self):
        def loop():
            prev = None
            while True:
                g = find_game_window()
                pid = g["pid"] if g else None
                if pid != prev:
                    self.detected_game = g
                    self.set_game_status(g)
                    if g:
                        if AUTO_START_ON_GAME and not self.auto_enabled:
                            self.run_on_main(self.toggle_auto, True)
                    prev = pid
                time.sleep(GAME_SCAN_INTERVAL)
        threading.Thread(target=loop, daemon=True).start()

    # ---------- снимок ----------
    def _hidden_shot(self, prefix, only_if_game=False, manual=False):
        was_vis = self.root.state() != "withdrawn"
        overlay_was_vis = self.overlay.visible

        if was_vis:
            self.root.withdraw()
            self.root.update_idletasks()
        if overlay_was_vis:
            self.overlay.hide()
            self.root.update_idletasks()

        time.sleep(POST_HIDE_DELAY)

        try:
            return take_screenshot(
                prefix, only_if_game=only_if_game, manual=manual,
                monitor_index=self.monitor_index,
                copy_clipboard=self.config.get("copy_to_clipboard", True))
        finally:
            if was_vis: self.root.deiconify()
            if overlay_was_vis: self.overlay.show()

    def _after_shot(self, path):
        if not path:
            self.set_status("❌ Снимок не сделан")
            return
        self.last_screenshot_path = path
        self._preview_src_path = None
        filename = os.path.basename(path)

        if self.config.get("play_sound", True):
            threading.Thread(target=play_shutter_sound, daemon=True).start()

        if self.config.get("flash_effect", True):
            try:
                self.flash.fire()
            except Exception:
                logging.exception("flash")

        if self.config.get("show_toast", True):
            def on_click():
                try:
                    open_folder_in_explorer(os.path.dirname(path))
                except Exception:
                    pass
            self.toast.show("Скриншот сохранён",
                            filename, on_click=on_click)

        self.set_status(f"✅ {filename}")
        self._update_preview()

    def manual_shot(self):
        try:
            p = self.run_on_main(self._hidden_shot, "manual", False, True)
            self._after_shot(p)
        except Exception as e:
            logging.exception("manual_shot")
            messagebox.showerror("Ошибка", str(e))

    def on_hotkey(self):
        try:
            p = self.run_on_main(self._hidden_shot, "manual", False, True)
            self._after_shot(p)
        except Exception:
            logging.exception("hotkey")

    def copy_last_screenshot(self):
        path = self.last_screenshot_path or self._preview_src_path
        if not path or not os.path.isfile(path):
            try:
                paths = list_today_screenshots()
                if not paths:
                    self.set_status("❌ Нет скриншотов за сегодня")
                    return
                path = paths[0]
            except Exception:
                logging.exception("copy_last find")
                self.set_status("❌ Не удалось найти последний снимок")
                return

        try:
            img = Image.open(path)
            if copy_image_to_clipboard(img):
                self.set_status(f"📋 {os.path.basename(path)} в буфере")
                if self.config.get("show_toast", True):
                    self.toast.show("Скопировано в буфер",
                                    os.path.basename(path))
            else:
                self.set_status("❌ Буфер обмена недоступен")
        except Exception:
            logging.exception("copy_last")
            self.set_status("❌ Не удалось открыть файл")

    # ---------- хоткей ----------
    def setup_hotkey(self):
        if self.hotkey_handle is not None:
            try:
                keyboard.remove_hotkey(self.hotkey_handle)
            except Exception:
                logging.exception("remove old hotkey")
            self.hotkey_handle = None

        if not self.hotkey:
            self.set_status("⌨️ Хоткей не задан")
            return

        try:
            self.hotkey_handle = keyboard.add_hotkey(self.hotkey, self.on_hotkey)
            self.set_status(f"✅ Хоткей: {self.hotkey.upper()}")
        except Exception as e:
            logging.exception("hotkey setup")
            self.set_status(f"❌ Хоткей '{self.hotkey}' не зарегистрирован")

    def start_capture_hotkey(self):
        if self._capturing:
            return
        self._capturing = True
        self.hotkey_btn.configure(
            text="Нажмите…",
            fg_color=C["accent_glow"], hover_color=C["accent_glow"])
        self.hotkey_label_var.set("…")
        self.set_status("⌨️ Нажмите клавишу (Esc — отмена)")
        threading.Thread(target=self._capture_hotkey_worker, daemon=True).start()

    def _capture_hotkey_worker(self):
        try:
            time.sleep(0.25)
            hotkey = keyboard.read_hotkey(suppress=False)
            hotkey = (hotkey or "").strip().lower()
            if hotkey in ("", "esc", "escape"):
                self.run_on_main(self._cancel_capture)
                return
            self.run_on_main(self._apply_new_hotkey, hotkey)
        except Exception:
            logging.exception("capture hotkey worker")
            self.run_on_main(self._cancel_capture)

    def _apply_new_hotkey(self, hotkey: str):
        self._capturing = False
        self.hotkey = hotkey
        self.config["hotkey"] = hotkey
        save_config(self.config)
        self.hotkey_label_var.set(hotkey.upper())
        self.hotkey_btn.configure(
            text="Изменить",
            fg_color=C["accent"], hover_color=C["accent_h"])
        self.setup_hotkey()

    def _cancel_capture(self):
        self._capturing = False
        self.hotkey_label_var.set(
            self.hotkey.upper() if self.hotkey else "—")
        self.hotkey_btn.configure(
            text="Изменить",
            fg_color=C["accent"], hover_color=C["accent_h"])
        self.set_status("⌨️ Отменено")

    # ---------- авто ----------
    def toggle_auto(self, force=None):
        new = (not self.auto_enabled) if force is None else force
        if new == self.auto_enabled: return
        self.auto_enabled = new
        if self.auto_enabled:
            self.auto_btn.configure(
                text="⏸  СТОП",
                fg_color=C["red"], hover_color=C["red_h"])
            self.timer_hint.configure(text=self._timer_hint_text())
            self.next_auto_time = time.time() + self.interval_minutes * 60
            logging.info("Авто ВКЛ (интервал %d мин)", self.interval_minutes)
            threading.Thread(target=self._auto_loop, daemon=True).start()
        else:
            self.auto_btn.configure(
                text="▶  Авто",
                fg_color=C["green"], hover_color=C["green_h"])
            self.timer_hint.configure(text="Авто-режим выключен")
            self.next_auto_time = 0.0

    def _auto_loop(self):
        while self.auto_enabled:
            while self.auto_enabled and time.time() < self.next_auto_time:
                time.sleep(0.3)
            if not self.auto_enabled: return
            try:
                p = self.run_on_main(self._hidden_shot, "auto",
                                     AUTO_ONLY_IF_GAME, False)
                self._after_shot(p)
            except Exception:
                logging.exception("auto")
            self.next_auto_time = time.time() + self.interval_minutes * 60

    # ---------- оверлей ----------
    def toggle_overlay(self):
        new_state = not self.overlay.enabled
        self.overlay.set_enabled(new_state)
        if new_state:
            self.overlay.show()
            self.overlay_btn.configure(text="📺  Оверлей: ВКЛ")
        else:
            self.overlay_btn.configure(text="📺  Оверлей: ВЫКЛ")

    # ---------- очистка ----------
    def cleanup_async(self, show_result=True):
        def worker():
            st = cleanup_old_folders(RETAIN_DAYS)
            msg = (f"Удалено: {len(st['deleted'])}  •  "
                   f"пропущено: {len(st['skipped'])}  •  "
                   f"ошибок: {len(st['errors'])}")
            if not st["deleted"] and not st["errors"]:
                msg = f"Старых папок (>{RETAIN_DAYS} дней) нет"
            self.set_status(msg)
            if show_result:
                self.run_on_main(messagebox.showinfo, "Очистка", msg)
        threading.Thread(target=worker, daemon=True).start()

    def cleanup_now(self): self.cleanup_async(show_result=True)

    def start_daily_cleanup(self):
        def loop():
            while True:
                time.sleep(24 * 60 * 60)
                self.cleanup_async(show_result=False)
        threading.Thread(target=loop, daemon=True).start()

    # ---------- папки ----------
    def open_today_folder(self):
        open_folder_in_explorer(get_day_folder())

    def open_logs_folder(self):
        open_folder_in_explorer(LOG_DIR)

    # ---------- трей ----------
    def start_tray(self):
        try: img = Image.open(ensure_icon(C["accent"]))
        except Exception: img = Image.new("RGB", (64, 64), C["accent"])

        # Подменю "Открыть"
        open_menu = pystray.Menu(
            Item("Папка со снимками", self._tray_open),
            Item("Логи",              self._tray_logs),
            Item("Галерея",           self._tray_gallery),
        )

        # Подменю "Ещё"
        more_menu = pystray.Menu(
            Item("Копировать последний", self._tray_copy_last),
            pystray.Menu.SEPARATOR,
            Item("Очистить старые снимки", self._tray_cleanup),
            pystray.Menu.SEPARATOR,
            Item("О программе",          self._tray_about),
        )

        menu = pystray.Menu(
            # "Показать окно" — первым и действием по умолчанию (двойной клик)
            Item("Показать окно",  self._tray_show, default=True),
            Item("Сделать скриншот", self._tray_shot),
            pystray.Menu.SEPARATOR,
            Item(
                "Авто-снимки",
                self._tray_toggle_auto,
                checked=lambda item: self.auto_enabled,
                radio=False,
            ),
            Item(
                "Показывать оверлей",
                self._tray_overlay,
                checked=lambda item: self.overlay.enabled,
                radio=False,
            ),
            pystray.Menu.SEPARATOR,
            Item("Открыть", open_menu),
            Item("Ещё",     more_menu),
            pystray.Menu.SEPARATOR,
            Item("Выход",   self._tray_quit),
        )
        self.icon = pystray.Icon("screenshoter", img,
                                 "Game Screenshoter", menu=menu)
        threading.Thread(target=self.icon.run, daemon=True).start()

    def _tray_shot(self, icon, item):
        try:
            p = self.run_on_main(self._hidden_shot, "manual", False, True)
            self._after_shot(p)
        except Exception: logging.exception("tray shot")
        
    def _tray_toggle_auto(self, icon, item):
        """Переключает авто-режим из трея."""
        try:
            self.action_queue.put(lambda: self.toggle_auto())
        except Exception:
            logging.exception("tray toggle auto")

    def _tray_about(self, icon, item):
        """Показывает диалог 'О программе'."""
        def _show():
            try:
                text = (
                    f"Game Screenshoter  v{APP_VERSION}\n\n"
                    "Автоматический захват игрового экрана\n"
                    "для GTA 5 / Majestic RP\n\n"
                    f"Скриншоты:  {BASE_DIR}\n"
                    f"Логи:       {LOG_DIR}\n\n"
                    f"Хоткей:     {self.hotkey.upper()}\n"
                    f"Интервал:   {self.interval_minutes} мин\n"
                    f"Всего снимков: {self._stats_cache.get('total', 0)}"
                )
                messagebox.showinfo("О программе", text)
            except Exception:
                logging.exception("about dialog")
        self.action_queue.put(_show)

    def _tray_gallery(self, icon, item):
        self.action_queue.put(self.open_gallery)

    def _tray_copy_last(self, icon, item):
        try:
            self.run_on_main(self.copy_last_screenshot)
        except Exception:
            logging.exception("tray copy last")

    def _tray_overlay(self, icon, item):
        self.action_queue.put(self.toggle_overlay)

    def _tray_open(self, icon, item):
        open_folder_in_explorer(get_day_folder())

    def _tray_logs(self, icon, item):
        open_folder_in_explorer(LOG_DIR)

    def _tray_cleanup(self, icon, item):
        self.cleanup_async(show_result=False)

    def _tray_show(self, icon, item):
        self.action_queue.put(self._show_main_window)

    def _show_main_window(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()
            self.overlay.set_draggable(True)
        except Exception:
            logging.exception("_show_main_window")

    def _tray_quit(self, icon, item):
        try:
            self._resizing = False
            self._save_current_geometry()
        except Exception:
            logging.exception("save geometry on quit")
        try:
            if self.icon: self.icon.stop()
        except Exception: pass
        try: keyboard.unhook_all_hotkeys()
        except Exception: pass
        self.auto_enabled = False
        self.overlay.hide()
        self.action_queue.put(self.root.destroy)

    def hide_to_tray(self):
        self.root.withdraw()
        self.set_status("Свёрнуто в трей")
        self.overlay.set_draggable(False)

    def quit_app(self):
        self._tray_quit(self.icon, None)


if __name__ == "__main__":
    if not WIN32_AVAILABLE:
        logging.warning("pywin32 недоступен")
    ensure_icon()
    root = ctk.CTk()
    app = ScreenshotApp(root)
    root.mainloop()