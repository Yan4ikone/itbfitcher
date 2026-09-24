# ITB FITCHER — modern GUI v3.0


import sys

# ==================================================================
# ВАЖНО: sys.dont_write_bytecode = True ДО любых остальных импортов.
#
# ИСТОРИЯ ПРАВКИ: dictionaries/products.py и dictionaries/
# all_dictionaries.py перезаписываются на диске прямо во время работы
# программы (обучение, редактор словарей - см. learning/builder.py,
# learning/dictionary_editor.py), и весь механизм "самолечения" из
# products-dict-gradation-audit.md держится на инварианте "перед
# записью читаем состояние заново с диска через importlib.reload -
# тогда ничьи параллельные правки не воскрешаются и не теряются".
#
# Обнаружено при тестировании нового редактора dropdown-вариантов:
# стандартный .pyc-кэш Python использует mtime файла, УСЕЧЁННЫЙ ДО
# ЦЕЛОЙ СЕКУНДЫ (это поведение CPython по умолчанию, не особенность
# этой машины) - если products.py перезаписывается два и более раз
# в пределах ОДНОЙ секунды (что для быстрых последовательных правок,
# например пакетного применения нескольких исправлений подряд,
# реалистично), importlib.reload() может решить, что закэшированный
# .pyc всё ещё актуален, и вернуть СТАРОЕ содержимое, несмотря на то
# что на диске уже лежит новое - следующая правка тогда применяется
# поверх устаревших данных, и часть более ранних изменений тихо
# теряется. Синтетически воспроизведено: 3 записи products.py подряд
# (с разным содержимым) в пределах одной секунды - reload() каждый
# раз возвращал СОДЕРЖИМОЕ ПЕРВОЙ ЗАПИСИ, пока не отключили запись
# .pyc; после этого reload() корректно видел каждое изменение.
#
# sys.dont_write_bytecode = True запрещает Python вообще писать/
# использовать .pyc-кэш в этом процессе - для настольного приложения
# цена этого исчезающе мала (чуть медленнее самый первый импорт при
# запуске), а весь класс "тихого отката" правок исчезает.
# ==================================================================
sys.dont_write_bytecode = True

import os
import shutil
import threading
import time
import pandas as pd
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import ScrolledText

from core.app_controller import AppController
from core.ai_settings import is_image_ai_enabled, set_image_ai_enabled
from learning.archive_importer import import_archive_files
from learning.manual import ManualTeacher
from learning.runtime import LearningRuntime
from learning.learning_window import LearningWindow
from result_window import ResultWindow
from server_split import (
    split_by_servers,
    merge_server_results,
    find_rows_with_url,
)
import openpyxl

if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdin is None:
    sys.stdin = open(os.devnull, "r")

# ==================================================================
# ФАЙЛОВОЕ ЛОГИРОВАНИЕ ОШИБОК (logs/errors_YYYY-MM-DD.log)
#
# ВАЖНО: строки выше (sys.stdout is None -> devnull) означают, что в
# windowed/noconsole-сборке (без консоли) ЛЮБОЙ print() в проекте
# уходит в никуда - именно поэтому ошибки ИИ-движка по картинке
# (engines/*_image_description_engine.py) и ошибка инициализации
# image_processor (engines/decision_engine.py) были невидимы вообще
# нигде ("ИИ не работает, куча ошибок" без единой видимой ошибки).
# setup_logging() пишет их дополнительно в файл на диске - см.
# подробное объяснение в utils/app_logging.py. Вызывается здесь как
# можно раньше - до импорта AppController/OzonAutoProcessor и т.п.,
# которые могут что-то залогировать уже при первом использовании.
# ==================================================================
from utils.app_logging import setup_logging

setup_logging()


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


class SplitDialog(tk.Toplevel):
    """Окно настройки разделения файла по машинам/серверам -
    количество машин задаётся свободно, количество строк на каждую
    машину можно скорректировать вручную (по умолчанию - поровну)."""

    def __init__(self, parent, app, total_rows):
        super().__init__(parent)
        self.app = app
        self.total_rows = total_rows
        self.dest_dir = None

        self.title("Разделить по серверам")
        self.configure(bg=app.BG)
        self.transient(parent)
        self.grab_set()

        # ------------------------------------------------------------
        # ИСТОРИЯ ПРАВКИ: раньше окно имело фиксированный размер
        # 420x520 и НЕ подстраивалось под содержимое. Список строк
        # "Машина N:" рисовался в обычном Frame без прокрутки - при
        # небольшом количестве машин (5-10) это работало незаметно,
        # но при вводе, например, 100 машин список требовал ~3000px
        # высоты, а окно оставалось 520px. Из-за этого "Осталось
        # нераспределённых", выбор папки и кнопка "Разделить" (они
        # были упакованы В КОНЦЕ, ПОСЛЕ списка строк) физически
        # уезжали далеко за пределы видимой области окна, а resizable
        # окна (изменение размера мышью) всё равно не помогало - ни
        # один экран не показал бы 3000px высоты целиком.
        #
        # Фикс: (1) окно теперь явно resizable и стартует с разумного
        # размера, подобранного под высоту экрана; (2) список строк
        # "Машина N:" вынесен в прокручиваемую область (Canvas +
        # Scrollbar), поддерживающую колесо мыши; (3) "Осталось
        # нераспределённых", выбор папки и кнопка "Разделить"
        # упакованы В ЗАКРЕПЛЁННЫЙ нижний блок ДО прокручиваемой
        # области (side="bottom") - теперь они всегда видны и
        # доступны, сколько бы машин ни было указано.
        # ------------------------------------------------------------
        self.resizable(True, True)
        screen_h = self.winfo_screenheight()
        win_h = max(420, min(640, screen_h - 120))
        self.geometry(f"460x{win_h}")
        self.minsize(400, 340)

        self.entry_vars = []

        tk.Label(
            self, text=f"Всего строк: {total_rows}",
            bg=app.BG, fg=app.TEXT, font=("Segoe UI", 12, "bold"),
        ).pack(pady=(15, 5))

        n_row = tk.Frame(self, bg=app.BG)
        n_row.pack(pady=5)

        tk.Label(
            n_row, text="Количество машин:",
            bg=app.BG, fg=app.TEXT, font=("Segoe UI", 10),
        ).pack(side="left", padx=(0, 8))

        self.n_var = tk.StringVar(value="5")
        n_entry = tk.Entry(
            n_row, textvariable=self.n_var, width=5,
            font=("Segoe UI", 10),
        )
        n_entry.pack(side="left")

        ttk.Button(
            n_row, text="Обновить", command=self._rebuild_rows,
        ).pack(side="left", padx=8)

        # Закреплённый нижний блок - упаковывается ПЕРВЫМ, side="bottom",
        # поэтому прокручиваемый список строк ниже никогда не может
        # вытеснить его за пределы окна.
        bottom = tk.Frame(self, bg=app.BG)
        bottom.pack(side="bottom", fill="x")

        self.remaining_label = tk.Label(
            bottom, text="", bg=app.BG, fg=app.TEXT,
            font=("Segoe UI", 11, "bold"),
        )
        self.remaining_label.pack(pady=5)

        dest_row = tk.Frame(bottom, bg=app.BG)
        dest_row.pack(pady=5, fill="x", padx=15)

        self.dest_var = tk.StringVar(value="Папка не выбрана")

        tk.Label(
            dest_row, textvariable=self.dest_var,
            bg=app.BG, fg=app.MUTED, font=("Segoe UI", 9),
            anchor="w",
        ).pack(side="left", fill="x", expand=True)

        ttk.Button(
            dest_row, text="Папка...", command=self._choose_dest,
        ).pack(side="right")

        ttk.Button(
            bottom, text="Разделить", command=self._do_split,
            style="Primary.TButton",
        ).pack(pady=15, fill="x", padx=15)

        # Прокручиваемая область со строками машин (занимает всё
        # оставшееся место над закреплённым нижним блоком).
        scroll_area = tk.Frame(self, bg=app.BG)
        scroll_area.pack(side="top", fill="both", expand=True, padx=15, pady=10)

        rows_canvas = tk.Canvas(scroll_area, bg=app.BG, highlightthickness=0)
        rows_vsb = ttk.Scrollbar(
            scroll_area, orient="vertical", command=rows_canvas.yview,
        )
        rows_canvas.configure(yscrollcommand=rows_vsb.set)
        rows_canvas.pack(side="left", fill="both", expand=True)
        rows_vsb.pack(side="right", fill="y")

        self.rows_frame = tk.Frame(rows_canvas, bg=app.BG)
        rows_window = rows_canvas.create_window(
            (0, 0), window=self.rows_frame, anchor="nw",
        )

        def _on_rows_configure(_event=None):
            rows_canvas.configure(scrollregion=rows_canvas.bbox("all"))

        def _on_canvas_configure(event):
            rows_canvas.itemconfigure(rows_window, width=event.width)

        self.rows_frame.bind("<Configure>", _on_rows_configure)
        rows_canvas.bind("<Configure>", _on_canvas_configure)

        def _on_mousewheel(event):
            rows_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

        def _bind_mousewheel(_event=None):
            rows_canvas.bind_all("<MouseWheel>", _on_mousewheel)

        def _unbind_mousewheel(_event=None):
            rows_canvas.unbind_all("<MouseWheel>")

        rows_canvas.bind("<Enter>", _bind_mousewheel)
        rows_canvas.bind("<Leave>", _unbind_mousewheel)
        # На случай, если курсор остался над списком в момент закрытия
        # окна (иначе "Leave" не наступит, и bind_all("<MouseWheel>")
        # останется висеть глобально на уже уничтоженный canvas).
        self.bind("<Destroy>", _unbind_mousewheel)

        self._rebuild_rows()

    def _rebuild_rows(self):
        for widget in self.rows_frame.winfo_children():
            widget.destroy()
        self.entry_vars = []

        try:
            n = max(1, int(self.n_var.get()))
        except ValueError:
            n = 1
            self.n_var.set("1")

        per_machine = self.total_rows // n
        extra = self.total_rows % n

        for i in range(n):
            count = per_machine + (1 if i < extra else 0)

            row = tk.Frame(self.rows_frame, bg=self.app.BG)
            row.pack(fill="x", pady=2)

            tk.Label(
                row, text=f"Машина {i + 1}:",
                bg=self.app.BG, fg=self.app.TEXT,
                width=12, anchor="w", font=("Segoe UI", 10),
            ).pack(side="left")

            var = tk.StringVar(value=str(count))
            var.trace_add("write", lambda *a: self._update_remaining())
            entry = tk.Entry(row, textvariable=var, width=8)
            entry.pack(side="left", padx=5)

            self.entry_vars.append(var)

        self._update_remaining()

    def _update_remaining(self):
        used = 0
        for var in self.entry_vars:
            try:
                used += int(var.get())
            except ValueError:
                pass

        remaining = self.total_rows - used

        self.remaining_label.config(
            text=f"Осталось нераспределённых: {remaining}",
            fg="#16a34a" if remaining == 0 else "#dc2626",
        )

    def _choose_dest(self):
        folder = filedialog.askdirectory(title="Куда сохранить файлы")
        if folder:
            self.dest_dir = folder
            self.dest_var.set(folder)

    def _do_split(self):
        try:
            counts = [int(var.get()) for var in self.entry_vars]
        except ValueError:
            messagebox.showerror(
                "Ошибка", "Количество строк должно быть числом.",
            )
            return

        if sum(counts) != self.total_rows:
            messagebox.showerror(
                "Ошибка",
                f"Сумма ({sum(counts)}) не совпадает с общим "
                f"числом строк ({self.total_rows}).",
            )
            return

        if any(c < 0 for c in counts):
            messagebox.showerror("Ошибка", "Количество не может быть отрицательным.")
            return

        dest_dir = self.dest_dir or os.path.join(
            os.path.dirname(self.app.selected_file["path"]),
            "распределено_по_серверам",
        )

        self.destroy()
        self.app.run_split(len(counts), counts, dest_dir)


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
        # Тумблер "Использовать ИИ по картинке" - начальное значение
        # читается из settings.json (core/ai_settings.py), чтобы при
        # следующем запуске программы сохранялось то, что куратор
        # выбрал в прошлый раз, а не сбрасывалось на дефолт.
        self.use_image_ai_var = tk.BooleanVar(value=is_image_ai_enabled())

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

        row2 = tk.Frame(body, bg=self.CARD)
        row2.pack(fill="x", pady=(7, 0))

        ttk.Button(
            row2, text="Разделить по серверам",
            command=self.open_split_dialog,
            style="Secondary.TButton"
        ).pack(side="left")
        ttk.Button(
            row2, text="Собрать с серверов",
            command=self.merge_from_servers,
            style="Secondary.TButton"
        ).pack(side="left", padx=7)
        ttk.Button(
            row2, text="Импорт архива",
            command=self.import_archive,
            style="Secondary.TButton"
        ).pack(side="left")

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

        tk.Checkbutton(
            body,
            text="Использовать ИИ по картинке (для спорных карточек)",
            variable=self.use_image_ai_var,
            command=self._on_toggle_image_ai,
            bg=self.CARD,
            activebackground=self.CARD,
            fg=self.MUTED,
            selectcolor=self.CARD,
            font=("Segoe UI", 9),
        ).pack(anchor="w", pady=(4, 0))

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

    def _on_toggle_image_ai(self):
        # Сохраняется сразу по клику (не по кнопке "Запустить") - в
        # settings.json, откуда его на каждой карточке читает
        # DecisionEngine.decide() (engines/decision_engine.py, шаг 7.5,
        # см. core/ai_settings.py). Действует сразу, в т.ч. на уже
        # запущенную пакетную обработку (воркеры перечитывают файл на
        # каждой карточке, а не один раз при старте).
        enabled = self.use_image_ai_var.get()
        set_image_ai_enabled(enabled)
        self.append_log(
            "ИИ по картинке: "
            + ("включено" if enabled else "выключено")
        )

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
    # Разделение по серверам / сборка результатов
    # ========================================================

    def open_split_dialog(self):
        if not self._require_file():
            return

        try:
            wb = openpyxl.load_workbook(self.selected_file["path"])
            rows = find_rows_with_url(wb.active)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл: {e}")
            return

        total = len(rows)

        if total == 0:
            messagebox.showwarning(
                "Нет строк",
                "В выбранном файле не найдено ни одной строки со ссылкой.",
            )
            return

        SplitDialog(self.root, self, total)

    def run_split(self, n, counts, dest_dir):
        try:
            paths = split_by_servers(
                self.selected_file["path"],
                n=n,
                output_dir=dest_dir,
                counts=counts,
                log=self.gui_log,
            )
            messagebox.showinfo(
                "Готово",
                f"Создано файлов: {len(paths)}\nПапка:\n{dest_dir}",
            )
            self.gui_log(f"✓ Разделено на {len(paths)} машин(ы)")
            try:
                os.startfile(dest_dir)
            except Exception:
                pass
        except Exception as e:
            self.gui_log(f"✗ Ошибка разделения: {e}")
            messagebox.showerror("Ошибка разделения", str(e))

    def merge_from_servers(self):
        if not self._require_file():
            return

        paths = filedialog.askopenfilenames(
            title="Выберите обработанные файлы со всех машин",
            filetypes=[("Excel files", "*.xlsx *.xlsm")],
        )

        if not paths:
            return

        base, ext = os.path.splitext(self.selected_file["path"])
        output_path = f"{base}_RESULT{ext}"

        if os.path.exists(output_path):
            if not messagebox.askyesno(
                "Файл уже существует",
                f"{os.path.basename(output_path)} уже существует. "
                "Перезаписать?",
            ):
                return

        try:
            merge_server_results(
                list(paths),
                output_path,
                # Файлы машин теперь содержат ТОЛЬКО свои строки (см.
                # server_split.py) - строки сопоставляются с исходным
                # файлом по ссылке, а не по номеру, поэтому сборке
                # нужен именно ОРИГИНАЛЬНЫЙ, ещё не делённый файл (тот
                # же self.selected_file["path"], который делили
                # кнопкой "Разделить по серверам") как основа со всеми
                # строками на местах.
                source_path=self.selected_file["path"],
                log=self.gui_log,
            )
            self.gui_log(f"✓ Результаты собраны: {output_path}")
            messagebox.showinfo(
                "Готово",
                f"Результаты собраны в файл:\n{output_path}\n\n"
                "Теперь можно нажать «Обучение», чтобы применить "
                "исправления локально.",
            )
        except Exception as e:
            self.gui_log(f"✗ Ошибка сборки: {e}")
            messagebox.showerror("Ошибка сборки", str(e))

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

    # ========================================================
    # Импорт архива ("Первичная проверка" - файлы, которые куратор
    # вёл ОТДЕЛЬНО от программы: исходное название, исправленное,
    # код ТН ВЭД). См. learning/archive_importer.py.
    # ========================================================

    def import_archive(self):

        paths = filedialog.askopenfilenames(
            title="Выберите архивные файлы «Первичная проверка»",
            filetypes=[("Excel files", "*.xlsx *.xlsm")],
        )

        if not paths:
            return

        if not messagebox.askyesno(
            "Импорт архива",
            f"Выбрано файлов: {len(paths)}.\n\n"
            "Строки, где куратор согласился с названием, будут "
            "применены к словарю сразу. Расхождения и спорные случаи "
            "(например, новое название совпадает с уже существующим "
            "алиасом другого товара) откроются на проверку в окне "
            "обучения, как обычно.\n\nПродолжить?",
        ):
            return

        self.set_status("Импорт архива...")

        try:
            result = import_archive_files(list(paths), dry_run=False)
        except Exception as e:
            self.set_status("Ошибка")
            self.gui_log(f"✗ Ошибка импорта архива: {e}")
            messagebox.showerror("Ошибка импорта архива", str(e))
            return

        self.set_status("Готово")
        self.gui_log("✓ Импорт архива завершён")
        self.gui_log(result.summary_text())

        review_report = result.discrepancy_report
        has_review_items = any((
            review_report.new_products,
            review_report.new_aliases,
            review_report.new_dropdown_variants,
            review_report.new_dropdown_candidates,
            review_report.new_patterns,
            review_report.new_dictionary_words,
        ))

        if has_review_items and result.discrepancy_runtime is not None:
            window = LearningWindow(
                self.root, review_report, result.discrepancy_runtime
            )
            self.root.wait_window(window)
            if window.applied:
                self.gui_log("✓ Проверенные расхождения из архива сохранены")

        messagebox.showinfo("Импорт архива", result.summary_text())

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    App().run()