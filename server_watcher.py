"""
Скрипт-сторож для сервера.

Логика: разделили файл на N машин ("Разделить по серверам" в
MainApp.py кладёт файлы вида "{имя}_machine_{N}.xlsx" в общую
сетевую папку) -> на каждом сервере запущен этот скрипт -> он сам
следит за входящей папкой, находит СВОЙ файл (по номеру машины),
забирает его, запускает обработку и кладёт результат в исходящую
папку. Человеку на сервере ничего нажимать не нужно.

Настройка (номер машины, папки) вводится один раз при первом
запуске и сохраняется в server_watcher_config.json рядом со
скриптом.
"""

import os
import re
import sys
import json
import shutil
import threading
import time
import traceback

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from core.app_controller import AppController

CONFIG_PATH = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])),
    "server_watcher_config.json",
)

LOCAL_WORK_DIR = os.path.join(
    os.path.dirname(os.path.abspath(sys.argv[0])),
    "server_work",
)

DEFAULT_POLL_INTERVAL = 10


# ================================================================
# КОНФИГ
# ================================================================

def load_config():

    if not os.path.exists(CONFIG_PATH):
        return {}

    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_config(config):

    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)


# ================================================================
# ПОИСК СВОЕГО ФАЙЛА
# ================================================================

def find_my_file(incoming_folder, machine_id):
    """Ищет файл вида "..._machine_{machine_id}.xlsx" во входящей
    папке - именно так называет файлы split_by_servers() в
    server_split.py. Регистр и порядок цифр не важны, но номер
    машины должен совпадать ЦЕЛИКОМ (не "12" при поиске "1")."""

    if not os.path.isdir(incoming_folder):
        return None

    pattern = re.compile(
        rf"_machine_{re.escape(str(machine_id))}\.xlsx$",
        re.IGNORECASE,
    )

    for name in os.listdir(incoming_folder):

        if pattern.search(name):
            return os.path.join(incoming_folder, name)

    return None


# ================================================================
# СТОРОЖ
# ================================================================

class ServerWatcher:

    def __init__(self, config, log, status, on_stats=None):
        self.config = config
        self.log = log
        self.status = status
        self.on_stats = on_stats
        self.running = False
        self.thread = None
        self.controller = AppController()
        self.current_processor = None

    def start(self):

        if self.running:
            return

        self.running = True

        self.thread = threading.Thread(
            target=self._loop,
            daemon=True,
        )

        self.thread.start()

        self.log("Сторож запущен")

    def stop(self):

        self.running = False

        if self.current_processor:
            try:
                self.current_processor.stop()
            except Exception:
                pass

        self.log("Сторож остановлен")

    def _loop(self):

        os.makedirs(LOCAL_WORK_DIR, exist_ok=True)

        while self.running:

            try:
                self._check_once()
            except Exception as e:
                self.log(f"✗ Ошибка сторожа: {e}")
                traceback.print_exc()

            for _ in range(int(self.config.get("poll_interval", DEFAULT_POLL_INTERVAL))):

                if not self.running:
                    return

                time.sleep(1)

    def _check_once(self):

        os.makedirs(LOCAL_WORK_DIR, exist_ok=True)

        incoming = self.config["incoming_folder"]
        machine_id = self.config["machine_id"]

        self.status(f"Ожидание файла (машина {machine_id})...")

        found_path = find_my_file(incoming, machine_id)

        if not found_path:
            return

        file_name = os.path.basename(found_path)

        self.log(f"Найден файл: {file_name}")

        # ------------------------------------------------------
        # Забираем файл СЕБЕ (move, не copy) - это сразу "снимает"
        # его из входящей папки, чтобы при перезапуске/повторном
        # проходе сторожа этот же файл не подхватился ещё раз, и
        # чтобы не работать с Excel по сети (риск блокировок/
        # медленной записи на сетевом диске).
        # ------------------------------------------------------

        local_path = os.path.join(LOCAL_WORK_DIR, file_name)

        shutil.move(found_path, local_path)

        self.log(f"Файл забран локально: {local_path}")
        self.status(f"Обрабатываю: {file_name}")

        processor = self.controller.create_ozon_processor(
            local_path,
            logger=self.log,
            stats_callback=self._stats_callback,
            skip_filled=True,
        )

        self.current_processor = processor

        processor.run()

        self.current_processor = None

        result_path = getattr(processor, "result_path", None)

        if not result_path or not os.path.exists(result_path):
            self.log(
                f"✗ Файл результата не найден после обработки: "
                f"{result_path}"
            )
            return

        outgoing = self.config["outgoing_folder"]
        os.makedirs(outgoing, exist_ok=True)

        dest_path = os.path.join(
            outgoing,
            os.path.basename(result_path),
        )

        shutil.copy(result_path, dest_path)

        self.log(f"✓ Результат отправлен: {dest_path}")
        self.status(f"Готово: {file_name}")

    def _stats_callback(self, total, processed, found, not_found):

        if self.on_stats:
            self.on_stats(total, processed, found, not_found)

        self.status(
            f"Обрабатываю... {processed}/{total} "
            f"(найдено {found}, не найдено {not_found})"
        )


# ================================================================
# GUI
# ================================================================

class WatcherApp:

    BG = "#1e1f22"
    CARD = "#2b2d31"
    TEXT = "white"
    ACCENT = "#4e8cff"
    GREEN = "#35b56a"
    RED = "#dc2626"

    def __init__(self):

        self.root = tk.Tk()
        self.root.title("ITB — Сторож сервера")
        self.root.geometry("640x520")
        self.root.configure(bg=self.BG)

        self.config = load_config()
        self.watcher = None

        self._build()

        if self._config_is_complete():
            self._start_watching()
        else:
            self.log(
                "Настройки не заданы - заполните поля выше и "
                "нажмите «Сохранить и запустить»"
            )

    # ------------------------------------------------------
    # UI
    # ------------------------------------------------------

    def _build(self):

        form = tk.Frame(self.root, bg=self.CARD)
        form.pack(fill="x", padx=15, pady=15)

        tk.Label(
            form, text="НАСТРОЙКИ СЕРВЕРА", bg=self.CARD, fg="#9aa4b2",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w", padx=10, pady=(10, 5))

        self.machine_id_var = tk.StringVar(
            value=str(self.config.get("machine_id", ""))
        )
        self.incoming_var = tk.StringVar(
            value=self.config.get("incoming_folder", "")
        )
        self.outgoing_var = tk.StringVar(
            value=self.config.get("outgoing_folder", "")
        )
        self.interval_var = tk.StringVar(
            value=str(self.config.get("poll_interval", DEFAULT_POLL_INTERVAL))
        )

        self._add_row(form, 1, "Номер машины:", self.machine_id_var)
        self._add_row(form, 2, "Входящая папка:", self.incoming_var, browse=True)
        self._add_row(form, 3, "Исходящая папка:", self.outgoing_var, browse=True)
        self._add_row(form, 4, "Интервал проверки (сек):", self.interval_var)

        ttk.Button(
            form, text="Сохранить и запустить",
            command=self._save_and_start,
        ).grid(row=5, column=0, columnspan=3, sticky="ew", padx=10, pady=10)

        status_frame = tk.Frame(self.root, bg=self.CARD)
        status_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.status_var = tk.StringVar(value="Не запущено")

        tk.Label(
            status_frame, textvariable=self.status_var, bg=self.CARD,
            fg=self.ACCENT, font=("Segoe UI", 12, "bold"),
        ).pack(anchor="w", padx=10, pady=10)

        btn_frame = tk.Frame(self.root, bg=self.BG)
        btn_frame.pack(fill="x", padx=15, pady=(0, 10))

        self.stop_btn = ttk.Button(
            btn_frame, text="Остановить сторож", command=self._stop_watching,
        )
        self.stop_btn.pack(side="left")

        log_frame = tk.Frame(self.root, bg=self.CARD)
        log_frame.pack(fill="both", expand=True, padx=15, pady=(0, 15))

        self.log_text = tk.Text(
            log_frame, bg="#1b1b1b", fg="#e5e5e5", relief="flat",
            font=("Consolas", 9),
        )
        self.log_text.pack(fill="both", expand=True, padx=10, pady=10)

    def _add_row(self, parent, row, label, var, browse=False):

        tk.Label(
            parent, text=label, bg=self.CARD, fg=self.TEXT,
            font=("Segoe UI", 10), anchor="w",
        ).grid(row=row, column=0, sticky="w", padx=10, pady=4)

        entry = tk.Entry(parent, textvariable=var, width=40)
        entry.grid(row=row, column=1, sticky="ew", padx=5, pady=4)

        if browse:
            ttk.Button(
                parent, text="...",
                command=lambda: self._browse(var),
                width=3,
            ).grid(row=row, column=2, padx=5)

        parent.grid_columnconfigure(1, weight=1)

    def _browse(self, var):

        folder = filedialog.askdirectory(title="Выберите папку")

        if folder:
            var.set(folder)

    # ------------------------------------------------------
    # Логика
    # ------------------------------------------------------

    def _config_is_complete(self):

        return bool(
            self.config.get("machine_id")
            and self.config.get("incoming_folder")
            and self.config.get("outgoing_folder")
        )

    def _save_and_start(self):

        machine_id = self.machine_id_var.get().strip()
        incoming = self.incoming_var.get().strip()
        outgoing = self.outgoing_var.get().strip()

        if not machine_id or not incoming or not outgoing:
            messagebox.showerror(
                "Ошибка",
                "Заполните номер машины и обе папки.",
            )
            return

        try:
            interval = int(self.interval_var.get())
        except ValueError:
            interval = DEFAULT_POLL_INTERVAL

        self.config = {
            "machine_id": machine_id,
            "incoming_folder": incoming,
            "outgoing_folder": outgoing,
            "poll_interval": interval,
        }

        save_config(self.config)

        self._start_watching()

    def _start_watching(self):

        if self.watcher and self.watcher.running:
            self.watcher.stop()

        self.watcher = ServerWatcher(
            self.config,
            log=self.gui_log,
            status=self.gui_status,
        )

        self.watcher.start()

    def _stop_watching(self):

        if self.watcher:
            self.watcher.stop()

    def gui_log(self, message):

        self.root.after(0, lambda: self._append_log(str(message)))

    def _append_log(self, message):

        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)

    def gui_status(self, text):

        self.root.after(0, lambda: self.status_var.set(text))

    def log(self, message):
        self.gui_log(message)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    WatcherApp().run()
