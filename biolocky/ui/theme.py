"""Design tokens. Solid, warm surfaces with hairline borders and no gradients or glass:
classic-Mac restraint with iOS-style rounded grouped lists."""
import customtkinter as ctk
import tkinter.font as tkfont

TOK = {  # (light, dark)
    "bg":     ("#ECEAE6", "#1C1C1E"),
    "side":   ("#DFDCD6", "#252527"),
    "card":   ("#FBFAF8", "#2C2C2E"),
    "field":  ("#FFFFFF", "#1F1F21"),
    "line":   ("#C6C2BA", "#3F3F43"),
    "sel":    ("#CDC9C1", "#3A3A3E"),
    "text":   ("#1D1D1F", "#F2F2F7"),
    "muted":  ("#6B6B70", "#9A9AA0"),
    "accent": ("#2D6CDF", "#4A8CF0"),
    "accent_h": ("#2459BC", "#6AA0F5"),
    "danger": ("#C4352B", "#EE6A5F"),
    "toast":  ("#2B2B2D", "#EDEDED"),
    "toast_t": ("#FFFFFF", "#111111"),
}


def idx():
    return 1 if ctk.get_appearance_mode() == "Dark" else 0


def col(name):
    return TOK[name][idx()]


def pick_family(root):
    have = set(tkfont.families(root))
    for f in ("SF Pro Text", "Lucida Grande", "Helvetica Neue", "Segoe UI", "Helvetica", "Arial"):
        if f in have:
            return f
    return "TkDefaultFont"


class Fonts:
    def __init__(self, root):
        fam = self.family = pick_family(root)
        F = lambda size, w="normal": ctk.CTkFont(family=fam, size=size, weight=w)
        self.body, self.small, self.bold = F(13), F(11), F(13, "bold")
        self.h1, self.h2, self.big = F(20, "bold"), F(15, "bold"), F(26, "bold")
