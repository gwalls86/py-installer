#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
===============================================================================
  PyInstaller GUI — CustomTkinter edition
===============================================================================
  Requisitos:
    pip install customtkinter pyinstaller
===============================================================================
"""

from __future__ import annotations

import json
import os
import queue
import shlex
import subprocess
import sys
import threading
import traceback
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, List, Optional, Tuple

import tkinter as tk
from tkinter import filedialog, messagebox

try:
    import customtkinter as ctk
except ImportError:
    print("Instalando customtkinter...")
    subprocess.run([sys.executable, "-m", "pip", "install", "customtkinter"],
                   check=True)
    import customtkinter as ctk

# ─── TEMA ─────────────────────────────────────────────────────────────────────

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

C = {
    "bg":        "#1e1e2e",
    "bg_card":   "#24273a",
    "bg_input":  "#2d2d3f",
    "bg_hover":  "#363850",
    "accent":    "#89b4fa",
    "accent2":   "#b4befe",
    "success":   "#a6e3a1",
    "warning":   "#f9e2af",
    "error":     "#f38ba8",
    "info":      "#94e2d5",
    "fg":        "#cdd6f4",
    "fg_dim":    "#9399b2",
    "fg_muted":  "#6c7086",
    "border":    "#45475a",
}

APP_TITLE   = "PyInstaller GUI"


def _get_python_exe() -> str:
    """
    Devuelve la ruta al intérprete Python real.
    Cuando corremos como .exe frozen, sys.executable apunta al .exe,
    no a python.exe — hay que buscarlo en el PATH del sistema.
    """
    if not getattr(sys, "frozen", False):
        return sys.executable  # En desarrollo, sys.executable es python.exe

    # En .exe frozen: buscar python.exe en el PATH
    import shutil
    for candidate in ("python", "python3", "python.exe", "python3.exe"):
        found = shutil.which(candidate)
        if found and "pyinstaller_gui" not in found.lower():
            return found

    # Fallback: buscar en rutas comunes de Windows
    import winreg
    try:
        for key_path in (
            r"SOFTWARE\Python\PythonCore",
            r"SOFTWARE\WOW6432Node\Python\PythonCore",
        ):
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                versions = []
                i = 0
                while True:
                    try:
                        versions.append(winreg.EnumKey(key, i))
                        i += 1
                    except OSError:
                        break
                for ver in sorted(versions, reverse=True):
                    try:
                        with winreg.OpenKey(key, ver + r"\InstallPath") as ikey:
                            install_path = winreg.QueryValue(ikey, None)
                            python_exe = Path(install_path) / "python.exe"
                            if python_exe.exists():
                                return str(python_exe)
                    except OSError:
                        continue
    except Exception:
        pass

    raise RuntimeError(
        "No se encontró Python en el sistema.\n\n"
        "Asegúrate de que Python esté instalado y en el PATH.\n"
        "Descárgalo en: https://www.python.org/downloads/"
    )


def _get_resource_path(filename: str) -> Path:
    """
    Devuelve la ruta correcta a un recurso tanto en desarrollo como en .exe.
    - En .exe (frozen): los recursos están en sys._MEIPASS (carpeta temporal)
    - En desarrollo: junto al script
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS) / filename
    try:
        return Path(__file__).parent / filename
    except NameError:
        return Path.cwd() / filename
APP_VERSION = "1.1"
CONFIG_FILE = "pyinstaller_gui_config.json"

SUBPROCESS_FLAGS = 0x08000000 if sys.platform == "win32" else 0


# ─── CONFIG ───────────────────────────────────────────────────────────────────

@dataclass
class BuildConfig:
    script_path:    str = ""
    output_dir:     str = ""
    name:           str = ""
    icon_path:      str = ""
    onefile:        bool = True
    windowed:       bool = True
    clean:          bool = True
    strip:          bool = False
    upx:            bool = False
    hidden_imports: List[str] = field(default_factory=list)
    add_data:       List[str] = field(default_factory=list)
    extra_args:     str = ""

    def to_dict(self):  return asdict(self)

    @classmethod
    def from_dict(cls, d):
        return cls(**{k: v for k, v in d.items() if k in cls.__annotations__})

    def save(self, p: Path):
        p.write_text(json.dumps(self.to_dict(), indent=2, ensure_ascii=False),
                     encoding="utf-8")

    @classmethod
    def load(cls, p: Path):
        if not p.exists(): return cls()
        try: return cls.from_dict(json.loads(p.read_text(encoding="utf-8")))
        except Exception: return cls()

    def build_args(self) -> List[str]:
        args = ["--onefile" if self.onefile else "--onedir"]
        if self.windowed:  args.append("--windowed")
        if self.clean:     args.append("--clean")
        if self.strip:     args.append("--strip")
        if not self.upx:   args.append("--noupx")
        args += ["--name", self.name.strip() or Path(self.script_path).stem]
        # Todos los artefactos van junto al script a compilar, no junto al .exe
        if self.script_path.strip():
            script_dir = str(Path(self.script_path).parent)
            # dist/ — ejecutable final
            if self.output_dir.strip():
                args += ["--distpath", self.output_dir.strip()]
            else:
                args += ["--distpath", str(Path(self.script_path).parent / "dist")]
            # build/ — archivos temporales de compilación
            args += ["--workpath", str(Path(self.script_path).parent / "build")]
            # .spec — archivo de especificación de PyInstaller
            args += ["--specpath", script_dir]
        elif self.output_dir.strip():
            args += ["--distpath", self.output_dir.strip()]
        if self.icon_path.strip():
            ico = self.icon_path.strip().replace("/", "\\")
            args += ["--icon", ico]
            # Empaquetar el .ico dentro del .exe para cargarlo en runtime
            # Formato Windows: "src;dst_folder"  Linux/Mac: "src:dst_folder"
            sep = ";" if sys.platform == "win32" else ":"
            args += ["--add-data", f"{ico}{sep}."]
        for hi in self.hidden_imports:
            if hi.strip(): args += ["--hidden-import", hi.strip()]
        for ad in self.add_data:
            if ad.strip(): args += ["--add-data", ad.strip()]
        if self.extra_args.strip():
            args += shlex.split(self.extra_args.strip())
        args.append(self.script_path)
        return args


# ─── BRIDGE ───────────────────────────────────────────────────────────────────

class CancelToken:
    def __init__(self):
        self._ev  = threading.Event()
        self.proc: Optional[subprocess.Popen] = None

    def cancel(self):
        self._ev.set()
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate(); self.proc.wait(timeout=3)
            except Exception:
                try: self.proc.kill()
                except Exception: pass

    def is_set(self): return self._ev.is_set()


class Bridge:
    def __init__(self):
        self.q      = queue.Queue()
        self.cancel = CancelToken()

    def log(self, msg: str, level: str = "INFO"):
        self.q.put(("log", (msg, level)))

    def done(self, ok: bool, msg: str = ""):
        self.q.put(("done", (ok, msg)))

    def drain(self) -> List[Tuple[str, Any]]:
        out = []
        while True:
            try: out.append(self.q.get_nowait())
            except queue.Empty: break
        return out


# ─── WIDGETS ──────────────────────────────────────────────────────────────────

class Card(ctk.CTkFrame):
    """Tarjeta con fondo ligeramente elevado y esquinas redondeadas."""
    def __init__(self, parent, **kw):
        super().__init__(parent,
                         fg_color=C["bg_card"],
                         corner_radius=12,
                         border_width=1,
                         border_color=C["border"],
                         **kw)


class SectionLabel(ctk.CTkLabel):
    def __init__(self, parent, text: str, **kw):
        super().__init__(parent,
                         text=text,
                         font=ctk.CTkFont("Segoe UI", 11, "bold"),
                         text_color=C["accent"],
                         **kw)


class HintLabel(ctk.CTkLabel):
    def __init__(self, parent, text: str, **kw):
        kw.setdefault("font", ctk.CTkFont("Segoe UI", 10))
        kw.setdefault("text_color", C["fg_muted"])
        super().__init__(parent, text=text, **kw)


class PathField(ctk.CTkFrame):
    def __init__(self, parent, label: str, var: ctk.StringVar,
                 mode: str = "file", filetypes=None, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.var   = var
        self.mode  = mode
        self.types = filetypes or [("Todos", "*.*")]

        self.columnconfigure(1, weight=1)

        ctk.CTkLabel(self, text=label,
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["fg_dim"],
                     width=130, anchor="w").grid(row=0, column=0,
                                                  sticky="w", padx=(0, 8))
        ctk.CTkEntry(self, textvariable=var,
                     fg_color=C["bg_input"],
                     border_color=C["border"],
                     text_color=C["fg"],
                     font=ctk.CTkFont("Segoe UI", 11)).grid(
            row=0, column=1, sticky="ew")
        ctk.CTkButton(self, text="Examinar",
                      width=90, height=32,
                      fg_color=C["bg_hover"],
                      hover_color=C["border"],
                      text_color=C["fg"],
                      font=ctk.CTkFont("Segoe UI", 11),
                      command=self._browse).grid(
            row=0, column=2, padx=(8, 0))

    def _browse(self):
        if self.mode == "file":
            p = filedialog.askopenfilename(filetypes=self.types)
        elif self.mode == "save_file":
            p = filedialog.asksaveasfilename(filetypes=self.types)
        else:
            p = filedialog.askdirectory()
        if p: self.var.set(p)


class TogglePill(ctk.CTkFrame):
    """Checkbutton con apariencia de pill/tag."""
    def __init__(self, parent, text: str, var: ctk.BooleanVar, **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.var = var
        self.text = text
        self._btn = ctk.CTkButton(
            self,
            text=text,
            width=120, height=30,
            corner_radius=15,
            font=ctk.CTkFont("Segoe UI", 11),
            command=self._toggle,
        )
        self._btn.pack()
        self._refresh()
        var.trace_add("write", lambda *_: self._refresh())

    def _toggle(self):
        self.var.set(not self.var.get())

    def _refresh(self):
        if self.var.get():
            self._btn.configure(fg_color=C["accent"],
                                hover_color=C["accent2"],
                                text_color=C["bg"])
        else:
            self._btn.configure(fg_color=C["bg_hover"],
                                hover_color=C["border"],
                                text_color=C["fg_muted"])


class EditableList(ctk.CTkFrame):
    def __init__(self, parent, placeholder: str = "", **kw):
        super().__init__(parent, fg_color="transparent", **kw)
        self.placeholder = placeholder
        self.columnconfigure(0, weight=1)

        self.listbox = tk.Listbox(
            self,
            background=C["bg_input"],
            foreground=C["fg"],
            selectbackground=C["accent"],
            selectforeground=C["bg"],
            relief="flat", borderwidth=0,
            height=3,
            font=("Consolas", 10),
            highlightthickness=0,
        )
        self.listbox.grid(row=0, column=0, sticky="ew", pady=(0, 6))

        row2 = ctk.CTkFrame(self, fg_color="transparent")
        row2.grid(row=1, column=0, sticky="ew")
        row2.columnconfigure(0, weight=1)

        self.entry_var = ctk.StringVar()
        ctk.CTkEntry(row2, textvariable=self.entry_var,
                     placeholder_text=placeholder,
                     fg_color=C["bg_input"],
                     border_color=C["border"],
                     text_color=C["fg"],
                     font=ctk.CTkFont("Consolas", 10)).grid(
            row=0, column=0, sticky="ew", padx=(0, 8))

        btn_f = ctk.CTkFrame(row2, fg_color="transparent")
        btn_f.grid(row=0, column=1)
        ctk.CTkButton(btn_f, text="+ Agregar", width=90, height=28,
                      fg_color=C["accent"], hover_color=C["accent2"],
                      text_color=C["bg"],
                      font=ctk.CTkFont("Segoe UI", 10),
                      command=self._add).pack(side="left")
        ctk.CTkButton(btn_f, text="✕ Quitar", width=80, height=28,
                      fg_color=C["bg_hover"], hover_color=C["error"],
                      text_color=C["fg"],
                      font=ctk.CTkFont("Segoe UI", 10),
                      command=self._remove).pack(side="left", padx=(6, 0))

    def _add(self):
        v = self.entry_var.get().strip()
        if v: self.listbox.insert("end", v); self.entry_var.set("")

    def _remove(self):
        s = self.listbox.curselection()
        if s: self.listbox.delete(s[0])

    def get_items(self): return list(self.listbox.get(0, "end"))

    def set_items(self, items):
        self.listbox.delete(0, "end")
        for i in items: self.listbox.insert("end", i)


class LogView(ctk.CTkFrame):
    COLORS = {
        "INFO":    C["fg"],
        "SUCCESS": C["success"],
        "WARNING": C["warning"],
        "ERROR":   C["error"],
        "DIM":     C["fg_muted"],
        "CMD":     C["info"],
    }

    def __init__(self, parent, **kw):
        super().__init__(parent, fg_color=C["bg_card"],
                         corner_radius=10,
                         border_width=1,
                         border_color=C["border"], **kw)
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self.text = tk.Text(
            self,
            state="disabled",
            background=C["bg_card"],
            foreground=C["fg"],
            font=("Consolas", 9),
            relief="flat", borderwidth=0,
            wrap="word",
            insertbackground=C["fg"],
            padx=10, pady=8,
        )
        sb = ctk.CTkScrollbar(self, command=self.text.yview)
        self.text.configure(yscrollcommand=sb.set)
        self.text.grid(row=0, column=0, sticky="nsew", padx=(2, 0), pady=2)
        sb.grid(row=0, column=1, sticky="ns", pady=2, padx=(0, 2))

        for tag, color in self.COLORS.items():
            self.text.tag_configure(tag, foreground=color)

    def append(self, msg: str, level: str = "INFO"):
        self.text.configure(state="normal")
        self.text.insert("end", msg + "\n", level)
        self.text.see("end")
        self.text.configure(state="disabled")

    def clear(self):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.configure(state="disabled")


# ─── MENSAJES DE ERROR ────────────────────────────────────────────────────────

_PERMISSION_ERROR_MSG = (
    "Error de permisos al eliminar la carpeta build.\n\n"
    "Ruta bloqueada:\n"
    "  {path}\n\n"
    "Causa más probable:\n"
    "  Un proceso externo tiene bloqueado uno o más archivos en la carpeta\n"
    "  build (sincronizador de nube, antivirus, o una instancia anterior\n"
    "  del ejecutable aún en ejecución).\n\n"
    "Soluciones:\n"
    "  1. Si usas Google Drive, OneDrive o Dropbox: pausa la sincronización\n"
    "     y vuelve a compilar.\n"
    "  2. Cierra cualquier instancia del ejecutable anterior que esté corriendo.\n"
    "  3. Desactiva temporalmente el antivirus en tiempo real y reintenta.\n"
    "  4. Borra manualmente la carpeta 'build' junto al script y reintenta.\n"
    "  5. Ejecuta la aplicación como Administrador."
)


# ─── DIÁLOGO ERROR DE PERMISOS ───────────────────────────────────────────────

class PermissionErrorDialog(ctk.CTkToplevel):
    """
    Diálogo modal para PermissionError WinError 5.
    Ofrece tres acciones: Forzar borrado + reintentar, Solo reintentar, Cerrar.
    result: "force" | "retry" | "close"
    """
    def __init__(self, parent, message: str, build_path: str):
        super().__init__(parent)
        self.result     = "close"
        self.build_path = build_path

        self.title("Error de permisos")
        self.resizable(False, False)
        self.configure(fg_color=C["bg"])
        self.grab_set()  # modal

        # ── Ícono + título ──
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.pack(fill="x", padx=20, pady=(20, 0))
        ctk.CTkLabel(hdr, text="⛔", font=ctk.CTkFont("Segoe UI", 28),
                     text_color=C["error"]).pack(side="left", padx=(0, 10))
        ctk.CTkLabel(hdr, text="Error de permisos al limpiar build",
                     font=ctk.CTkFont("Segoe UI", 13, "bold"),
                     text_color=C["error"]).pack(side="left")

        # ── Mensaje ──
        ctk.CTkTextbox(self, width=520, height=230,
                       fg_color=C["bg_input"], text_color=C["fg"],
                       font=ctk.CTkFont("Consolas", 11),
                       wrap="word", state="normal").pack(padx=20, pady=12)
        # Insertar texto (necesitamos la referencia)
        self._tb = self.winfo_children()[-1]
        self._tb.insert("0.0", message)
        self._tb.configure(state="disabled")

        # ── Botones ──
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(fill="x", padx=20, pady=(0, 20))

        ctk.CTkButton(btn_frame,
                      text="🗑 Forzar borrado y reintentar",
                      fg_color=C["error"], hover_color="#c0566e",
                      text_color="#ffffff",
                      font=ctk.CTkFont("Segoe UI", 12, "bold"),
                      command=self._force).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame,
                      text="↺ Solo reintentar",
                      fg_color=C["bg_hover"],
                      text_color=C["fg"],
                      font=ctk.CTkFont("Segoe UI", 12),
                      command=self._retry).pack(side="left", padx=(0, 8))

        ctk.CTkButton(btn_frame,
                      text="Cerrar",
                      fg_color=C["bg_card"],
                      text_color=C["fg_dim"],
                      font=ctk.CTkFont("Segoe UI", 12),
                      command=self._close).pack(side="right")

        # Centrar sobre la ventana padre
        self.update_idletasks()
        px = parent.winfo_x() + (parent.winfo_width()  - self.winfo_width())  // 2
        py = parent.winfo_y() + (parent.winfo_height() - self.winfo_height()) // 2
        self.geometry(f"+{px}+{py}")
        self.wait_window()

    def _force(self):
        self.result = "force"
        self.destroy()

    def _retry(self):
        self.result = "retry"
        self.destroy()

    def _close(self):
        self.result = "close"
        self.destroy()


# ─── APP PRINCIPAL ────────────────────────────────────────────────────────────

class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE}  v{APP_VERSION}")
        self.geometry("860x820")
        self.minsize(720, 640)
        self.configure(fg_color=C["bg"])

        # Iniciar maximizado
        self.after(0, lambda: self.state("zoomed"))

        # Ícono de la ventana — se aplica después de que CTk termine de renderizar
        def _apply_icon():
            _ico = _get_resource_path("icon.ico")
            if _ico.exists():
                try:
                    self.iconbitmap(str(_ico).replace("/", "\\"))
                except Exception:
                    pass
        self.after(200, _apply_icon)

        self.config_path = Path(__file__).parent / CONFIG_FILE
        self.cfg         = BuildConfig.load(self.config_path)
        self.bridge: Optional[Bridge] = None
        self.worker: Optional[threading.Thread] = None

        self._build_ui()
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── Layout ───────────────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=1)

        # Header
        hdr = ctk.CTkFrame(self, fg_color="transparent")
        hdr.grid(row=0, column=0, sticky="ew", padx=24, pady=(18, 0))
        hdr.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(hdr, text="PyInstaller GUI",
                     font=ctk.CTkFont("Segoe UI", 20, "bold"),
                     text_color=C["accent"]).grid(row=0, column=0, sticky="w")
        ctk.CTkLabel(hdr,
                     text="Empaqueta scripts Python en ejecutables .exe",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["fg_muted"]).grid(row=1, column=0, sticky="w",
                                                     pady=(1, 0))
        sep = ctk.CTkFrame(self, height=1, fg_color=C["border"])
        sep.grid(row=0, column=0, sticky="sew", padx=0, pady=(56, 0))

        # Body: dos paneles
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.grid(row=1, column=0, sticky="nsew", padx=0, pady=0)
        body.grid_columnconfigure(0, weight=2, minsize=380)
        body.grid_columnconfigure(1, weight=3)
        body.grid_rowconfigure(0, weight=1)

        # Panel izquierdo — configuracion scrollable
        left = ctk.CTkScrollableFrame(body,
                                       fg_color="transparent",
                                       scrollbar_button_color=C["border"],
                                       scrollbar_button_hover_color=C["bg_hover"])
        left.grid(row=0, column=0, sticky="nsew", padx=(16, 6), pady=(10, 0))
        left.grid_columnconfigure(0, weight=1)
        self._populate(left)

        # Panel derecho — log
        right = ctk.CTkFrame(body, fg_color="transparent")
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 16), pady=(10, 0))
        right.grid_columnconfigure(0, weight=1)
        right.grid_rowconfigure(1, weight=1)

        ctk.CTkLabel(right,
                     text="Output de compilacion",
                     font=ctk.CTkFont("Segoe UI", 11, "bold"),
                     text_color=C["accent"]).grid(
            row=0, column=0, sticky="w", padx=2, pady=(2, 6))

        self.log_view = LogView(right)
        self.log_view.grid(row=1, column=0, sticky="nsew")
        self.log_view.append(f"{APP_TITLE} v{APP_VERSION} — listo.", "SUCCESS")
        self.log_view.append("Configura el script y pulsa Compilar.", "DIM")

        # Toolbar fija abajo
        self._build_toolbar()

    def _populate(self, p):
        # ── Script ────────────────────────────────────────────────────────
        c1 = Card(p)
        c1.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        c1.grid_columnconfigure(0, weight=1)

        SectionLabel(c1, "📄  Script Python").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        self.var_script = ctk.StringVar(value=self.cfg.script_path)
        PathField(c1, "Script (.py):", self.var_script,
                  filetypes=[("Python", "*.py"), ("Todos", "*.*")]).grid(
            row=1, column=0, sticky="ew", padx=16, pady=4)

        nf = ctk.CTkFrame(c1, fg_color="transparent")
        nf.grid(row=2, column=0, sticky="ew", padx=16, pady=(4, 12))
        nf.grid_columnconfigure(1, weight=1)
        ctk.CTkLabel(nf, text="Nombre del .exe:",
                     font=ctk.CTkFont("Segoe UI", 11),
                     text_color=C["fg_dim"],
                     width=130, anchor="w").grid(row=0, column=0, sticky="w",
                                                  padx=(0, 8))
        self.var_name = ctk.StringVar(value=self.cfg.name)
        ctk.CTkEntry(nf, textvariable=self.var_name,
                     placeholder_text="vacío = nombre del script",
                     fg_color=C["bg_input"],
                     border_color=C["border"],
                     text_color=C["fg"],
                     font=ctk.CTkFont("Segoe UI", 11)).grid(
            row=0, column=1, sticky="ew")

        # ── Salida + Ícono ────────────────────────────────────────────────
        c2 = Card(p)
        c2.grid(row=1, column=0, sticky="ew", pady=(0, 10))
        c2.grid_columnconfigure(0, weight=1)

        SectionLabel(c2, "📁  Salida  &  🎨  Ícono").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        self.var_outdir = ctk.StringVar(value=self.cfg.output_dir)
        PathField(c2, "Carpeta dist/:", self.var_outdir, mode="folder").grid(
            row=1, column=0, sticky="ew", padx=16, pady=4)

        # Ícono — acepta PNG, JPG, ICO; convierte automáticamente
        self.var_icon = ctk.StringVar(value=self.cfg.icon_path)
        self.var_icon_status = ctk.StringVar(value="")

        icon_row = ctk.CTkFrame(c2, fg_color="transparent")
        icon_row.grid(row=2, column=0, sticky="ew", padx=16, pady=4)
        icon_row.grid_columnconfigure(1, weight=1)

        ctk.CTkLabel(icon_row, text="Ícono:", width=130, anchor="w",
                      font=ctk.CTkFont("Segoe UI", 11),
                      text_color=C["fg_dim"]).grid(row=0, column=0,
                                                    sticky="w", padx=(0, 8))
        ctk.CTkEntry(icon_row, textvariable=self.var_icon,
                      fg_color=C["bg_input"], border_color=C["border"],
                      text_color=C["fg"],
                      font=ctk.CTkFont("Segoe UI", 11),
                      state="readonly").grid(row=0, column=1, sticky="ew")
        ctk.CTkButton(icon_row, text="Seleccionar",
                       width=100, height=32,
                       fg_color=C["accent"], hover_color=C["accent2"],
                       text_color=C["bg"],
                       font=ctk.CTkFont("Segoe UI", 11),
                       command=self._pick_icon).grid(row=0, column=2,
                                                      padx=(8, 0))

        self.lbl_icon_status = ctk.CTkLabel(
            c2, textvariable=self.var_icon_status,
            font=ctk.CTkFont("Segoe UI", 9),
            text_color=C["success"], anchor="w")
        self.lbl_icon_status.grid(row=3, column=0, sticky="w",
                                    padx=16, pady=(0, 4))

        HintLabel(c2,
                   "Acepta PNG, JPG, BMP, WebP o ICO — se convierte automaticamente"
        ).grid(row=4, column=0, sticky="w", padx=16, pady=(0, 12))


        c3 = Card(p)
        c3.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        c3.grid_columnconfigure(0, weight=1)

        SectionLabel(c3, "⚙️  Opciones de compilación").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 8))

        self.var_onefile  = ctk.BooleanVar(value=self.cfg.onefile)
        self.var_windowed = ctk.BooleanVar(value=self.cfg.windowed)
        self.var_clean    = ctk.BooleanVar(value=self.cfg.clean)
        self.var_strip    = ctk.BooleanVar(value=self.cfg.strip)
        self.var_upx      = ctk.BooleanVar(value=self.cfg.upx)

        pills_f = ctk.CTkFrame(c3, fg_color="transparent")
        pills_f.grid(row=1, column=0, sticky="ew", padx=16, pady=(0, 6))

        opts = [
            (self.var_onefile,  "--onefile"),
            (self.var_windowed, "--windowed"),
            (self.var_clean,    "--clean"),
            (self.var_strip,    "--strip"),
            (self.var_upx,      "UPX"),
        ]
        for i, (var, lbl) in enumerate(opts):
            TogglePill(pills_f, lbl, var).grid(
                row=0, column=i, padx=(0, 8), pady=4)

        hints = [
            "Un solo .exe",
            "Sin consola",
            "Limpiar caché",
            "Strip símbolos",
            "Comprimir UPX",
        ]
        for i, h in enumerate(hints):
            HintLabel(pills_f, h, font=ctk.CTkFont("Segoe UI", 9)).grid(
                row=1, column=i, padx=(0, 8))

        HintLabel(c3,
                  "💡  --onefile + --windowed es lo recomendado para apps de escritorio").grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 12))

        # ── Hidden imports ────────────────────────────────────────────────
        c4 = Card(p)
        c4.grid(row=3, column=0, sticky="ew", pady=(0, 10))
        c4.grid_columnconfigure(0, weight=1)

        SectionLabel(c4, "🔍  Hidden imports").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        HintLabel(c4,
                  "Módulos que PyInstaller no detecta automáticamente").grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 6))

        self.list_imports = EditableList(
            c4, placeholder="ej: PIL, cv2, sklearn.ensemble")
        self.list_imports.grid(row=2, column=0, sticky="ew",
                                padx=16, pady=(0, 12))
        self.list_imports.set_items(self.cfg.hidden_imports)

        # ── Add data ──────────────────────────────────────────────────────
        c5 = Card(p)
        c5.grid(row=4, column=0, sticky="ew", pady=(0, 10))
        c5.grid_columnconfigure(0, weight=1)

        SectionLabel(c5, "📦  Archivos adicionales  (--add-data)").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 4))
        HintLabel(c5,
                  'Windows: "origen;destino"   Linux/Mac: "origen:destino"').grid(
            row=1, column=0, sticky="w", padx=16, pady=(0, 6))

        self.list_data = EditableList(
            c5, placeholder='ej: data/config.json;data')
        self.list_data.grid(row=2, column=0, sticky="ew",
                             padx=16, pady=(0, 12))
        self.list_data.set_items(self.cfg.add_data)

        # ── Args extra ────────────────────────────────────────────────────
        c6 = Card(p)
        c6.grid(row=5, column=0, sticky="ew", pady=(0, 4))
        c6.grid_columnconfigure(0, weight=1)

        SectionLabel(c6, "🔧  Argumentos adicionales").grid(
            row=0, column=0, sticky="w", padx=16, pady=(12, 6))

        self.var_extra = ctk.StringVar(value=self.cfg.extra_args)
        ctk.CTkEntry(c6, textvariable=self.var_extra,
                     placeholder_text="ej: --debug all --log-level WARN",
                     fg_color=C["bg_input"],
                     border_color=C["border"],
                     text_color=C["fg"],
                     font=ctk.CTkFont("Consolas", 11)).grid(
            row=1, column=0, sticky="ew", padx=16, pady=(0, 8))
        HintLabel(c6, "Cualquier argumento válido de PyInstaller").grid(
            row=2, column=0, sticky="w", padx=16, pady=(0, 12))

    def _build_toolbar(self):
        bot = ctk.CTkFrame(self, fg_color=C["bg_card"],
                           corner_radius=0,
                           border_width=1,
                           border_color=C["border"])
        bot.grid(row=2, column=0, sticky="sew", padx=0, pady=0)
        bot.grid_columnconfigure(0, weight=1)

        # Controles
        ctrl = ctk.CTkFrame(bot, fg_color="transparent")
        ctrl.grid(row=0, column=0, sticky="ew", padx=20, pady=(10, 10))

        self.btn_build = ctk.CTkButton(
            ctrl, text="▶  Compilar",
            width=130, height=36,
            fg_color=C["accent"], hover_color=C["accent2"],
            text_color=C["bg"],
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            command=self._on_build,
        )
        self.btn_build.pack(side="left")

        self.btn_stop = ctk.CTkButton(
            ctrl, text="⏹  Cancelar",
            width=120, height=36,
            fg_color=C["error"], hover_color="#fab0c4",
            text_color=C["bg"],
            font=ctk.CTkFont("Segoe UI", 13, "bold"),
            state="disabled",
            command=self._on_stop,
        )
        self.btn_stop.pack(side="left", padx=(10, 0))

        ctk.CTkButton(
            ctrl, text="💾  Guardar",
            width=100, height=36,
            fg_color=C["bg_hover"], hover_color=C["border"],
            text_color=C["fg"],
            font=ctk.CTkFont("Segoe UI", 11),
            command=self._save_config,
        ).pack(side="right")

        ctk.CTkButton(
            ctrl, text="📁  dist",
            width=80, height=36,
            fg_color=C["bg_hover"], hover_color=C["border"],
            text_color=C["fg"],
            font=ctk.CTkFont("Segoe UI", 11),
            command=self._open_dist,
        ).pack(side="right", padx=(0, 8))

        ctk.CTkButton(
            ctrl, text="📋  Ver cmd",
            width=90, height=36,
            fg_color=C["bg_hover"], hover_color=C["border"],
            text_color=C["fg"],
            font=ctk.CTkFont("Segoe UI", 11),
            command=self._show_command,
        ).pack(side="right", padx=(0, 8))

        # Status
        self.var_status = ctk.StringVar(value="Listo.")
        ctk.CTkLabel(bot, textvariable=self.var_status,
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["fg_muted"],
                     anchor="w").grid(row=1, column=0, sticky="ew",
                                       padx=20, pady=(0, 6))

        # Log


    # ── Acciones ──────────────────────────────────────────────────────────────

    def _collect(self) -> BuildConfig:
        return BuildConfig(
            script_path    = self.var_script.get().strip(),
            output_dir     = self.var_outdir.get().strip(),
            name           = self.var_name.get().strip(),
            icon_path      = self.var_icon.get().strip(),
            onefile        = self.var_onefile.get(),
            windowed       = self.var_windowed.get(),
            clean          = self.var_clean.get(),
            strip          = self.var_strip.get(),
            upx            = self.var_upx.get(),
            hidden_imports = self.list_imports.get_items(),
            add_data       = self.list_data.get_items(),
            extra_args     = self.var_extra.get().strip(),
        )

    def _save_config(self):
        self.cfg = self._collect()
        self.cfg.save(self.config_path)
        self.log_view.append(f"✓ Config guardada: {self.config_path}", "SUCCESS")

    def _show_command(self):
        cfg = self._collect()
        if not cfg.script_path:
            messagebox.showwarning("Script faltante",
                                   "Selecciona un script .py primero.")
            return
        args  = cfg.build_args()
        cmd   = "pyinstaller " + " ".join(
            f'"{a}"' if " " in a else a for a in args)

        win = ctk.CTkToplevel(self)
        win.title("Comando generado")
        win.geometry("700x160")
        win.configure(fg_color=C["bg"])
        win.grab_set()

        ctk.CTkLabel(win, text="Comando que se ejecutará:",
                     font=ctk.CTkFont("Segoe UI", 10),
                     text_color=C["fg_muted"]).pack(
            anchor="w", padx=16, pady=(12, 4))

        txt = tk.Text(win, height=4,
                      background=C["bg_input"], foreground=C["info"],
                      font=("Consolas", 9), relief="flat", wrap="word",
                      padx=8, pady=6)
        txt.pack(fill="both", expand=True, padx=16, pady=(0, 8))
        txt.insert("1.0", cmd)
        txt.configure(state="disabled")

        ctk.CTkButton(win, text="Cerrar", width=80,
                      command=win.destroy,
                      fg_color=C["bg_hover"],
                      hover_color=C["border"],
                      text_color=C["fg"]).pack(pady=(0, 12))

    def _pick_icon(self) -> None:
        """
        Abre selector de imagen (PNG/JPG/ICO/etc).
        - Si es PNG/JPG/BMP/WebP: convierte a .ico con todos los tamaños.
        - Si es .ico: verifica que tenga los tamaños necesarios y lo regenera si faltan.
        Actualiza el campo automáticamente con el .ico resultante.
        """
        src = filedialog.askopenfilename(
            title="Selecciona una imagen o ícono",
            filetypes=[
                ("Imágenes e íconos", "*.png *.jpg *.jpeg *.webp *.bmp *.gif *.ico"),
                ("Todos", "*.*"),
            ]
        )
        if not src:
            return

        try:
            from PIL import Image
        except ImportError:
            messagebox.showerror(
                "Pillow no instalado",
                "Instala Pillow con:\n\npip install pillow"
            )
            return

        REQUIRED_SIZES = [16, 24, 32, 48, 64, 128, 256]
        src_path = Path(src)

        try:
            self.var_icon_status.set("⏳ Procesando imagen...")
            self.update_idletasks()

            src_ext = src_path.suffix.lower()

            if src_ext == ".ico":
                # Verificar si el .ico ya tiene todos los tamaños necesarios
                existing = Image.open(src)
                existing_sizes = set(existing.ico.sizes()) if hasattr(existing, 'ico') else set()

                required_set = {(s, s) for s in REQUIRED_SIZES}
                needs_rebuild = not required_set.issubset(existing_sizes)

                if not needs_rebuild:
                    # Ya está completo — copiar junto al script si es necesario
                    script = self.var_script.get().strip()
                    if script and Path(script).is_file():
                        ico_dst = Path(script).parent / "icon.ico"
                        if ico_dst != src_path:
                            import shutil
                            shutil.copy2(src, ico_dst)
                            self.var_icon.set(str(ico_dst))
                            self.log_view.append(f"✓ Ícono copiado junto al script: {ico_dst.name}", "SUCCESS")
                        else:
                            self.var_icon.set(src)
                            self.log_view.append(f"✓ Ícono seleccionado: {src_path.name}", "SUCCESS")
                    else:
                        self.var_icon.set(src)
                        self.log_view.append(f"✓ Ícono seleccionado: {src_path.name}", "SUCCESS")
                    self.var_icon_status.set(
                        f"✓ Ícono OK — {len(existing_sizes)} tamaños detectados"
                    )
                    self.lbl_icon_status.configure(text_color=C["success"])
                    return

                # Necesita regenerarse
                self.log_view.append(
                    f"⚠ El .ico tiene {len(existing_sizes)} tamaños — regenerando con {len(REQUIRED_SIZES)}...",
                    "WARNING"
                )
                img = existing.convert("RGBA")
            else:
                # PNG, JPG, etc — abrir y convertir
                img = Image.open(src).convert("RGBA")

            # Guardar siempre como icon.ico junto al script
            script = self.var_script.get().strip()
            if script and Path(script).is_file():
                dst = Path(script).parent / "icon.ico"
            else:
                dst = src_path.parent / "icon.ico"

            # Recortar a cuadrado centrado si la imagen no es cuadrada
            w, h = img.size
            if w != h:
                side = min(w, h)
                left = (w - side) // 2
                top  = (h - side) // 2
                img  = img.crop((left, top, left + side, top + side))

            # Escalar a 256 si es más pequeña para mejor calidad al reducir
            if max(img.size) < 256:
                img = img.resize((256, 256), Image.LANCZOS)

            # Generar cada tamaño como imagen separada
            sized_images = []
            for s in REQUIRED_SIZES:
                sized_images.append(img.resize((s, s), Image.LANCZOS))

            # ── Construir el .ico manualmente con struct ──────────────────
            # Pillow tiene un bug conocido que guarda 256px como 255px.
            # Construimos el archivo directamente para garantizar calidad total.
            import struct, io

            def _img_to_bmp_bytes(im: "Image.Image") -> bytes:
                """Convierte una imagen RGBA a bytes BMP para embeber en .ico."""
                bmp_io = io.BytesIO()
                # .ico usa BMP sin file header, con altura doble (XOR + AND mask)
                w, h = im.size
                # BITMAPINFOHEADER
                header = struct.pack(
                    "<IiiHHIIiiII",
                    40,        # biSize
                    w, h * 2,  # width, height*2 (ico convention)
                    1,         # planes
                    32,        # bpp (RGBA)
                    0,         # compression (BI_RGB)
                    w * h * 4, # image size
                    0, 0,      # x/y pixels per meter
                    0, 0,      # colors used/important
                )
                bmp_io.write(header)
                # Pixel data — BMP es bottom-up, RGBA → BGRA
                pixels = im.tobytes("raw", "BGRA")
                # BMP bottom-up: invertir filas
                row_size = w * 4
                rows = [pixels[i * row_size:(i + 1) * row_size]
                        for i in range(h - 1, -1, -1)]
                bmp_io.write(b"".join(rows))
                # AND mask (todos transparentes = 0) con padding a 4 bytes
                mask_row = b"\x00" * ((w + 31) // 32 * 4)
                for _ in range(h):
                    bmp_io.write(mask_row)
                return bmp_io.getvalue()

            entries = []
            for im in sized_images:
                data = _img_to_bmp_bytes(im)
                w, h = im.size
                # En .ico, 256 se representa como 0
                entries.append((w if w < 256 else 0,
                                 h if h < 256 else 0,
                                 data))

            # Escribir el archivo .ico
            # Header: 6 bytes  |  Directory: 16 bytes × n  |  Data
            n = len(entries)
            header = struct.pack("<HHH", 0, 1, n)  # reserved, type=1(ICO), count
            offset = 6 + n * 16
            directory = b""
            image_data = b""
            for (w, h, data) in entries:
                size = len(data)
                directory += struct.pack(
                    "<BBBBHHII",
                    w, h,   # width, height (0 = 256)
                    0,       # color count (0 = >8bpp)
                    0,       # reserved
                    1,       # planes
                    32,      # bpp
                    size,    # data size
                    offset,  # offset to data
                )
                image_data += data
                offset += size

            with open(str(dst), "wb") as f:
                f.write(header + directory + image_data)

            self.var_icon.set(str(dst))
            status_msg = (
                f"✓ Convertido a .ico — {len(REQUIRED_SIZES)} tamaños (16→256px)"
                if src_ext != ".ico"
                else f"✓ Ícono regenerado — {len(REQUIRED_SIZES)} tamaños (16→256px)"
            )
            self.var_icon_status.set(status_msg)
            self.lbl_icon_status.configure(text_color=C["success"])
            self.log_view.append(f"✓ Ícono listo: {dst.name}", "SUCCESS")

        except Exception as e:
            self.var_icon_status.set(f"✗ Error: {e}")
            self.lbl_icon_status.configure(text_color=C["error"])
            self.log_view.append(f"✗ Error procesando ícono: {e}", "ERROR")

    def _on_build(self):
        if self.worker and self.worker.is_alive():
            messagebox.showinfo("En proceso", "Ya hay una compilación en curso.")
            return

        cfg = self._collect(); self.cfg = cfg

        if not cfg.script_path:
            messagebox.showerror("Script faltante",
                                  "Selecciona un script .py primero."); return
        if not Path(cfg.script_path).is_file():
            messagebox.showerror("No encontrado",
                                  f"No existe:\n{cfg.script_path}"); return
        if cfg.icon_path and not Path(cfg.icon_path).is_file():
            messagebox.showerror("Ícono no encontrado",
                                  f"No existe:\n{cfg.icon_path}"); return

        # Deshabilitar botón inmediatamente para feedback visual
        self.btn_build.configure(state="disabled")
        self.var_status.set("⏳ Verificando entorno Python...")
        self.log_view.append("⏳ Buscando Python y verificando PyInstaller...", "DIM")
        self.update_idletasks()

        # Hacer la verificación en un hilo para no bloquear la UI
        def _check_and_build():
            try:
                python_exe = _get_python_exe()
            except RuntimeError as e:
                self.after(0, lambda: self._on_check_failed(str(e)))
                return

            try:
                subprocess.run([python_exe, "-m", "PyInstaller", "--version"],
                               capture_output=True, check=True,
                               creationflags=SUBPROCESS_FLAGS)
                self.after(0, lambda: self._launch_build(cfg))
            except (subprocess.CalledProcessError, FileNotFoundError):
                self.after(0, lambda: self._ask_install_pyinstaller(cfg))

        threading.Thread(target=_check_and_build, daemon=True).start()

    def _on_check_failed(self, msg: str):
        self.btn_build.configure(state="normal")
        self.var_status.set("✗ Error")
        messagebox.showerror("Python no encontrado", msg)

    def _ask_install_pyinstaller(self, cfg: BuildConfig):
        self.btn_build.configure(state="normal")
        if not messagebox.askyesno(
            "PyInstaller no instalado",
            "PyInstaller no está instalado.\n\n¿Instalarlo ahora con pip?"
        ): return
        self._install_then_build(cfg)

    def _install_then_build(self, cfg: BuildConfig):
        self.log_view.clear()
        self.log_view.append("Instalando PyInstaller...", "INFO")
        self.btn_build.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.bridge = Bridge()
        br = self.bridge

        def worker():
            try:
                proc = subprocess.Popen(
                    [_get_python_exe(), "-m", "pip", "install", "pyinstaller"],
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=SUBPROCESS_FLAGS)
                br.cancel.proc = proc
                for line in proc.stdout: br.log(line.rstrip(), "DIM")
                proc.wait()
                if proc.returncode == 0:
                    br.log("✓ PyInstaller instalado.", "SUCCESS")
                    br.done(True, "instalado")
                else:
                    br.done(False, "Error instalando PyInstaller")
            except Exception as e:
                br.done(False, str(e))

        self._pending = cfg
        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _launch_build(self, cfg: BuildConfig):
        self.log_view.clear()
        self.bridge = Bridge()
        self.btn_build.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.var_status.set("Compilando…")
        br = self.bridge

        args    = cfg.build_args()
        cmd_str = "pyinstaller " + " ".join(
            f'"{a}"' if " " in a else a for a in args)
        self.log_view.append("═" * 55, "DIM")
        self.log_view.append("  COMPILACIÓN INICIADA", "SUCCESS")
        self.log_view.append("═" * 55, "DIM")
        self.log_view.append(f"CMD: {cmd_str}", "CMD")
        self.log_view.append("", "INFO")

        def worker():
            try:
                proc = subprocess.Popen(
                    [_get_python_exe(), "-m", "PyInstaller"] + args,
                    stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                    text=True, encoding="utf-8", errors="replace",
                    creationflags=SUBPROCESS_FLAGS)
                br.cancel.proc = proc
                permission_error_detected = False
                permission_error_path     = ""
                for line in proc.stdout:
                    line = line.rstrip()
                    if not line: continue
                    lo  = line.lower()
                    lvl = ("ERROR"   if "error" in lo or "failed" in lo else
                           "WARNING" if "warn"  in lo else
                           "DIM"     if any(x in lo for x in
                                            ("info:", "building", "copying")) else
                           "INFO")
                    br.log(line, lvl)
                    # Detectar PermissionError WinError 5 en el output de PyInstaller
                    if "permissionerror" in lo and ("winerror 5" in lo or "access is denied" in lo):
                        permission_error_detected = True
                        # Intentar extraer la ruta del mensaje
                        import re
                        m = re.search(r"'([^']+)'$", line)
                        if m:
                            permission_error_path = m.group(1)
                proc.wait()
                if br.cancel.is_set():
                    br.done(False, "Cancelado.")
                elif proc.returncode == 0:
                    br.done(True, "Compilación exitosa.")
                else:
                    if permission_error_detected:
                        br.done(False, _PERMISSION_ERROR_MSG.format(
                            path=permission_error_path or "(carpeta build)"))
                    else:
                        br.done(False, f"PyInstaller terminó con código {proc.returncode}.")
            except Exception as e:
                br.log(traceback.format_exc(), "ERROR")
                br.done(False, str(e))

        self.worker = threading.Thread(target=worker, daemon=True)
        self.worker.start()

    def _on_stop(self):
        if self.bridge:
            self.bridge.cancel.cancel()
            self.log_view.append("⏹ Cancelando...", "WARNING")
            self.btn_stop.configure(state="disabled")

    def _open_dist(self):
        cfg  = self._collect()
        dist = cfg.output_dir.strip() or (
            str(Path(cfg.script_path).parent / "dist")
            if cfg.script_path else "dist")
        p = Path(dist)
        if not p.exists():
            messagebox.showwarning("No encontrada",
                                   f"La carpeta dist no existe aún:\n{dist}")
            return
        try:
            if sys.platform == "win32":   os.startfile(str(p))
            elif sys.platform == "darwin": subprocess.Popen(["open", str(p)])
            else:                          subprocess.Popen(["xdg-open", str(p)])
        except Exception as e:
            messagebox.showerror("Error", str(e))

    # ── Poll ──────────────────────────────────────────────────────────────────

    def _poll(self):
        try:
            if self.bridge:
                for ev, payload in self.bridge.drain():
                    if ev == "log":
                        self.log_view.append(*payload)
                    elif ev == "done":
                        self._on_done(*payload)
        except Exception as e:
            self.log_view.append(f"(Error interno: {e})", "ERROR")
        finally:
            self.after(100, self._poll)

    def _on_done(self, ok: bool, summary: str):
        self.btn_build.configure(state="normal")
        self.btn_stop.configure(state="disabled")

        if ok:
            self.var_status.set(f"✓ {summary}")
            self.log_view.append("═" * 55, "DIM")
            self.log_view.append("  ✓ COMPILACIÓN COMPLETADA", "SUCCESS")
            self.log_view.append("═" * 55, "DIM")
            pending = getattr(self, "_pending", None)
            if pending:
                self._pending = None
                self._launch_build(pending)
                return
            dist = self.cfg.output_dir.strip() or str(
                Path(self.cfg.script_path).parent / "dist")
            if messagebox.askyesno("¡Listo!",
                                   f"Ejecutable generado en:\n{dist}\n\n"
                                   "¿Abrir la carpeta?"):
                self._open_dist()
        else:
            self.var_status.set(f"✗ {summary}")
            self.log_view.append("═" * 55, "DIM")
            self.log_view.append(f"  ✗ {summary}", "ERROR")
            self.log_view.append("═" * 55, "DIM")
            # Mostrar diálogo especial si el error es de permisos
            is_permission = (
                "error de permisos" in summary.lower()
                or "access is denied" in summary.lower()
                or "winerror 5" in summary.lower()
            )
            if is_permission:
                # Extraer ruta build del summary para pasarla al diálogo
                import re as _re
                m = _re.search(r"Ruta bloqueada:\\n  (.+?)\\n", summary)
                blocked = m.group(1).strip() if m else ""
                # Subir hasta la raíz de build/ (dos niveles desde localpycs)
                build_root = ""
                if blocked:
                    from pathlib import Path as _Path
                    p = _Path(blocked)
                    # Buscar "build" en los ancestros
                    for part in p.parents:
                        if part.name == "build":
                            build_root = str(part)
                            break
                    if not build_root:
                        build_root = str(_Path(self.cfg.script_path).parent / "build")
                else:
                    build_root = str(Path(self.cfg.script_path).parent / "build")
                dlg = PermissionErrorDialog(self, summary, build_root)
                if dlg.result in ("force", "retry"):
                    if dlg.result == "force":
                        self._force_delete_build(build_root)
                    self._launch_build(self.cfg)

    def _force_delete_build(self, build_root: str):
        """
        Intenta borrar la carpeta build forzadamente.
        Primero intenta shutil.rmtree; si falla por permisos, usa
        'rd /s /q' (Windows) como último recurso.
        """
        import shutil
        p = Path(build_root)
        if not p.exists():
            self.log_view.append(f"ℹ Carpeta build no encontrada: {build_root}", "INFO")
            return
        self.log_view.append(f"🗑 Forzando borrado de: {build_root}", "WARNING")
        try:
            shutil.rmtree(str(p), ignore_errors=False)
            self.log_view.append("✓ Carpeta build eliminada.", "SUCCESS")
        except Exception as e:
            self.log_view.append(f"  shutil.rmtree falló: {e}", "WARNING")
            self.log_view.append("  Intentando con 'rd /s /q'...", "WARNING")
            try:
                result = subprocess.run(
                    ["cmd", "/c", "rd", "/s", "/q", str(p)],
                    capture_output=True, text=True,
                    creationflags=SUBPROCESS_FLAGS)
                if result.returncode == 0:
                    self.log_view.append("✓ Carpeta build eliminada (cmd).", "SUCCESS")
                else:
                    self.log_view.append(
                        f"  rd /s /q falló (código {result.returncode}): "
                        f"{result.stderr.strip()}", "ERROR")
            except Exception as e2:
                self.log_view.append(f"  Error al ejecutar rd: {e2}", "ERROR")

    def _on_close(self):
        if self.worker and self.worker.is_alive():
            if not messagebox.askyesno("Salir",
                                       "Compilación en curso.\n\n¿Salir y cancelar?"):
                return
            if self.bridge: self.bridge.cancel.cancel()
        try:
            self.cfg = self._collect()
            self.cfg.save(self.config_path)
        except Exception: pass
        self.destroy()


# ─── ENTRY ────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    app = App()
    app.mainloop()