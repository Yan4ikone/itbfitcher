import os
import tkinter as tk
from tkinter import ttk


class ResultWindow(tk.Toplevel):
    """Modern summary window shown after processing."""

    BG = "#f5f7fb"
    CARD = "#ffffff"
    TEXT = "#182230"
    MUTED = "#687386"
    BORDER = "#e3e8f0"
    PRIMARY = "#2563eb"
    SUCCESS = "#16a34a"
    WARNING = "#d97706"
    DANGER = "#dc2626"

    def __init__(self, parent, *, total=0, processed=0, found=0,
                 not_found=0, errors=0, cached=0, elapsed=None,
                 output_path=None, marketplace=None):
        super().__init__(parent)
        self.output_path = output_path
        self.title("Результаты обработки — ITB FITCHER")
        self.geometry("900x650")
        self.minsize(780, 560)
        self.transient(parent)
        self.grab_set()
        self.configure(bg=self.BG)

        self._configure_styles()
        self._build(
            total=total,
            processed=processed,
            found=found,
            not_found=not_found,
            errors=errors,
            cached=cached,
            elapsed=elapsed,
            marketplace=marketplace,
        )

    def _configure_styles(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure("TFrame", background=self.BG)
        style.configure("Primary.TButton", font=("Segoe UI", 10, "bold"),
                        padding=(18, 11), foreground="white",
                        background=self.PRIMARY, borderwidth=0)
        style.map("Primary.TButton", background=[("active", "#1d4ed8")])
        style.configure("Secondary.TButton", font=("Segoe UI", 10), padding=(14, 10))

    def _card(self, parent):
        return tk.Frame(parent, bg=self.CARD,
                        highlightbackground=self.BORDER,
                        highlightthickness=1, bd=0)

    @staticmethod
    def _safe_int(value):
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    def _build(self, *, total, processed, found, not_found, errors,
               cached, elapsed, marketplace):
        total = self._safe_int(total)
        processed = self._safe_int(processed)
        found = self._safe_int(found)
        not_found = self._safe_int(not_found)
        errors = self._safe_int(errors)
        cached = self._safe_int(cached)

        success_rate = (found / total * 100) if total else 0

        outer = tk.Frame(self, bg=self.BG)
        outer.pack(fill="both", expand=True, padx=28, pady=24)

        header = tk.Frame(outer, bg=self.BG)
        header.pack(fill="x", pady=(0, 20))

        left = tk.Frame(header, bg=self.BG)
        left.pack(side="left")
        tk.Label(left, text="Результаты обработки", bg=self.BG, fg=self.TEXT,
                 font=("Segoe UI", 23, "bold")).pack(anchor="w")
        subtitle = "Обработка завершена"
        if marketplace:
            subtitle += f" • {marketplace}"
        tk.Label(left, text=subtitle, bg=self.BG, fg=self.MUTED,
                 font=("Segoe UI", 10)).pack(anchor="w", pady=(3, 0))

        badge_bg = "#eaf7ee" if errors == 0 else "#fff4df"
        badge_fg = self.SUCCESS if errors == 0 else self.WARNING
        tk.Label(header, text="✓  Успешно" if errors == 0 else "⚠  Есть ошибки",
                 bg=badge_bg, fg=badge_fg, font=("Segoe UI", 10, "bold"),
                 padx=14, pady=7).pack(side="right")

        # Main success card
        card = self._card(outer)
        card.pack(fill="x", pady=(0, 14))
        content = tk.Frame(card, bg=self.CARD)
        content.pack(fill="x", padx=22, pady=20)

        tk.Label(content, text=f"{success_rate:.1f}%", bg=self.CARD, fg=self.PRIMARY,
                 font=("Segoe UI", 34, "bold")).pack(anchor="w")
        tk.Label(content, text="успешно найдено и обработано", bg=self.CARD,
                 fg=self.MUTED, font=("Segoe UI", 10)).pack(anchor="w")

        bar_bg = tk.Frame(content, bg="#e8edf5", height=12)
        bar_bg.pack(fill="x", pady=(14, 6))
        bar_bg.pack_propagate(False)
        fill_width = max(0.0, min(success_rate, 100.0)) / 100.0
        fill = tk.Frame(bar_bg, bg=self.PRIMARY, height=12)
        fill.place(relx=0, rely=0, relwidth=fill_width, relheight=1)
        tk.Label(content, text=f"{found:,} из {total:,} позиций", bg=self.CARD,
                 fg=self.MUTED, font=("Segoe UI", 9)).pack(anchor="w")

        # Metrics
        metrics = tk.Frame(outer, bg=self.BG)
        metrics.pack(fill="x", pady=(0, 14))
        for i in range(5):
            metrics.columnconfigure(i, weight=1)

        values = [
            ("Всего", total, self.TEXT),
            ("Обработано", processed, self.SUCCESS),
            ("Из кеша", cached, self.PRIMARY),
            ("Не найдено", not_found, self.WARNING),
            ("Ошибки", errors, self.DANGER if errors else self.TEXT),
        ]
        for i, (caption, value, fg) in enumerate(values):
            c = self._card(metrics)
            c.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 5 if i < 4 else 0))
            tk.Label(c, text=f"{value:,}", bg=self.CARD, fg=fg,
                     font=("Segoe UI", 18, "bold")).pack(anchor="w", padx=14, pady=(13, 0))
            tk.Label(c, text=caption, bg=self.CARD, fg=self.MUTED,
                     font=("Segoe UI", 9)).pack(anchor="w", padx=14, pady=(0, 13))

        # Details
        details = self._card(outer)
        details.pack(fill="x", pady=(0, 14))
        d = tk.Frame(details, bg=self.CARD)
        d.pack(fill="x", padx=20, pady=15)

        tk.Label(d, text="ДЕТАЛИ", bg=self.CARD, fg=self.MUTED,
                 font=("Segoe UI", 8, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))

        elapsed_text = "—"
        if elapsed is not None:
            try:
                seconds = float(elapsed)
                if seconds >= 60:
                    elapsed_text = f"{int(seconds // 60)} мин {int(seconds % 60)} сек"
                else:
                    elapsed_text = f"{seconds:.1f} сек"
            except (TypeError, ValueError):
                elapsed_text = str(elapsed)

        details_values = [
            ("Время обработки", elapsed_text),
            ("Средняя скорость", self._speed_text(processed, elapsed)),
        ]
        for row, (caption, value) in enumerate(details_values, start=1):
            tk.Label(d, text=caption, bg=self.CARD, fg=self.MUTED,
                     font=("Segoe UI", 9)).grid(row=row, column=0, sticky="w", padx=(0, 30), pady=2)
            tk.Label(d, text=value, bg=self.CARD, fg=self.TEXT,
                     font=("Segoe UI", 9, "bold")).grid(row=row, column=1, sticky="w", pady=2)

        # Buttons
        buttons = tk.Frame(outer, bg=self.BG)
        buttons.pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Закрыть", command=self.destroy,
                   style="Secondary.TButton").pack(side="right")
        if self.output_path:
            ttk.Button(buttons, text="Открыть папку с результатом",
                       command=self.open_output_folder,
                       style="Primary.TButton").pack(side="right", padx=8)

    @staticmethod
    def _speed_text(processed, elapsed):
        try:
            seconds = float(elapsed)
            if seconds <= 0:
                return "—"
            return f"{processed / seconds:.2f} поз./сек"
        except (TypeError, ValueError, ZeroDivisionError):
            return "—"

    def open_output_folder(self):
        if not self.output_path:
            return
        folder = os.path.dirname(os.path.abspath(self.output_path))
        try:
            os.startfile(folder)
        except AttributeError:
            pass