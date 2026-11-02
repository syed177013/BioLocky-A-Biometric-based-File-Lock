import ctypes
import io
import os
import subprocess
import sys
import time
import tempfile
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog

import customtkinter as ctk
from PIL import Image, ImageTk

from .. import __version__, legacy, mailer
from ..config import (APP_DIR, APP_ICON, ASSET_DIR, GITHUB_URL, HOME, ICON_DIR, LEGACY_DIR, RES_DIR, Settings)
from ..vault import Vault, BadSecret, Throttled, b64, unb64
from . import sheets
from .theme import TOK, Fonts, col
from .widgets import Bg, Btn, Field, FileGrid, draw_lock

AUTOLOCK = {"1 minute": 1, "2 minutes": 2, "5 minutes": 5, "10 minutes": 10, "15 minutes": 15, "Never": 0}
RELOCK = {"30 seconds": 30, "1 minute": 60, "2 minutes": 120, "5 minutes": 300, "10 minutes": 600}


def rev(d, v):
    return next((k for k, x in d.items() if x == v), next(iter(d)))


class App(ctk.CTk):
    def __init__(self):
        if sys.platform.startswith("win"):   # own taskbar group + icon instead of python.exe's
            try:
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("BioLocky.App")
            except Exception:
                pass
        super().__init__()
        self._icon_pil = None
        self.settings = Settings(HOME / "settings.json")
        ctk.set_appearance_mode(self.settings.get("theme"))
        self.vault = Vault(HOME)
        self.res = RES_DIR
        self.sheet = None
        self.files_unlocked = False
        self._announce = False
        self._count = 0
        self.last_active = time.time()
        self._themed, self._icons, self._thumb_cache = [], {}, {}
        self.fonts = Fonts(self)
        self._load_icon()
        self._apply_icon()                  # before CTk's own 200 ms icon timer, so it is skipped
        try:
            self.scale = ctk.ScalingTracker.get_window_scaling(self)
        except Exception:
            self.scale = 1.0
        self.bg = Bg(self)
        self.bg.on_error = lambda ex: self.toast(sheets.err_text(ex))
        self.title("BioLocky")
        self.geometry("1040x660")
        self.minsize(860, 560)
        self.configure(fg_color=TOK["bg"])
        self._build_shell()
        self.protocol("WM_DELETE_WINDOW", self.quit_app)
        for ev in ("<Motion>", "<Key>", "<Button>"):
            self.bind_all(ev, self._touch, add="+")
        self.bind("<Escape>", lambda e: self.sheet and self.sheet.close())
        self.show_lock()
        self.after(350, self._apply_icon)  # re-apply in case the toolkit replaced it
        self.after(5000, self._tick)

    # ------------------------------------------------------------ helpers
    def _icon_source(self):
        p = Path(os.path.expanduser(str(APP_ICON)))
        if not p.is_absolute():
            p = APP_DIR / p
        for c in (p, p.with_suffix(".png"), p.with_suffix(".ico")):
            if c.is_file():
                return c
        print(f"[BioLocky] App icon not found: {p}")
        return None

    def _load_icon(self):
        src = self._icon_source()
        if not src:
            return
        try:
            im = Image.open(src)
            im.load()
            im = im.convert("RGBA")
            side = max(im.size)                      # pad to a square so nothing is stretched
            sq = Image.new("RGBA", (side, side), (0, 0, 0, 0))
            sq.paste(im, ((side - im.width) // 2, (side - im.height) // 2))
            self._icon_pil = sq
        except Exception as ex:
            print(f"[BioLocky] Couldn't read app icon {src}: {ex}")

    def _build_ico(self):
        path = Path(tempfile.gettempdir()) / "biolocky_icon.ico"
        self._icon_pil.save(path, format="ICO", sizes=[(s, s) for s in (16, 24, 32, 48, 64, 128, 256)])
        return path

    def _apply_icon(self):
        if self._icon_pil is None:
            return
        try:
            big = self._icon_pil.resize((256, 256), Image.LANCZOS) if self._icon_pil.width > 256 else self._icon_pil
            self._icon_img = ImageTk.PhotoImage(big)
            self.iconphoto(True, self._icon_img)
            if sys.platform.startswith("win"):       # title bar + taskbar need a real .ico
                self.iconbitmap(str(self._build_ico()))
        except Exception as ex:
            print(f"[BioLocky] Couldn't apply app icon: {ex}")

    def _logo(self, canvas, cx, cy, size, bg):
        """App icon if one is configured, otherwise the built-in padlock."""
        canvas.delete("all")
        if self._icon_pil is not None:
            px = max(8, int(size * self.scale))
            canvas._logo_img = ImageTk.PhotoImage(self._icon_pil.resize((px, px), Image.LANCZOS))
            canvas.create_image(cx, cy, image=canvas._logo_img)
        else:
            draw_lock(canvas, cx, cy, size * 0.78, col("accent"), bg)

    def _status(self):
        n, s = self._count, len(self.grid_view.sel)
        parts = [f"{n} item{'s' if n != 1 else ''}"]
        if s:
            parts.append(f"{s} selected")
        parts.append("Files unlocked" if self.files_unlocked else "Vault unlocked")
        self.status_left.configure(text=" · ".join(parts))

    def _touch(self, _=None):
        self.last_active = time.time()

    @staticmethod
    def fmt_size(n):
        for u in ("B", "KB", "MB", "GB"):
            if n < 1024 or u == "GB":
                return f"{n:.0f} {u}" if u == "B" else f"{n:.1f} {u}"
            n /= 1024

    def themed(self, widget, **opts):
        self._themed.append((widget, opts))
        widget.configure(**{k: col(v) for k, v in opts.items()})
        return widget

    def restyle(self):
        self._themed = [(w, o) for w, o in self._themed if w.winfo_exists()]
        for w, o in self._themed:
            w.configure(**{k: col(v) for k, v in o.items()})
        self.grid_view.redraw()
        if self.lockview.winfo_ismapped():
            self.show_lock()

    def icon(self, name, size):
        key = (name, size)
        if key not in self._icons:
            self._icons[key] = ctk.CTkImage(Image.open(ASSET_DIR / name), size=(size, size))
        return self._icons[key]

    def thumb_image(self, e):
        """PIL image for a grid card (blurred thumb for images, extension icon otherwise)."""
        if e.get("thumb"):
            return Image.open(io.BytesIO(unb64(e["thumb"]))).convert("RGBA")
        ext = os.path.splitext(e["name"])[1][1:].lower()
        if ext not in self._thumb_cache:
            p = ICON_DIR / f"{ext}.png"
            p = p if ext and p.exists() else ICON_DIR / "default.png"
            im = Image.open(p).convert("RGBA").resize((int(64 * self.scale), int(64 * self.scale)), Image.LANCZOS)
            self._thumb_cache[ext] = im
        return self._thumb_cache[ext]

    def toast(self, text, ms=2800):
        t = ctk.CTkLabel(self, text=text, font=self.fonts.body, text_color=TOK["toast_t"],
                         fg_color=TOK["toast"], corner_radius=8, height=34, padx=16)
        t.place(relx=.5, rely=1.0, y=-int(52 * self.scale), anchor="s")
        t.lift()
        self.after(ms, t.destroy)

    def log_event(self, kind, msg, thumb=None):
        if self.vault.unlocked:
            self.bg.run(lambda: self.vault.add_event(kind, msg, thumb))

    def set_progress(self, frac, text=""):
        self.status_right.configure(text=text)
        if frac is None:
            self.progress.grid_remove()
        else:
            self.progress.grid()
            self.progress.set(frac)

    # ------------------------------------------------------------ shell
    def _build_shell(self):
        F = self.fonts
        self.grid_columnconfigure(1, weight=1)
        self.grid_rowconfigure(0, weight=1)
        side = ctk.CTkFrame(self, width=214, corner_radius=0, fg_color=TOK["side"])
        side.grid(row=0, column=0, sticky="nsw", rowspan=2)
        side.grid_propagate(False)
        ctk.CTkFrame(self, width=1, corner_radius=0, fg_color=TOK["line"]).grid(row=0, column=0, sticky="nse", rowspan=2)
        brand = ctk.CTkFrame(side, fg_color="transparent")
        brand.pack(fill="x", padx=18, pady=(22, 18))
        self.brand_icon = tk.Canvas(brand, width=30, height=34, bd=0, highlightthickness=0)
        self.brand_icon.pack(side="left")
        self.themed(self.brand_icon, bg="side")
        self._paint_brand()
        ctk.CTkLabel(brand, text="BioLocky", font=F.h2, text_color=TOK["text"]).pack(side="left", padx=8)

        self.nav = {}
        for key, label in (("files", "Files"), ("activity", "Activity"), ("settings", "Settings")):
            b = ctk.CTkButton(side, text=label, anchor="w", height=34, corner_radius=7, font=F.body,
                              fg_color="transparent", hover_color=TOK["sel"], text_color=TOK["text"],
                              command=lambda k=key: self.show_page(k))
            b.pack(fill="x", padx=10, pady=1)
            self.nav[key] = b
        foot = ctk.CTkFrame(side, fg_color="transparent")
        foot.pack(side="bottom", fill="x", padx=12, pady=16)
        Btn(foot, "Lock Vault", self.lock_now, F, width=190).pack()

        main = ctk.CTkFrame(self, corner_radius=0, fg_color=TOK["bg"])
        main.grid(row=0, column=1, sticky="nsew")
        main.grid_columnconfigure(0, weight=1)
        main.grid_rowconfigure(0, weight=1)
        self.pages = {k: ctk.CTkFrame(main, fg_color=TOK["bg"], corner_radius=0) for k in self.nav}
        self._build_files(self.pages["files"])
        self._build_activity(self.pages["activity"])
        self._build_settings(self.pages["settings"])
        for p in self.pages.values():
            p.grid(row=0, column=0, sticky="nsew")

        bar = ctk.CTkFrame(self, height=28, corner_radius=0, fg_color=TOK["side"])
        bar.grid(row=1, column=1, sticky="ew")
        bar.grid_columnconfigure(1, weight=1)
        self.status_left = ctk.CTkLabel(bar, text="", font=F.small, text_color=TOK["muted"])
        self.status_left.grid(row=0, column=0, padx=14, pady=4)
        self.status_right = ctk.CTkLabel(bar, text="", font=F.small, text_color=TOK["muted"])
        self.status_right.grid(row=0, column=1, sticky="e", padx=8)
        self.progress = ctk.CTkProgressBar(bar, width=140, height=6, progress_color=TOK["accent"], fg_color=TOK["line"])
        self.progress.grid(row=0, column=2, padx=(0, 14))
        self.progress.grid_remove()

        self.lockview = ctk.CTkFrame(self, corner_radius=0, fg_color=TOK["bg"])
        self.show_page("files")

    def _paint_brand(self):
        self._logo(self.brand_icon, 15, 17, 28, col("side"))

    def show_page(self, key):
        self.pages[key].lift()
        for k, b in self.nav.items():
            b.configure(fg_color=TOK["sel"] if k == key else "transparent")
        if key == "activity":
            self.refresh_activity()
        elif key == "settings":
            self.refresh_settings()

    def _header(self, parent, title):
        h = ctk.CTkFrame(parent, fg_color="transparent")
        h.pack(fill="x", padx=24, pady=(22, 10))
        ctk.CTkLabel(h, text=title, font=self.fonts.h1, text_color=TOK["text"]).pack(side="left")
        return h

    # ------------------------------------------------------------ files page
    SORTS = {"Name": "name", "Date added": "added", "Date created": "created",
             "Date modified": "modified", "Type": "type", "Size": "size"}

    def _build_files(self, page):
        F = self.fonts
        h = self._header(page, "Files")
        Btn(h, "Add Files", self.add_files, F, "primary", 104).pack(side="right")
        Btn(h, "?", lambda: sheets.help_sheet(self), F, width=34).pack(side="right", padx=8)
        self.search = Field(h, F, placeholder="Search", width=200)
        self.search.configure(height=30)
        self.search.pack(side="right")
        self._search_job = None
        self.search.bind("<KeyRelease>", lambda e: self._debounce_search())

        bar = ctk.CTkFrame(page, fg_color="transparent")
        bar.pack(fill="x", padx=24, pady=(0, 8))
        ctk.CTkLabel(bar, text="Sort by", font=F.small, text_color=TOK["muted"]).pack(side="left")
        self.sort_menu = ctk.CTkOptionMenu(
            bar, values=list(self.SORTS), command=self.set_sort, width=130, height=28, corner_radius=7,
            font=F.body, dropdown_font=F.body, fg_color=TOK["field"], button_color=TOK["line"],
            button_hover_color=TOK["sel"], text_color=TOK["text"], dropdown_fg_color=TOK["card"],
            dropdown_text_color=TOK["text"], dropdown_hover_color=TOK["sel"])
        self.sort_menu.set(rev(self.SORTS, self.settings.get("sort_key")))
        self.sort_menu.pack(side="left", padx=8)
        self.dir_btn = Btn(bar, "", self.toggle_dir, F, width=104, height=28)
        self.dir_btn.pack(side="left")
        self._paint_dir()
        Btn(bar, "Select All", lambda: self.grid_view.select_all(), F, height=28, width=90).pack(side="right")
        self.btn_delete = Btn(bar, "Delete", lambda: self.delete_files(self.grid_view.selected_ids()), F,
                              "danger", 76, 28)
        self.btn_delete.pack(side="right", padx=6)
        self.btn_export = Btn(bar, "Export", lambda: self.export_files(self.grid_view.selected_ids()), F,
                              width=76, height=28)
        self.btn_export.pack(side="right")
        self.sel_lbl = ctk.CTkLabel(bar, text="", font=F.small, text_color=TOK["muted"])
        self.sel_lbl.pack(side="right", padx=10)

        wrap = ctk.CTkFrame(page, fg_color="transparent")
        wrap.pack(fill="both", expand=True, padx=(10, 4), pady=(0, 4))
        self.grid_view = FileGrid(wrap, self, self.open_file, self.file_menu, self.delete_files, self.on_select)
        sb = ctk.CTkScrollbar(wrap, command=self.grid_view.yview, fg_color="transparent",
                              button_color=TOK["line"], button_hover_color=TOK["muted"])
        self.grid_view.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.grid_view.pack(side="left", fill="both", expand=True)

    def on_select(self, ids):
        n = len(ids)
        self.sel_lbl.configure(text=f"{n} selected" if n else "")
        st = "normal" if n else "disabled"
        self.btn_export.configure(state=st)
        self.btn_delete.configure(state=st)
        self._status()

    def _paint_dir(self):
        self.dir_btn.configure(text="↓ Descending" if self.settings.get("sort_desc") else "↑ Ascending")

    def set_sort(self, label):
        key = self.SORTS[label]
        if key != self.settings.get("sort_key"):
            self.settings.set("sort_key", key)
            # Explorer-style defaults: dates and sizes start newest/largest first
            self.settings.set("sort_desc", key in ("added", "created", "modified", "size"))
            self._paint_dir()
            self.refresh_files()

    def toggle_dir(self):
        self.settings.set("sort_desc", not self.settings.get("sort_desc"))
        self._paint_dir()
        self.refresh_files()

    @staticmethod
    def _sort_val(e, key):
        if key == "name":
            return e["name"].lower()
        if key == "type":
            return (os.path.splitext(e["name"])[1].lower(), e["name"].lower())
        if key == "size":
            return e["size"]
        return e.get(key) or e["added"]   # older entries have no created/modified

    def _debounce_search(self):
        if self._search_job:
            self.after_cancel(self._search_job)
        self._search_job = self.after(150, self.refresh_files)

    def refresh_files(self):
        if not self.vault.unlocked:
            return
        q = self.search.get().strip().lower()
        files = self.vault.files()
        self._count = len(files)
        shown = [e for e in files if q in e["name"].lower()] if q else files
        key = self.settings.get("sort_key")
        shown.sort(key=lambda e: e["name"].lower())          # stable tie-break
        shown.sort(key=lambda e: self._sort_val(e, key), reverse=bool(self.settings.get("sort_desc")))
        self.grid_view.set_items(shown)

    def add_files(self):
        paths = filedialog.askopenfilenames(title="Add files to BioLocky")
        if paths:
            self._import(list(paths))

    def _import(self, paths):
        move, total = self.settings.get("move_on_import"), len(paths)
        self.set_progress(0, f"Encrypting 1 of {total}")

        def job():
            ok, fail = 0, []
            for i, p in enumerate(paths):
                last = [-1.0]

                def prog(f, i=i, name=os.path.basename(p)):
                    if f - last[0] >= 0.02 or f >= 1:
                        last[0] = f
                        self.bg.post(self.set_progress, (i + f) / total, f"Encrypting {i + 1} of {total} · {name}")
                try:
                    self.vault.import_path(p, move, prog)
                    ok += 1
                except Exception as ex:
                    fail.append(f"{os.path.basename(p)}: {ex}")
            return ok, fail

        def done(r):
            ok, fail = r
            self.set_progress(None)
            self.refresh_files()
            if fail:
                sheets.info(self, "Some files couldn’t be added", "\n".join(fail[:4]))
            else:
                self.toast(f"{ok} file{'s' if ok != 1 else ''} secured" + (" and moved" if move else ""))
        self.bg.run(job, done, lambda ex: (self.set_progress(None), self.toast(sheets.err_text(ex))))

    # ---- open / export / delete
    @property
    def _session_open(self):
        return self.files_unlocked and self.settings.get("keep_unlocked")

    def file_menu(self, fid, x, y):
        ids = self.grid_view.selected_ids()
        n = len(ids)
        m = tk.Menu(self, tearoff=0)
        if n <= 1:
            if self._session_open:
                m.add_command(label="Open", command=lambda: self.open_file(fid))
            else:
                m.add_command(label="Open with Face", command=lambda: self.open_file(fid, "face"))
                m.add_command(label="Open with Voice", command=lambda: self.open_file(fid, "voice"))
                m.add_command(label="Open with Passcode", command=lambda: self.open_file(fid, "passcode"))
            m.add_separator()
        m.add_command(label="Export…" if n <= 1 else f"Export {n} files…", command=lambda: self.export_files(ids))
        m.add_command(label="Delete…" if n <= 1 else f"Delete {n} files…", command=lambda: self.delete_files(ids))
        m.tk_popup(x, y)

    def gate(self, method, then):
        v = self.vault
        if method == "face":
            if not v.has_faces:
                return self.toast("Set up Face Unlock in Settings first")
            sheets.FaceSheet(self, "verify", then)
        elif method == "voice":
            if not v.has_voice:
                return self.toast("Record a voice passphrase in Settings first")
            sheets.VoiceSheet(self, "verify", then)
        else:
            sheets.ask_passcode(self, "Confirm it’s you", then)

    def open_file(self, fid, method=None):
        if self._session_open:                       # already authenticated this session
            return self._decrypt_and_launch(fid)
        v = self.vault
        method = method or ("face" if v.has_faces else "voice" if v.has_voice else "passcode")

        def ok():
            if self.settings.get("keep_unlocked"):
                self.files_unlocked, self._announce = True, True
                self._status()
            self._decrypt_and_launch(fid)
        self.gate(method, ok)

    def _decrypt_and_launch(self, fid):
        self.set_progress(0.0, "Decrypting…")
        self.progress.configure(mode="indeterminate")
        self.progress.start()

        def done(path):
            self._stop_busy()
            self._launch(path)
            msg = f"Opened. It will re-lock in {rev(RELOCK, self.settings.get('relock_sec')).lower()}."
            if self._announce:
                self._announce = False
                msg = "Opened. All files stay unlocked until the vault locks."
            self.toast(msg)
        self.bg.run(lambda: self.vault.open_temp(fid, self.settings.get("relock_sec")), done,
                    lambda ex: (self._stop_busy(), self.toast(sheets.err_text(ex))))

    def _stop_busy(self):
        self.progress.stop()
        self.progress.configure(mode="determinate")
        self.set_progress(None)

    @staticmethod
    def _launch(path):
        try:
            if sys.platform.startswith("win"):
                os.startfile(path)  # noqa
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

    @staticmethod
    def _unique(name, folder, used):
        stem, ext = os.path.splitext(name)
        cand, n = name, 1
        while cand.lower() in used or os.path.exists(os.path.join(folder, cand)):
            n += 1
            cand = f"{stem} ({n}){ext}"
        used.add(cand.lower())
        return cand

    def export_files(self, ids):
        if not ids:
            return
        entries = [self.vault.entry(i) for i in ids]

        def go():
            if len(entries) == 1:
                dest = filedialog.asksaveasfilename(initialfile=entries[0]["name"], title="Export decrypted copy")
                jobs = [(entries[0]["id"], dest)] if dest else []
            else:
                folder = filedialog.askdirectory(title=f"Export {len(entries)} files to…")
                used = set()
                jobs = [(e["id"], os.path.join(folder, self._unique(e["name"], folder, used)))
                        for e in entries] if folder else []
            if not jobs:
                return
            total = len(jobs)
            self.set_progress(0, f"Exporting 1 of {total}")

            def job():
                ok, fail = 0, []
                for i, (fid, dest) in enumerate(jobs):
                    try:
                        self.vault.export(fid, dest)
                        ok += 1
                    except Exception as ex:
                        fail.append(f"{os.path.basename(dest)}: {ex}")
                    self.bg.post(self.set_progress, (i + 1) / total, f"Exporting {min(i + 2, total)} of {total}")
                return ok, fail

            def done(r):
                self.set_progress(None)
                if r[1]:
                    sheets.info(self, "Some files couldn’t be exported", "\n".join(r[1][:4]))
                else:
                    self.toast(f"Exported {r[0]} file{'s' if r[0] != 1 else ''}")
            self.bg.run(job, done, lambda ex: (self.set_progress(None), self.toast(sheets.err_text(ex))))
        sheets.ask_passcode(self, "Export decrypted copies", go, "Exported copies are not protected.")

    def delete_files(self, ids):
        if not ids:
            return
        what = f"“{self.vault.entry(ids[0])['name']}”" if len(ids) == 1 else f"{len(ids)} files"
        sheets.confirm(self, "Delete permanently?", f"{what} will be permanently removed from the vault.",
                       "Delete", lambda: self.bg.run(lambda: self.vault.delete_many(ids),
                                                    lambda _: self.refresh_files()), danger=True)

    # ------------------------------------------------------------ intruder
    def intruder(self, jpg):
        self.log_event("denied", "Unrecognised face at unlock", jpg)
        cfg = self.vault.mail_cfg()
        if mailer.configured(cfg):
            mailer.send_async(cfg, jpg, lambda ok, msg: self.bg.post(self.log_event, "mail", msg))

    # ------------------------------------------------------------ activity
    def _build_activity(self, page):
        h = self._header(page, "Activity")
        Btn(h, "Clear", lambda: self.bg.run(self.vault.clear_events, lambda _: self.refresh_activity()),
            self.fonts).pack(side="right")
        self.act_list = ctk.CTkScrollableFrame(page, fg_color="transparent", corner_radius=0)
        self.act_list.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        self._act_imgs = []

    def refresh_activity(self):
        for w in self.act_list.winfo_children():
            w.destroy()
        self._act_imgs.clear()
        if not self.vault.unlocked:
            return
        evs = self.vault.events()
        if not evs:
            ctk.CTkLabel(self.act_list, text="No activity yet.", font=self.fonts.body,
                         text_color=TOK["muted"]).pack(pady=40)
        for ev in evs[:60]:
            row = ctk.CTkFrame(self.act_list, fg_color=TOK["card"], corner_radius=10, border_width=1,
                               border_color=TOK["line"])
            row.pack(fill="x", pady=4, padx=6)
            if ev.get("thumb"):
                img = ctk.CTkImage(Image.open(io.BytesIO(unb64(ev["thumb"]))), size=(48, 48))
                self._act_imgs.append(img)
                ctk.CTkLabel(row, image=img, text="").pack(side="left", padx=10, pady=8)
            tone = {"denied": "danger", "granted": "accent"}.get(ev["kind"], "muted")
            col_f = ctk.CTkFrame(row, fg_color="transparent")
            col_f.pack(side="left", pady=8, padx=(12 if not ev.get("thumb") else 0, 0))
            ctk.CTkLabel(col_f, text=ev["msg"], font=self.fonts.bold, text_color=TOK[tone], anchor="w").pack(anchor="w")
            ctk.CTkLabel(col_f, text=time.strftime("%d %b %Y, %H:%M", time.localtime(ev["t"])),
                         font=self.fonts.small, text_color=TOK["muted"]).pack(anchor="w")

    # ------------------------------------------------------------ settings
    def _build_settings(self, page):
        self._header(page, "Settings")
        sc = ctk.CTkScrollableFrame(page, fg_color="transparent", corner_radius=0)
        sc.pack(fill="both", expand=True, padx=14, pady=(0, 8))
        F, S = self.fonts, self.settings

        def group(title):
            ctk.CTkLabel(sc, text=title.upper(), font=F.small, text_color=TOK["muted"]).pack(anchor="w", padx=14, pady=(14, 4))
            g = ctk.CTkFrame(sc, fg_color=TOK["card"], corner_radius=10, border_width=1, border_color=TOK["line"])
            g.pack(fill="x", padx=6)
            g.n = 0
            return g

        def row(g, label, widget_fn, sub=None):
            if g.n:
                ctk.CTkFrame(g, height=1, fg_color=TOK["line"]).pack(fill="x", padx=14)
            g.n += 1
            r = ctk.CTkFrame(g, fg_color="transparent")
            r.pack(fill="x", padx=14, pady=9)
            left = ctk.CTkFrame(r, fg_color="transparent")
            left.pack(side="left")
            ctk.CTkLabel(left, text=label, font=F.body, text_color=TOK["text"]).pack(anchor="w")
            lbl = None
            if sub is not None:
                lbl = ctk.CTkLabel(left, text=sub, font=F.small, text_color=TOK["muted"])
                lbl.pack(anchor="w")
            widget_fn(r).pack(side="right")
            return lbl

        def menu(values, current, cb):
            def make(p):
                m = ctk.CTkOptionMenu(p, values=list(values), command=cb, width=130, height=30, corner_radius=7,
                                      font=F.body, dropdown_font=F.body, fg_color=TOK["field"],
                                      button_color=TOK["line"], button_hover_color=TOK["sel"],
                                      text_color=TOK["text"], dropdown_fg_color=TOK["card"],
                                      dropdown_text_color=TOK["text"], dropdown_hover_color=TOK["sel"])
                m.set(current)
                return m
            return make

        g = group("Unlock methods")
        self.lbl_face = row(g, "Face Unlock", lambda p: Btn(p, "Set Up", self.enroll_face, F, width=96), "")
        self.btn_face = None
        self.lbl_voice = row(g, "Voice Passphrase", lambda p: Btn(p, "Record", self.enroll_voice, F, width=96), "")
        row(g, "Passcode", lambda p: Btn(p, "Change…", lambda: sheets.change_passcode(self), F, width=96),
            "Protects the vault and every setting on this page")
        row(g, "Intruder Alerts", lambda p: Btn(p, "Configure…", lambda: sheets.mail_config(self), F, width=96),
            "E-mail a photo after a failed face unlock")

        g = group("Privacy")
        row(g, "Auto-lock vault", menu(AUTOLOCK, rev(AUTOLOCK, S.get("autolock_min")),
                                       lambda v: S.set("autolock_min", AUTOLOCK[v])), "After inactivity")
        row(g, "Re-lock opened files", menu(RELOCK, rev(RELOCK, S.get("relock_sec")),
                                            lambda v: S.set("relock_sec", RELOCK[v])),
            "Decrypted copies are wiped after this long")

        def mk_switch(p):
            sw = ctk.CTkSwitch(p, text="", width=44, progress_color=TOK["accent"], fg_color=TOK["line"],
                               command=lambda: S.set("move_on_import", bool(sw.get())))
            sw.select() if S.get("move_on_import") else sw.deselect()
            return sw
        row(g, "Move files on import", mk_switch, "Delete the original once the encrypted copy is verified")

        def mk_keep(p):
            def chg():
                S.set("keep_unlocked", bool(sw.get()))
                self.files_unlocked = self.files_unlocked and bool(sw.get())
                self._status()
            sw = ctk.CTkSwitch(p, text="", width=44, progress_color=TOK["accent"], fg_color=TOK["line"], command=chg)
            sw.select() if S.get("keep_unlocked") else sw.deselect()
            return sw
        row(g, "Stay unlocked after first unlock", mk_keep,
            "One face, voice or passcode check opens every file until the vault locks")

        g = group("Appearance")
        row(g, "Theme", lambda p: ctk.CTkSegmentedButton(
            p, values=["Light", "Dark", "System"], command=self.set_theme, font=F.body, height=30,
            selected_color=TOK["accent"], selected_hover_color=TOK["accent_h"], unselected_color=TOK["field"],
            unselected_hover_color=TOK["sel"], text_color=TOK["text"]), None)
        seg = [w for w in g.winfo_children()[-1].winfo_children() if isinstance(w, ctk.CTkSegmentedButton)]
        if seg:
            seg[0].set(S.get("theme"))

        g = group("About")
        row(g, f"BioLocky {__version__}", lambda p: Btn(p, "GitHub", lambda: webbrowser.open_new_tab(GITHUB_URL), F, width=96),
            "Encrypted with AES-256-GCM · keys derived with scrypt")

    def refresh_settings(self):
        if not self.vault.unlocked:
            return
        v = self.vault
        self.lbl_face.configure(text="Enrolled · re-enrol any time" if v.has_faces else "Not set up")
        self.lbl_voice.configure(text="Passphrase saved" if v.has_voice else "Not set up")

    def enroll_face(self):
        sheets.ask_passcode(self, "Set up Face Unlock", lambda: sheets.FaceSheet(self, "enroll", lambda: None),
                            "Your passcode is required to change biometrics.")

    def enroll_voice(self):
        sheets.ask_passcode(self, "Record passphrase", lambda: sheets.VoiceSheet(self, "enroll", lambda: None),
                            "Your passcode is required to change biometrics.")

    def set_theme(self, mode):
        self.settings.set("theme", mode)
        ctk.set_appearance_mode(mode)
        self.after(30, self._after_theme)

    def _after_theme(self):
        self._paint_brand()
        self.restyle()

    # ------------------------------------------------------------ lock screen
    def show_lock(self):
        lv = self.lockview
        for w in lv.winfo_children():
            w.destroy()
        lv.configure(fg_color=TOK["bg"])
        lv.place(x=0, y=0, relwidth=1, relheight=1)
        lv.lift()
        create = not self.vault.exists
        F = self.fonts
        box = ctk.CTkFrame(lv, fg_color="transparent")
        box.place(relx=.5, rely=.46, anchor="center")
        ic = tk.Canvas(box, width=84, height=92, bd=0, highlightthickness=0, bg=col("bg"))
        ic.pack()
        self._logo(ic, 42, 46, 72, col("bg"))
        ctk.CTkLabel(box, text="BioLocky", font=F.big, text_color=TOK["text"]).pack(pady=(10, 2))
        ctk.CTkLabel(box, text="Choose a passcode to protect your vault" if create else "Enter your passcode to unlock",
                     font=F.body, text_color=TOK["muted"]).pack(pady=(0, 16))
        e1 = Field(box, F, show="•", placeholder="Passcode (6+ characters)" if create else "Passcode")
        e1.pack(pady=4)
        e2 = None
        if create:
            e2 = Field(box, F, show="•", placeholder="Confirm passcode")
            e2.pack(pady=4)
        msg = ctk.CTkLabel(box, text="", font=F.small, text_color=TOK["danger"], height=20)
        msg.pack(pady=(6, 2))
        e1.focus_set()

        def fail(ex):
            btn.configure(state="normal")
            e1.delete(0, "end")
            msg.configure(text=sheets.err_text(ex), text_color=TOK["danger"])

        def go(_=None):
            pw = e1.get()
            if create:
                if len(pw) < 6:
                    return msg.configure(text="Use at least 6 characters.")
                if pw != e2.get():
                    return msg.configure(text="Passcodes don’t match.")
            elif not pw:
                return
            btn.configure(state="disabled")
            msg.configure(text="Creating vault…" if create else "Unlocking…", text_color=TOK["muted"])
            if create:
                self.bg.run(lambda: self.vault.create(pw), self._after_create, fail)
            else:
                self.bg.run(lambda: self.vault.unlock(pw), lambda _: self.on_unlocked(), fail)
        (e2 or e1).bind("<Return>", go)
        btn = Btn(box, "Create Vault" if create else "Unlock", go, F, "primary", 260, height=36)
        btn.pack(pady=8)
        if not create:
            Btn(box, "Forgot passcode?", self.recover, F, "ghost", 160).pack()

    def _after_create(self, code):
        self._touch()
        self.lockview.place_forget()
        self.refresh_files()
        self.refresh_settings()
        sheets.show_recovery(self, code, self.on_unlocked)

    def recover(self):
        sh = sheets.Sheet(self, "Reset passcode", 420, 390)
        sh.label("Enter your recovery code and choose a new passcode.", "muted")
        f = [Field(sh.body, self.fonts, placeholder=ph, show=s) for ph, s in
             (("Recovery code (XXXXX-XXXXX-…)", None), ("New passcode (6+ characters)", "•"), ("Confirm new passcode", "•"))]
        for x in f:
            x.pack(pady=4)
        msg = sh.label("", "danger", self.fonts.small, pady=0)

        def go(_=None):
            code, new, conf = (x.get() for x in f)
            if len(new) < 6 or new != conf:
                return msg.configure(text="Passcodes must match and be 6+ characters.")
            btn.configure(state="disabled")
            self.bg.run(lambda: self.vault.reset_with_recovery(code, new),
                        lambda _: (sh.close(cancel=False), self.on_unlocked()),
                        lambda ex: (msg.configure(text=sheets.err_text(ex)), btn.configure(state="normal")))
        sh.add_button("Cancel", sh.close)
        btn = sh.add_button("Reset", go, "primary")

    def on_unlocked(self):
        self._touch()
        self.files_unlocked = False
        self.lockview.place_forget()
        self.refresh_files()
        self.refresh_settings()
        self.show_page("files")
        n = legacy.count(LEGACY_DIR)
        if n:
            sheets.confirm(self, "Import from earlier version?",
                           f"Found {n} item(s) from the previous BioLocky (files, face data, passphrase). "
                           "They’ll be re-encrypted into the new vault and the old copies securely removed.",
                           "Import", self._migrate, cancel_label="Later")

    def _migrate(self):
        self.set_progress(0, "Importing earlier data…")

        def done(r):
            self.set_progress(None)
            self.refresh_files()
            self.refresh_settings()
            msg = f"Imported {r['files']} file(s)" + (f" and {r['faces']} face sample(s)" if r["faces"] else "") + "."
            if r["failed"]:
                msg += "\nNot imported:\n" + "\n".join(r["failed"][:3])
            sheets.info(self, "Import finished", msg)
        self.bg.run(lambda: legacy.migrate(self.vault, LEGACY_DIR,
                                           lambda f: self.bg.post(self.set_progress, f, "Importing earlier data…")),
                    done)

    def lock_now(self):
        self.files_unlocked = False
        if self.sheet:
            self.sheet.close(cancel=True, animate=False)
        self.grid_view.set_items([])
        self.search.delete(0, "end")
        self.status_left.configure(text="Vault locked")
        self.show_lock()
        self.bg.run(self.vault.lock)

    # ------------------------------------------------------------ timers / exit
    def _tick(self):
        v = self.vault
        if v.unlocked:
            if v._temps:
                self.bg.run(v.wipe_temps)
            mins = self.settings.get("autolock_min")
            if mins and time.time() - self.last_active > mins * 60 and not (self.sheet and self.bg.active):
                self.lock_now()
        self.after(5000, self._tick)

    def quit_app(self):
        if self.sheet:
            self.sheet.close(cancel=True, animate=False)
        try:
            self.vault.wipe_temps(force=True)
        finally:
            self.destroy()