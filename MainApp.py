# ITB FITCHER — modern GUI v2.0
# pyinstaller --clean MainApp.spec

import os
import sys
import shutil
import threading
import time
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

from core.app_controller import AppController
from learning.manual import ManualTeacher
from learning.runtime import LearningRuntime
from learning.learning_window import LearningWindow
from result_window import ResultWindow

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")


# ============================================================
# Helpers
# ============================================================

def create_output_from_template(input_path):
    base_dir = os.path.dirname(os.path.abspath(sys.argv[0]))
    template_path = os.path.join(base_dir, "Шаблон.xlsm")
    if not os.path.exists(template_path):
        raise Exception(f"Шаблон.xlsm не найден в папке: {base_dir}")
    base, _ = os.path.splitext(input_path)
    output_path = f"{base}_RESULT.xlsm"
    shutil.copy(template_path, output_path)
    return output_path


def make_rule_hint(product_name):
    words = product_name.lower().split()
    if len(words) == 1:
        word = words[0]
        return f'r"{word[:-1] if len(word) > 5 else word}"'
    return " + ".join(f'r"{w[:5]}"' for w in words)


def make_category_rule(product_name):
    words = product_name.lower().split()
    if len(words) < 2:
        return ""
    pattern = ".*".join(w[:5] for w in words if len(w) >= 4)
    return f'r"{pattern}": "{product_name}",'


class App:
    BG = "#f5f7fb"
    CARD = "#ffffff"
    TEXT = "#182230"
    MUTED = "#687386"
    BORDER = "#e3e8f0"
    PRIMARY = "#2563eb"
    PRIMARY_DARK = "#1d4ed8"
    SUCCESS = "#16a34a"
    WARNING = "#d97706"
    DANGER = "#dc2626"

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Кодировщик")
        self.root.geometry("1180x780")
        self.root.minsize(980, 680)
        self.root.configure(bg=self.BG)

        self.controller = AppController()
        self.selected_file = {"path": None}
        self.current_processor = {"instance": None}

        self.progress_var = tk.DoubleVar(value=0)
        self.status_var = tk.StringVar(value="Готов к работе")
        self.file_var = tk.StringVar(value="Файл не выбран")
        self.stats = {
            "total": tk.StringVar(value="0"),
            "processed": tk.StringVar(value="0"),
            "remaining": tk.StringVar(value="0"),
            "found": tk.StringVar(value="0"),
            "not_found": tk.StringVar(value="0"),
        }
        self.skip_filled_var = tk.BooleanVar(value=True)

        self._configure_styles()
        self._build()
        self.processing_started_at = None

    # ========================================================
    # Styling
    # ========================================================

    def _configure_styles(self):
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        style.configure("TFrame", background=self.BG)
        style.configure("Card.TFrame", background=self.CARD)
        style.configure(
            "TLabel",
            background=self.BG,
            foreground=self.TEXT,
            font=("Segoe UI", 10),
        )
        style.configure(
            "Muted.TLabel",
            background=self.BG,
            foreground=self.MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Title.TLabel",
            background=self.BG,
            foreground=self.TEXT,
            font=("Segoe UI", 23, "bold"),
        )
        style.configure(
            "Subtitle.TLabel",
            background=self.BG,
            foreground=self.MUTED,
            font=("Segoe UI", 10),
        )
        style.configure(
            "CardTitle.TLabel",
            background=self.CARD,
            foreground=self.TEXT,
            font=("Segoe UI", 10, "bold"),
        )
        style.configure(
            "Metric.TLabel",
            background=self.CARD,
            foreground=self.TEXT,
            font=("Segoe UI", 21, "bold"),
        )
        style.configure(
            "MetricCaption.TLabel",
            background=self.CARD,
            foreground=self.MUTED,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Primary.TButton",
            font=("Segoe UI", 10, "bold"),
            padding=(18, 11),
            foreground="white",
            background=self.PRIMARY,
            borderwidth=0,
        )
        style.map("Primary.TButton", background=[("active", self.PRIMARY_DARK)])
        style.configure(
            "Secondary.TButton",
            font=("Segoe UI", 10),
            padding=(14, 10),
        )
        style.configure(
            "Danger.TButton",
            font=("Segoe UI", 10),
            padding=(14, 10),
            foreground=self.DANGER,
        )
        style.configure(
            "Modern.Horizontal.TProgressbar",
            troughcolor="#e8edf5",
            background=self.PRIMARY,
            bordercolor="#e8edf5",
            lightcolor=self.PRIMARY,
            darkcolor=self.PRIMARY,
            thickness=12,
        )
        style.configure(
            "TCheckbutton",
            background=self.CARD,
            foreground=self.TEXT,
            font=("Segoe UI", 9),
        )

    # ========================================================
    # UI
    # ========================================================

    def _build(self):
        outer = ttk.Frame(self.root)
        outer.pack(fill="both", expand=True, padx=28, pady=24)

        self._build_header(outer)
        self._build_file_card(outer)
        self._build_metrics(outer)
        self._build_progress_card(outer)
        self._build_actions_card(outer)
        self._build_log_card(outer)

    def _build_header(self, parent):
        header = ttk.Frame(parent)
        header.pack(fill="x", pady=(0, 18))

        left = ttk.Frame(header)
        left.pack(side="left")

        ttk.Label(left, text="Кодировщик", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            left,
            text="Автоматическая обработка товаров и определение ТН ВЭД",
            style="Subtitle.TLabel",
        ).pack(anchor="w", pady=(3, 0))

        status = tk.Label(
            header,
            textvariable=self.status_var,
            bg="#eaf7ee",
            fg=self.SUCCESS,
            font=("Segoe UI", 10, "bold"),
            padx=14,
            pady=7,
        )
        status.pack(side="right", pady=4)
        self.status_badge = status

    def _card(self, parent):
        frame = tk.Frame(
            parent,
            bg=self.CARD,
            highlightbackground=self.BORDER,
            highlightthickness=1,
            bd=0,
        )
        frame.pack(fill="x", pady=(0, 12))
        return frame

    def _build_file_card(self, parent):
        card = self._card(parent)
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=18, pady=15)

        tk.Label(
            body, text="ВХОДНОЙ ФАЙЛ", bg=self.CARD, fg=self.MUTED,
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")

        row = tk.Frame(body, bg=self.CARD)
        row.pack(fill="x", pady=(7, 0))

        tk.Label(
            row, textvariable=self.file_var, bg=self.CARD, fg=self.TEXT,
            font=("Segoe UI", 11, "bold"), anchor="w"
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            row, text="Выбрать Excel", command=self.choose_file,
            style="Secondary.TButton"
        ).pack(side="right")

    def _build_metrics(self, parent):
        wrapper = ttk.Frame(parent)
        wrapper.pack(fill="x", pady=(0, 12))
        for i in range(5):
            wrapper.columnconfigure(i, weight=1)

        items = [
            ("total", "Всего"),
            ("processed", "Обработано"),
            ("remaining", "Осталось"),
            ("found", "Найдено"),
            ("not_found", "Не найдено"),
        ]

        for i, (key, caption) in enumerate(items):
            card = tk.Frame(
                wrapper, bg=self.CARD,
                highlightbackground=self.BORDER,
                highlightthickness=1,
            )
            card.grid(row=0, column=i, sticky="nsew", padx=(0 if i == 0 else 5, 5 if i < 4 else 0))
            tk.Label(
                card, textvariable=self.stats[key], bg=self.CARD,
                fg=self.TEXT, font=("Segoe UI", 20, "bold")
            ).pack(anchor="w", padx=14, pady=(13, 0))
            tk.Label(
                card, text=caption, bg=self.CARD, fg=self.MUTED,
                font=("Segoe UI", 9)
            ).pack(anchor="w", padx=14, pady=(0, 13))

    def _build_progress_card(self, parent):
        card = self._card(parent)
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=18, pady=15)

        top = tk.Frame(body, bg=self.CARD)
        top.pack(fill="x")
        tk.Label(
            top, text="ПРОГРЕСС", bg=self.CARD, fg=self.MUTED,
            font=("Segoe UI", 8, "bold")
        ).pack(side="left")
        self.percent_label = tk.Label(
            top, text="0%", bg=self.CARD, fg=self.TEXT,
            font=("Segoe UI", 10, "bold")
        )
        self.percent_label.pack(side="right")

        ttk.Progressbar(
            body, variable=self.progress_var, maximum=100,
            style="Modern.Horizontal.TProgressbar"
        ).pack(fill="x", pady=(9, 7))

        self.detail_label = tk.Label(
            body, text="Ожидание запуска", bg=self.CARD, fg=self.MUTED,
            font=("Segoe UI", 9), anchor="w"
        )
        self.detail_label.pack(fill="x")

    def _build_actions_card(self, parent):
        card = self._card(parent)
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="x", padx=18, pady=15)

        tk.Label(
            body, text="УПРАВЛЕНИЕ", bg=self.CARD, fg=self.MUTED,
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w")

        row = tk.Frame(body, bg=self.CARD)
        row.pack(fill="x", pady=(9, 0))

        ttk.Button(
            row, text="▶  Запустить обработку", command=self.start_processing,
            style="Primary.TButton"
        ).pack(side="left")
        ttk.Button(
            row, text="Пауза", command=self.pause_ozon_auto,
            style="Secondary.TButton"
        ).pack(side="left", padx=7)
        ttk.Button(
            row, text="Остановить", command=self.stop_ozon_auto,
            style="Danger.TButton"
        ).pack(side="left")

        ttk.Button(
            row, text="Обучение", command=self.start_learning,
            style="Secondary.TButton"
        ).pack(side="right")

        tk.Checkbutton(
            body,
            text="Пропускать товары, у которых код уже заполнен",
            variable=self.skip_filled_var,
            bg=self.CARD,
            activebackground=self.CARD,
            fg=self.MUTED,
            selectcolor=self.CARD,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(11, 0))

    def _build_log_card(self, parent):
        card = self._card(parent)
        body = tk.Frame(card, bg=self.CARD)
        body.pack(fill="both", expand=True, padx=18, pady=15)

        tk.Label(
            body, text="ПОСЛЕДНИЕ СОБЫТИЯ", bg=self.CARD, fg=self.MUTED,
            font=("Segoe UI", 8, "bold")
        ).pack(anchor="w", pady=(0, 8))

        self.log_text = ScrolledText(
            body,
            height=7,
            font=("Consolas", 9),
            bg="#fbfcfe",
            fg="#334155",
            relief="flat",
            borderwidth=0,
            insertbackground=self.TEXT,
        )
        self.log_text.pack(fill="both", expand=True)

    # ========================================================
    # Helpers / callbacks
    # ========================================================

    def append_log(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def gui_log(self, message):
        self.root.after(0, lambda: self.append_log(str(message)))

    def set_status(self, text):
        def update():
            self.status_var.set(text)
            if "ошиб" in text.lower():
                self.status_badge.configure(bg="#fdecec", fg=self.DANGER)
            elif "пауза" in text.lower():
                self.status_badge.configure(bg="#fff4df", fg=self.WARNING)
            elif "готов" in text.lower() or "продолж" in text.lower():
                self.status_badge.configure(bg="#eaf7ee", fg=self.SUCCESS)
            else:
                self.status_badge.configure(bg="#eaf1ff", fg=self.PRIMARY)
        self.root.after(0, update)

    def update_progress(self, total, processed):
        percent = 0 if total == 0 else round(processed / total * 100, 1)
        self.root.after(0, lambda: self.progress_var.set(percent))
        self.root.after(0, lambda: self.percent_label.config(text=f"{percent}%"))
        self.root.after(0, lambda: self.detail_label.config(text=f"Обработано {processed} из {total}"))

    def update_stats(self, total, processed, found, not_found):
        remaining = total - processed
        values = {
            "total": total,
            "processed": processed,
            "remaining": remaining,
            "found": found,
            "not_found": not_found,
        }
        for key, value in values.items():
            self.root.after(0, lambda k=key, v=value: self.stats[k].set(str(v)))
        self.update_progress(total, processed)

    # ========================================================
    # File / processing
    # ========================================================

    def choose_file(self):
        path = filedialog.askopenfilename(
            title="Выберите Excel файл",
            filetypes=[("Excel files", "*.xlsx *.xlsm"), ("All files", "*.*")],
        )
        if not path:
            return
        self.selected_file["path"] = path
        self.file_var.set(os.path.basename(path))
        self.set_status("Файл выбран")
        self.append_log(f"✓ Выбран файл: {os.path.basename(path)}")

    def _require_file(self):
        if not self.selected_file["path"]:
            messagebox.showwarning("Файл не выбран", "Сначала выберите Excel-файл.")
            return False
        return True

    def start_processing(self):
        self.processing_started_at = time.perf_counter()
        if not self._require_file():
            return
        self.progress_var.set(0)
        self.percent_label.config(text="0%")
        self.detail_label.config(text="Запуск обработки...")
        self.set_status("Запуск...")
        threading.Thread(target=self.start_ozon_auto(), daemon=True).start()

    def run_processing_with_norm(self):
        try:
            output_path = self.controller.process(
                self.selected_file["path"],
                logger=self.gui_log,
                progress_callback=self.update_progress,
            )
            elapsed = time.perf_counter() - self.processing_started_at

            report_path = os.path.join(
                os.path.dirname(output_path),
                "CLASSIFICATION_REPORT.xlsx"
            )

            total = 0
            found = 0
            not_found = 0

            try:
                if os.path.exists(report_path):
                    report_df = pd.read_excel(report_path)

                    total = len(report_df)

                    if "Код" in report_df.columns:
                        codes = report_df["Код"].fillna("").astype(str).str.strip()
                        found = int(((codes != "") & (codes != "0")).sum())
                        not_found = total - found
            except Exception as report_error:
                self.gui_log(
                    f"⚠ Не удалось прочитать статистику: {report_error}"
                )

            self.root.after(
                0,
                lambda: ResultWindow(
                    self.root,
                    total=total,
                    processed=total,
                    found=found,
                    not_found=not_found,
                    errors=0,
                    cached=0,
                    elapsed=elapsed,
                    output_path=output_path,
                )
            )
            self.set_status("Готово")
            self.root.after(
                0,
                lambda: messagebox.showinfo(
                    "Готово",
                    f"Файл успешно обработан:\n{os.path.basename(output_path)}",
                ),
            )
            self.root.after(0, lambda: os.startfile(os.path.dirname(output_path)))
        except Exception as e:
            self.set_status("Ошибка")
            error_message = str(e)
            self.gui_log(f"✗ Ошибка: {error_message}")
            self.root.after(
                0,
                lambda msg=error_message: messagebox.showerror("Ошибка", msg),
            )

    # ========================================================
    # Ozon auto controls — kept for compatibility
    # ========================================================

    def start_ozon_auto(self):
        if not self._require_file():
            return
        self.progress_var.set(0)
        self.percent_label.config(text="0%")
        self.set_status("Запуск Ozon...")
        threading.Thread(target=self.run_ozon_auto_thread, daemon=True).start()

    def run_ozon_auto_thread(self):
        try:
            processor = self.controller.create_ozon_processor(
                self.selected_file["path"],
                logger=self.gui_log,
                stats_callback=self.update_stats,
                skip_filled=self.skip_filled_var.get(),
            )
            self.current_processor["instance"] = processor
            processor.run()
            self.current_processor["instance"] = None
            self.set_status("Готово")
            self.root.after(0, lambda: messagebox.showinfo("Готово", "Автообработка завершена"))
        except Exception as e:
            self.current_processor["instance"] = None
            self.set_status("Ошибка")
            error_message = str(e)
            self.gui_log(f"✗ Ошибка Ozon: {error_message}")
            self.root.after(
                0,
                lambda msg=error_message: messagebox.showerror("Ошибка", msg),
            )

    def stop_ozon_auto(self):
        processor = self.current_processor.get("instance")
        if processor:
            processor.stop()
            self.set_status("Остановлено")
            self.gui_log("■ Обработка остановлена пользователем")

    def pause_ozon_auto(self):
        processor = self.current_processor.get("instance")
        if processor is None:
            return
        if getattr(processor, "pause_requested", False):
            processor.resume()
            self.set_status("Продолжено")
            self.gui_log("▶ Обработка продолжена")
        else:
            processor.pause()
            self.set_status("Пауза")
            self.gui_log("Ⅱ Обработка поставлена на паузу")

    # ========================================================
    # Learning
    # ========================================================

    def start_learning(self):
        if not self._require_file():
            return

        result_file = (
            self.selected_file["path"]
            .replace(".xlsx", "_RESULT.xlsx")
            .replace(".xlsm", "_RESULT.xlsm")
        )

        if not os.path.exists(result_file):
            messagebox.showwarning(
                "Результат не найден",
                "Сначала выполните обработку файла и убедитесь, что RESULT-файл создан.",
            )
            return

        try:
            teacher = ManualTeacher()
            teacher.learn_result_file(result_file)
            runtime = LearningRuntime()
            report = runtime.analyze()
            window = LearningWindow(self.root, report, runtime)
            self.root.wait_window(window)
            if window.applied:
                runtime.mark_learning_processed(report.processed_cards)
                self.gui_log("✓ Обучение сохранено")
        except Exception as e:
            self.set_status("Ошибка")
            self.gui_log(f"✗ Ошибка обучения: {e}")
            messagebox.showerror("Ошибка обучения", str(e))

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()