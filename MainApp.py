# Версия: v1 GUI
# pyinstaller --onefile --noconsole MainApp.py
import os
import shutil
import sys
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
from tkinter.scrolledtext import (ScrolledText)

from core.app_controller import AppController
from learning.manual import ManualTeacher
from learning.runtime import LearningRuntime
from learning_window import LearningWindow
from modules.review_manager import ReviewManager


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

        if len(word) > 5:
            return f'r"{word[:-1]}"'

        return f'r"{word}"'

    return " + ".join(
        [
            f'r"{w[:5]}"'
            for w in words
        ]
    )

def start_recalculate():
    if not selected_file["path"]:
        messagebox.showwarning("Ошибка", "Выберите Excel-файл")
        return

    progress_var.set(0)
    progress_label.config(text="0%")
    set_status("Пересчет кодов...")

    threading.Thread(target=run_recalculate_thread, daemon=True).start()

def run_recalculate_thread():
    try:
        output_path = controller.recalculate(
            selected_file["path"],
            logger=gui_log,
            progress_callback=update_progress,
        )
        set_status("Готово")
        messagebox.showinfo("Готово", f"Коды пересчитаны: {os.path.basename(output_path)}")
        os.startfile(os.path.dirname(output_path))
    except Exception as e:
        set_status("Ошибка")
        messagebox.showerror("Ошибка", f"Не удалось пересчитать:\n{e}")

def make_category_rule(product_name):

    words = product_name.lower().split()

    if len(words) < 2:
        return ""

    pattern = ".*".join(
        [
            w[:5]
            for w in words
            if len(w) >= 4
        ]
    )

    return f'r"{pattern}": "{product_name}",'


def start_ozon_auto():

    if not selected_file["path"]:

        messagebox.showwarning(
            "Ошибка",
            "Выберите Excel-файл"
        )

        return

    progress_var.set(0)
    progress_label.config(text="0%")
    set_status("Запуск...")
    threading.Thread(
        target=run_ozon_auto_thread,
        daemon=True
    ).start()


def stop_ozon_auto():

    processor = (current_processor["instance"])

    if processor:

        processor.stop()
        set_status(
            "Остановлено"
        )

def pause_ozon_auto():

    processor = current_processor.get("instance")

    if processor is None:
        return

    if getattr(processor, "pause_requested", False):

        processor.resume()
        set_status("Продолжено")

    else:

        processor.pause()
        set_status("Пауза")

def run_ozon_auto_thread():

    try:

        set_status(
            "Запуск браузера..."
        )

        processor = controller.create_ozon_processor(
            selected_file["path"],
            logger=gui_log,
            stats_callback=update_stats,
            skip_filled=skip_filled_var.get(),
        )

        current_processor["instance"] = (processor)
        processor.run()
        current_processor["instance"] = None
        set_status("Готово")

        messagebox.showinfo("Готово", "Автообработка завершена")

    except Exception as e:

        current_processor["instance"] = None
        set_status("Ошибка")
        messagebox.showerror("Ошибка", str(e))


def append_log(message):

    log_text.insert(tk.END, message + "\n")
    log_text.see(tk.END)

def gui_log(message):

    root.after(0, lambda: append_log(message))

def update_stats(
        total,
        processed,
        found,
        not_found
):

    remaining = (total - processed)

    root.after(
        0,
        lambda: stats_total.set(
            f"Всего: {total}"
        )
    )

    root.after(
        0,
        lambda: stats_processed.set(
            f"Обработано: {processed}"
        )
    )

    root.after(
        0,
        lambda: stats_remaining.set(
            f"Осталось: {remaining}"
        )
    )

    root.after(
        0,
        lambda: stats_found.set(
            f"Найдено: {found}"
        )
    )

    root.after(
        0,
        lambda: stats_not_found.set(
            f"Не найдено: {not_found}"
        )
    )

    update_progress(
        total,
        processed
    )


def update_progress(
        total,
        processed
):

    if total == 0:

        percent = 0

    else:

        percent = round(
            (
                processed
                / total
            ) * 100,
            1
        )

    root.after(
        0,
        lambda: progress_var.set(
            percent
        )
    )

    root.after(
        0,
        lambda: progress_label.config(
            text=f"{percent}%"
        )
    )


# --- Логика GUI ---
controller = AppController()
selected_file = {"path": None}
current_processor = {
    "instance": None
}

def start_processing():
    if not selected_file["path"]:
        messagebox.showwarning("Ошибка", "Выберите Excel-файл")
        return

    progress_var.set(0)
    progress_label.config(text="0%")
    set_status("Обработка (с упрощением)...")

    threading.Thread(target=run_processing_with_norm, daemon=True).start()

def start_review_mode():

    if not selected_file["path"]:

        messagebox.showwarning(
            "Ошибка",
            "Выберите Excel-файл"
        )

        return

    review_window = tk.Toplevel(root)

    review_window.title(
        "Проверка товаров"
    )

    review_window.geometry(
        "750x500"
    )

    manager = ReviewManager(
        review_window,
        selected_file["path"]
    )

    manager.build_ui()


def run_processing_with_norm():
    try:
        output_path = controller.process(
            selected_file["path"],
            logger=gui_log,
            progress_callback=update_progress,
        )
        set_status("Готово")
        messagebox.showinfo("Готово", f"Файл обработан (с упрощением): {os.path.basename(output_path)}")
        os.startfile(os.path.dirname(output_path))
    except Exception as e:
        set_status("Ошибка")
        messagebox.showerror("Ошибка", f"Не удалось обработать файл:\n{e}")


def choose_file():
    path = filedialog.askopenfilename(
        title="Выберите Excel файл",
        filetypes=[("Excel files", "*.xlsx *.xlsm")]
    )
    if path:
        selected_file["path"] = path
        file_label.config(text=os.path.basename(path))

def set_status(text):

    root.after(
        0,
        lambda: status_var.set(text)
    )

def start_learning():

    if not selected_file["path"]:
        messagebox.showwarning(
            "Ошибка",
            "Выберите Excel-файл"
        )
        return

    result_file = (
        selected_file["path"]
        .replace(".xlsx", "_RESULT.xlsx")
        .replace(".xlsm", "_RESULT.xlsm")
    )

    if not os.path.exists(result_file):
        messagebox.showwarning(
            "Ошибка",
            "RESULT файл не найден"
        )
        return

    teacher = ManualTeacher()
    stats = teacher.learn_result_file(result_file)
    runtime = LearningRuntime()
    report = runtime.analyze()
    window = LearningWindow(root, report, runtime)
    root.wait_window(window)

    if window.applied:
        runtime.mark_learning_processed(
            report.processed_cards
        )
    print("\n========== LEARNING REPORT ==========")
    print("new_products:", len(report.new_products))
    print("new_aliases:", len(report.new_aliases))
    print("new_material_codes:", len(report.new_material_codes))
    print("new_dropdown_variants:", len(report.new_dropdown_variants))
    print(report)

root = tk.Tk()
root.title("Обработка ТН ВЭД")
root.geometry("1000x700")
root.minsize(900, 650)

# ==========================================
# Заголовок
# ==========================================

ttk.Label(
    root,
    text="Обработка ТН ВЭД",
    font=("Segoe UI", 18, "bold")
).pack(
    pady=(15, 10)
)

# ==========================================
# Файл
# ==========================================

file_frame = ttk.LabelFrame(
    root,
    text="Файл"
)

file_frame.pack(
    fill="x",
    padx=10,
    pady=5
)

file_label = ttk.Label(
    file_frame,
    text="Файл не выбран"
)

file_label.pack(
    pady=10
)

ttk.Button(
    file_frame,
    text="Выбрать Excel файл",
    command=choose_file
).pack(
    pady=(0, 10)
)

stats_frame = ttk.LabelFrame(
    root,
    text="Статистика"
)

stats_frame.pack(
    fill="x",
    padx=10,
    pady=5
)

stats_total = tk.StringVar(
    value="Всего: 0"
)

stats_processed = tk.StringVar(
    value="Обработано: 0"
)

stats_remaining = tk.StringVar(
    value="Осталось: 0"
)

stats_found = tk.StringVar(
    value="Найдено: 0"
)

stats_not_found = tk.StringVar(
    value="Не найдено: 0"
)
ttk.Label(
    stats_frame,
    textvariable=stats_total
).grid(
    row=0,
    column=0,
    padx=20,
    pady=5,
    sticky="w"
)

ttk.Label(
    stats_frame,
    textvariable=stats_processed
).grid(
    row=0,
    column=1,
    padx=20,
    pady=5,
    sticky="w"
)

ttk.Label(
    stats_frame,
    textvariable=stats_remaining
).grid(
    row=1,
    column=0,
    padx=20,
    pady=5,
    sticky="w"
)

ttk.Label(
    stats_frame,
    textvariable=stats_found
).grid(
    row=1,
    column=1,
    padx=20,
    pady=5,
    sticky="w"
)

ttk.Label(
    stats_frame,
    textvariable=stats_not_found
).grid(
    row=1,
    column=2,
    padx=20,
    pady=5,
    sticky="w"
)

progress_frame = ttk.LabelFrame(
    root,
    text="Прогресс"
)

progress_frame.pack(
    fill="x",
    padx=10,
    pady=5
)

progress_var = tk.DoubleVar(
    value=0
)

progress_bar = ttk.Progressbar(
    progress_frame,
    variable=progress_var,
    maximum=100
)

progress_bar.pack(
    fill="x",
    padx=10,
    pady=10
)

progress_label = ttk.Label(
    progress_frame,
    text="0%"
)

progress_label.pack(
    pady=(0, 10)
)

status_frame = ttk.LabelFrame(
    root,
    text="Состояние"
)

status_frame.pack(
    fill="x",
    padx=10,
    pady=5
)

status_var = tk.StringVar(
    value="Готов"
)

status_label = ttk.Label(
    status_frame,
    textvariable=status_var,
    font=(
        "Segoe UI",
        11,
        "bold"
    )
)

status_label.pack(
    pady=10
)
# ==========================================
# Кнопки
# ==========================================

action_frame = ttk.LabelFrame(
    root,
    text="Действия"
)

action_frame.pack(
    fill="x",
    padx=10,
    pady=5
)

buttons = [

    (
        "Обработать\n(с упрощением)",
        start_processing
    ),

    (
        "Пересчитать\nкоды",
        start_recalculate
    ),

    (
        "Проверка\nтоваров",
        start_review_mode
    ),

    (
        "Автообработка\nОзон",
        start_ozon_auto
    ),
    (
        "Остановить",
       stop_ozon_auto
    ),

    (
        "Пауза",
        pause_ozon_auto
    ),

    (
    "Обучить\nпо результату",
    start_learning
    )

]

for col, (text, cmd) in enumerate(buttons):

    ttk.Button(
        action_frame,
        text=text,
        command=cmd
    ).grid(
        row=0,
        column=col,
        padx=5,
        pady=10,
        sticky="ew"
    )

    action_frame.columnconfigure(
        col,
        weight=1
    )

skip_filled_var = tk.BooleanVar(
    value=True
)

ttk.Checkbutton(
    action_frame,
    text="Пропускать товары с кодом",
    variable=skip_filled_var
).grid(
    row=1,
    column=0,
    columnspan=len(buttons),
    sticky="w",
    padx=10,
    pady=(0, 10)
)

# ==========================================
# Логи
# ==========================================

log_frame = ttk.LabelFrame(
    root,
    text="Журнал работы"
)

log_frame.pack(
    fill="both",
    expand=True,
    padx=10,
    pady=10
)

log_text = ScrolledText(
    log_frame,
    font=("Consolas", 10)
)

log_text.pack(
    fill="both",
    expand=True,
    padx=5,
    pady=5
)


root.mainloop()