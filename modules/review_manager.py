from tkinter import ttk, messagebox
import pandas as pd
import os


class ReviewManager:
    def __init__(self, root_window, file_path):
        self.root = root_window
        self.file_path = file_path
        # Ищем CONFLICTS.xlsx в той же папке, что и исходный файл
        self.conflicts_path = os.path.join(
            os.path.dirname(file_path),
            "CONFLICTS.xlsx"
        )

    def build_ui(self):
        self.root.configure(padx=10, pady=10)

        # Заголовок
        header_frame = ttk.Frame(self.root)
        header_frame.pack(fill="x", pady=(0, 10))

        ttk.Label(
            header_frame,
            text="Анализ конфликтов ТН ВЭД",
            font=("Segoe UI", 14, "bold")
        ).pack(side="left")

        # Проверяем наличие файла конфликтов
        if not os.path.exists(self.conflicts_path):
            ttk.Label(
                self.root,
                text="⚠️ Файл CONFLICTS.xlsx не найден.\nСначала нажмите 'Построить словари', чтобы программа нашла спорные товары.",
                foreground="orange",
                font=("Segoe UI", 11),
                justify="center"
            ).pack(expand=True)

            ttk.Button(
                self.root,
                text="Закрыть",
                command=self.root.destroy
            ).pack(pady=20)
            return

        # Читаем Excel
        try:
            df = pd.read_excel(self.conflicts_path)
        except Exception as e:
            messagebox.showerror("Ошибка", f"Не удалось прочитать файл:\n{e}")
            self.root.destroy()
            return

        # Информация о количестве
        ttk.Label(
            self.root,
            text=f"Найдено спорных позиций: {len(df)}",
            font=("Segoe UI", 10)
        ).pack(anchor="w", pady=(0, 5))

        # Создаем таблицу (Treeview)
        tree_frame = ttk.Frame(self.root)
        tree_frame.pack(fill="both", expand=True)

        columns = list(df.columns)
        tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=15)

        # Настраиваем заголовки и ширину
        for col in columns:
            tree.heading(col, text=col)
            if col == "Наименование":
                tree.column(col, width=350, anchor="w")
            elif col == "Примеры":
                tree.column(col, width=300, anchor="w")
            else:
                tree.column(col, width=120, anchor="center")

        # Заполняем данными
        for _, row in df.iterrows():
            values = [str(row[col]) if pd.notna(row[col]) else "" for col in columns]
            tree.insert("", "end", values=values)

        # Скроллбары
        scrollbar_y = ttk.Scrollbar(tree_frame, orient="vertical", command=tree.yview)
        scrollbar_x = ttk.Scrollbar(tree_frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)

        tree.grid(row=0, column=0, sticky="nsew")
        scrollbar_y.grid(row=0, column=1, sticky="ns")
        scrollbar_x.grid(row=1, column=0, sticky="ew")

        tree_frame.grid_rowconfigure(0, weight=1)
        tree_frame.grid_columnconfigure(0, weight=1)

        # Кнопки управления
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", pady=(10, 0))

        ttk.Button(
            btn_frame,
            text="Открыть папку с файлом",
            command=lambda: os.startfile(os.path.dirname(self.conflicts_path))
        ).pack(side="left", padx=5)

        ttk.Button(
            btn_frame,
            text="Закрыть",
            command=self.root.destroy
        ).pack(side="right", padx=5)