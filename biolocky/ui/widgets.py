import queue
import sys
import tkinter as tk
import tkinter.font as tkfont
from concurrent.futures import ThreadPoolExecutor

import customtkinter as ctk
from PIL import Image, ImageTk

from .theme import TOK, col


def Btn(parent, text, command, fonts, kind="default", width=96, height=30, **kw):
    style = {
        "default": dict(fg_color=TOK["card"], hover_color=TOK["sel"], text_color=TOK["text"],
                        border_width=1, border_color=TOK["line"]),
        "primary": dict(fg_color=TOK["accent"], hover_color=TOK["accent_h"], text_color="#FFFFFF",
                        border_width=0),
        "danger":  dict(fg_color=TOK["card"], hover_color=TOK["sel"], text_color=TOK["danger"],
                        border_width=1, border_color=TOK["line"]),
        "ghost":   dict(fg_color="transparent", hover_color=TOK["sel"], text_color=TOK["accent"],
                        border_width=0),
    }[kind]
    style.update(kw)
    return ctk.CTkButton(parent, text=text, command=command, width=width, height=height,
                         corner_radius=7, font=fonts.body, **style)


def Field(parent, fonts, show=None, placeholder="", width=260):
    return ctk.CTkEntry(parent, show=show, placeholder_text=placeholder, width=width, height=36,
                        corner_radius=8, border_width=1, font=fonts.body, fg_color=TOK["field"],
                        border_color=TOK["line"], text_color=TOK["text"])


def draw_lock(c, cx, cy, s, fg, bg):
    c.delete("lock")
    w = max(2, int(s * 0.14))
    c.create_arc(cx - s * .3, cy - s * .62, cx + s * .3, cy + s * .2, start=0, extent=180,
                 style="arc", outline=fg, width=w, tags="lock")
    c.create_line(cx - s * .3, cy - s * .21, cx - s * .3, cy, fill=fg, width=w, tags="lock")
    c.create_line(cx + s * .3, cy - s * .21, cx + s * .3, cy, fill=fg, width=w, tags="lock")
    c.create_rectangle(cx - s * .5, cy - s * .02, cx + s * .5, cy + s * .55, fill=fg, outline=fg,
                       tags="lock")
    c.create_oval(cx - s * .09, cy + s * .14, cx + s * .09, cy + s * .32, fill=bg, outline=bg, tags="lock")
    c.create_rectangle(cx - s * .035, cy + s * .26, cx + s * .035, cy + s * .42, fill=bg, outline=bg,
                       tags="lock")


class Bg:
    """Runs work off the UI thread; results are delivered on the UI thread.
    Polls fast only while work is active, slowly otherwise (idle-friendly)."""

    def __init__(self, tk_root, workers=3):
        self.root, self.q, self.active = tk_root, queue.Queue(), 0
        self.pool = ThreadPoolExecutor(workers, thread_name_prefix="blk")
        self.on_error = lambda ex: None
        self._poll()

    def run(self, fn, done=None, err=None):
        self.active += 1

        def work():
            try:
                r = fn()
            except BaseException as ex:  # noqa
                self.q.put((self._finish, (err, ex, True)))
            else:
                self.q.put((self._finish, (done, r, False)))
        self.pool.submit(work)

    def post(self, fn, *a):
        self.q.put((fn, a))

    def _finish(self, cb, val, failed):
        self.active -= 1
        if failed and cb is None:
            self.on_error(val)
        elif cb:
            cb(val)

    def _poll(self):
        try:
            for _ in range(60):
                fn, a = self.q.get_nowait()
                fn(*a)
        except queue.Empty:
            pass
        self.root.after(20 if self.active else 200, self._poll)


class Sheet(ctk.CTkFrame):
    """Aqua-style sheet that slides down from the title bar and holds modal focus."""

    def __init__(self, app, title, width=420, height=260, on_close=None):
        if app.sheet is not None:
            app.sheet.close(cancel=False, animate=False)
        self.app, self.W, self.H, self.on_close = app, width, height, on_close
        self.s = app.scale
        super().__init__(app, width=width, height=height, corner_radius=12, border_width=1,
                         fg_color=TOK["card"], border_color=TOK["line"])
        app.sheet = self
        self.pack_propagate(False)
        self.grid_propagate(False)
        ctk.CTkLabel(self, text=title, font=app.fonts.h2, text_color=TOK["text"]).pack(pady=(26, 6))
        self.body = ctk.CTkFrame(self, fg_color="transparent")
        self.body.pack(fill="both", expand=True, padx=24, pady=(0, 18))
        self.buttons = ctk.CTkFrame(self, fg_color="transparent")
        self.buttons.pack(side="bottom", pady=(0, 18))
        self._y = -int(height * self.s) - 30
        self.place(relx=.5, y=self._y, anchor="n")
        self.lift()
        self._slide(-int(12 * self.s), 8)

    def _slide(self, target, frames):
        if not self.winfo_exists():
            return
        step = (target - self._y) / max(1, frames)
        self._y = int(self._y + step) if frames > 1 else target
        self.place_configure(y=self._y)
        if frames > 1:
            self.after(14, self._slide, target, frames - 1)
        elif target <= 0:
            try:
                self.grab_set()
            except tk.TclError:
                pass

    def add_button(self, text, command, kind="default", width=110):
        b = Btn(self.buttons, text, command, self.app.fonts, kind, width)
        b.pack(side="left", padx=6)
        return b

    def label(self, text, tone="text", font=None, wrap=None, **pk):
        l = ctk.CTkLabel(self.body, text=text, text_color=TOK[tone], font=font or self.app.fonts.body,
                         wraplength=wrap or int((self.W - 60) * self.s), justify="center")
        l.pack(**({"pady": 4} | pk))
        return l

    def close(self, cancel=True, animate=True):
        if not self.winfo_exists():
            return
        try:
            self.grab_release()
        except tk.TclError:
            pass
        if self.app.sheet is self:
            self.app.sheet = None
        if cancel and self.on_close:
            self.on_close()
        if animate:
            self.place_configure(y=self._y)
            self._slide(-int(self.H * self.s) - 30, 5)
            self.after(110, self.destroy)
        else:
            self.destroy()


class FileGrid(tk.Canvas):
    """Canvas-drawn grid with Explorer-style selection (click, Ctrl/Cmd-click, Shift-click, Ctrl+A)."""
    CW, CH, GAP = 148, 150, 14

    def __init__(self, master, app, on_open, on_menu, on_delete, on_select):
        super().__init__(master, highlightthickness=0, bd=0, bg=col("bg"), yscrollincrement=24)
        self.app, self.on_open, self.on_menu = app, on_open, on_menu
        self.on_delete, self.on_select = on_delete, on_select
        self.items, self.sel, self.anchor, self._photos, self._after = [], set(), None, {}, None
        self.s = app.scale
        fam = app.fonts.family
        self.f_name = tkfont.Font(family=fam, size=10)
        self.f_small = tkfont.Font(family=fam, size=9)
        self.f_empty = tkfont.Font(family=fam, size=15, weight="bold")
        self.mac = sys.platform == "darwin"
        self.bind("<Configure>", self._on_conf)
        self.bind("<Button-1>", self._click)
        self.bind("<Double-1>", self._dbl)
        for b in ("<Button-3>", "<Button-2>", "<Control-Button-1>"):
            self.bind(b, self._menu)
        self.bind("<Return>", lambda e: len(self.sel) == 1 and self.on_open(next(iter(self.sel))))
        self.bind("<Delete>", lambda e: self.sel and self.on_delete(self.selected_ids()))
        self.bind("<Escape>", lambda e: self.set_selection(set()))
        self.bind("<Control-a>", self._all)
        if self.mac:
            self.bind("<Command-a>", self._all)
        self.bind("<Enter>", self._bind_wheel)
        self.bind("<Leave>", self._unbind_wheel)

    # ---- data / selection
    def set_items(self, items):
        self.items = items
        self.sel &= {i["id"] for i in items}
        if self.anchor not in self.sel:
            self.anchor = None
        self._photos.clear()
        self.redraw()
        self.on_select(self.selected_ids())

    def selected_ids(self):
        return [e["id"] for e in self.items if e["id"] in self.sel]

    def set_selection(self, new):
        changed, self.sel = self.sel ^ new, set(new)
        for fid in changed:
            on = fid in self.sel
            self.itemconfig("bg:" + fid, outline=col("accent") if on else col("line"), width=2 if on else 1)
        if changed:
            self.on_select(self.selected_ids())

    def select_all(self):
        self.set_selection({e["id"] for e in self.items})

    def _all(self, _=None):
        self.select_all()
        return "break"

    # ---- drawing
    def _on_conf(self, _):
        if self._after:
            self.after_cancel(self._after)
        self._after = self.after(50, self.redraw)

    def _rr(self, x1, y1, x2, y2, r, **kw):
        p = [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
             x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]
        return self.create_polygon(p, smooth=True, **kw)

    def _fit(self, text, font, width):
        if font.measure(text) <= width:
            return text
        stem, dot, ext = text.rpartition(".")
        stem, ext = (stem, "." + ext) if dot and len(ext) <= 5 else (text, "")
        while stem and font.measure(stem + "…" + ext) > width:
            stem = stem[:-1]
        return stem + "…" + ext

    def _photo(self, e):
        if e["id"] not in self._photos:
            self._photos[e["id"]] = ImageTk.PhotoImage(self.app.thumb_image(e))
        return self._photos[e["id"]]

    def redraw(self):
        self._after = None
        self.delete("all")
        self.configure(bg=col("bg"))
        s, W = self.s, max(self.winfo_width(), 200)
        cw, ch, gap = int(self.CW * s), int(self.CH * s), int(self.GAP * s)
        if not self.items:
            self.create_text(W / 2, self.winfo_height() / 2 - 12 * s, text="Your vault is empty",
                             font=self.f_empty, fill=col("text"))
            self.create_text(W / 2, self.winfo_height() / 2 + 16 * s,
                             text="Choose “Add Files” to encrypt and move files into the vault.",
                             font=self.f_name, fill=col("muted"))
            self.configure(scrollregion=(0, 0, W, 1))
            return
        n = max(1, (W - gap) // (cw + gap))
        left = max(gap, (W - n * cw - (n - 1) * gap) // 2)
        for i, e in enumerate(self.items):
            x, y = left + (i % n) * (cw + gap), gap + (i // n) * (ch + gap)
            fid, sel = e["id"], e["id"] in self.sel
            t = ("id:" + fid,)
            self._rr(x, y, x + cw, y + ch, 10 * s, fill=col("card"), tags=t + ("bg:" + fid,),
                     outline=col("accent") if sel else col("line"), width=2 if sel else 1)
            self.create_image(x + cw / 2, y + 54 * s, image=self._photo(e), tags=t)
            self.create_text(x + cw / 2, y + ch - 38 * s, text=self._fit(e["name"], self.f_name, cw - 20 * s),
                             font=self.f_name, fill=col("text"), tags=t)
            self.create_text(x + cw / 2, y + ch - 18 * s, text=self.app.fmt_size(e["size"]),
                             font=self.f_small, fill=col("muted"), tags=t)
        rows = (len(self.items) + n - 1) // n
        self.configure(scrollregion=(0, 0, W, gap + rows * (ch + gap)))

    # ---- interaction
    def _hit(self):
        for t in self.gettags("current"):
            if t.startswith("id:"):
                return t[3:]
        return None

    def _click(self, e):
        self.focus_set()
        fid = self._hit()
        ctrl = bool(e.state & 0x4) or (self.mac and bool(e.state & 0x8))
        shift = bool(e.state & 0x1)
        if fid is None:
            if not (ctrl or shift):
                self.set_selection(set())
            return
        ids = [i["id"] for i in self.items]
        if shift and self.anchor in ids:
            a, b = sorted((ids.index(self.anchor), ids.index(fid)))
            rng = set(ids[a:b + 1])
            self.set_selection(rng | self.sel if ctrl else rng)
        elif ctrl:
            self.set_selection(self.sel ^ {fid})
            self.anchor = fid
        else:
            self.set_selection({fid})
            self.anchor = fid

    def _dbl(self, e):
        fid = self._hit()
        if fid:
            self.set_selection({fid})
            self.on_open(fid)

    def _menu(self, e):
        fid = self._hit()
        if fid is None:
            return
        if fid not in self.sel:
            self.set_selection({fid})
            self.anchor = fid
        self.on_menu(fid, e.x_root, e.y_root)

    def _bind_wheel(self, _):
        self.bind_all("<MouseWheel>", self._wheel)
        self.bind_all("<Button-4>", lambda e: self.yview_scroll(-3, "units"))
        self.bind_all("<Button-5>", lambda e: self.yview_scroll(3, "units"))

    def _unbind_wheel(self, _):
        for b in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            self.unbind_all(b)

    def _wheel(self, e):
        d = e.delta
        self.yview_scroll(int(-d / 120) if abs(d) >= 120 else (-1 if d > 0 else 1), "units")
