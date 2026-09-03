from tkinter import *
from tkinter import ttk, messagebox

from learning.applier import LearningApplier
from learning.review_models import (
    LearningReport,
)
from learning.dictionary_registry import dictionary_choices, group_choices


class LearningWindow(Toplevel):

    def __init__(self, parent, report: LearningReport, runtime):

        super().__init__(parent)

        self.report = report
        self.runtime = runtime
        self.title("Обучение системы")
        self.geometry("1450x750")
        self.minsize(1200, 600)
        self.transient(parent)
        self.grab_set()
        self.applied = False
        self.selected_products = set()
        self.selected_aliases = set()
        self.selected_dropdowns = set()
        self.selected_dropdown_match_words = set()
        self.selected_dropdown_candidates = set()
        self.selected_patterns = set()
        self.selected_dictionary_words = {}    # iid -> подтверждённый item (не set: NewDictionaryWord изменяемый -> нехэшируемый)
        self.product_rows = {}
        self.alias_rows = {}
        self.dropdown_rows = {}
        self.dropdown_match_words_rows = {}
        self.dropdown_candidate_rows = {}
        self.pattern_rows = {}
        self.dictionary_word_rows = {}
        self._build_ui()
        self._fill_products()
        self._fill_aliases()
        self._fill_dropdowns()
        self._fill_dropdown_match_words()
        self._fill_dropdown_candidates()
        self._fill_patterns()
        self._fill_dictionary_words()
    # ======================================================
    # UI
    # ======================================================
    def _build_ui(self):

        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.notebook = ttk.Notebook(self)
        self.notebook.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=10,
            pady=10
        )
        self.products_frame = ttk.Frame(self.notebook)
        self.aliases_frame = ttk.Frame(self.notebook)
        self.dropdowns_frame = ttk.Frame(self.notebook)
        self.dropdown_match_words_frame = ttk.Frame(self.notebook)
        self.dropdown_candidates_frame = ttk.Frame(self.notebook)
        self.patterns_frame = ttk.Frame(self.notebook)
        self.dictionary_words_frame = ttk.Frame(self.notebook)
        self.notebook.add(
            self.products_frame,
            text=f"Новые товары ({len(self.report.new_products)})"
        )
        self.notebook.add(
            self.aliases_frame,
            text=f"Алиасы ({len(self.report.new_aliases)})"
        )
        self.notebook.add(
            self.dropdowns_frame,
            text=f"Выпадающие списки ({len(self.report.new_dropdown_variants)})"
        )
        self.notebook.add(
            self.dropdown_match_words_frame,
            text=f"Расширить списки ({len(self.report.new_dropdown_match_words)})"
        )
        self.notebook.add(
            self.dropdown_candidates_frame,
            text=f"Нужен ли список? ({len(self.report.new_dropdown_candidates)})"
        )
        self.notebook.add(
            self.patterns_frame,
            text=f"Паттерны ({len(self.report.new_patterns)})"
        )
        self.notebook.add(
            self.dictionary_words_frame,
            text=f"Неизвестные слова ({len(self.report.new_dictionary_words)})"
        )
        self.products_tree = self._create_products_tree(
            self.products_frame
        )
        self.alias_tree = self._create_alias_tree(
            self.aliases_frame
        )
        self.dropdown_tree = self._create_dropdown_tree(
            self.dropdowns_frame
        )
        self.dropdown_match_words_tree = self._create_dropdown_match_words_tree(
            self.dropdown_match_words_frame
        )
        self.dropdown_candidate_tree = self._create_dropdown_candidate_tree(
            self.dropdown_candidates_frame
        )
        self.pattern_tree = self._create_pattern_tree(
            self.patterns_frame
        )
        self.dictionary_word_tree = self._create_dictionary_word_tree(
            self.dictionary_words_frame
        )

        bottom = ttk.Frame(self)
        bottom.grid(
            row=1,
            column=0,
            sticky="ew",
            padx=10,
            pady=(0, 10)
        )

        ttk.Button(
            bottom,
            text="Выбрать всё",
            command=self.select_all
        ).pack(side=LEFT)

        ttk.Button(
            bottom,
            text="Снять всё",
            command=self.clear_all
        ).pack(side=LEFT, padx=5)

        ttk.Separator(
            bottom,
            orient="vertical"
        ).pack(
            side=LEFT,
            fill=Y,
            padx=8
        )

        ttk.Button(
            bottom,
            text="Применить",
            command=self.apply
        ).pack(side=RIGHT)

        ttk.Button(
            bottom,
            text="Отмена",
            command=self.destroy
        ).pack(
            side=RIGHT,
            padx=5
        )

    # ======================================================
    # TREE BUILDERS
    # ======================================================
    def _create_tree(self, parent, columns):
        parent.columnconfigure(0, weight=1)
        parent.rowconfigure(0, weight=1)

        tree = ttk.Treeview(
            parent,
            columns=columns,
            show="headings",
            selectmode="browse"
        )

        vsb = ttk.Scrollbar(
            parent,
            orient="vertical",
            command=tree.yview
        )

        hsb = ttk.Scrollbar(
            parent,
            orient="horizontal",
            command=tree.xview
        )

        tree.configure(
            yscrollcommand=vsb.set,
            xscrollcommand=hsb.set
        )

        tree.grid(
            row=0,
            column=0,
            sticky="nsew"
        )

        vsb.grid(
            row=0,
            column=1,
            sticky="ns"
        )

        hsb.grid(
            row=1,
            column=0,
            sticky="ew"
        )

        # ------------------------------------------------------
        # ОДИН КЛИК = ВЫБОР / СНЯТИЕ ВЫБОРА
        # ------------------------------------------------------
        tree.bind(
            "<ButtonRelease-1>",
            self._toggle_current
        )
        # ------------------------------------------------------
        # ДВОЙНОЙ КЛИК БОЛЬШЕ НЕ ИСПОЛЬЗУЕМ
        # ------------------------------------------------------
        tree.bind(
            "<Double-1>",
            lambda event: "break"
        )
        # ------------------------------------------------------
        # SPACE = ВЫБОР / СНЯТИЕ ВЫБОРА
        # ------------------------------------------------------
        tree.bind(
            "<space>",
            self._toggle_current
        )
        return tree


    def _create_dictionary_word_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "dictionary",
                "word",
                "count",
                "product",
                "target",
            )
        )

        tree.heading("selected", text="✓")
        tree.heading("dictionary", text="Похоже на словарь")
        tree.heading("word", text="Неизвестное слово")
        tree.heading("count", text="Встреч")
        tree.heading("product", text="Например, товар")
        tree.heading("target", text="Куда добавлено")
        tree.column("selected", width=45, anchor="center")
        tree.column("dictionary", width=200)
        tree.column("word", width=260)
        tree.column("count", width=80, anchor="center")
        tree.column("product", width=260)
        tree.column("target", width=280)

        return tree

    def _create_pattern_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "product",
                "pattern"
            )
        )
        tree.heading(
            "selected",
            text="✓"
        )
        tree.heading(
            "product",
            text="Товар"
        )
        tree.heading(
            "pattern",
            text="Pattern"
        )
        tree.column(
            "selected",
            width=45,
            anchor="center"
        )
        tree.column(
            "product",
            width=300
        )
        tree.column(
            "pattern",
            width=800
        )
        return tree

    def _create_products_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "description",
                "code",
                "material",
                "title",
                "url"
            )
        )
        tree.heading("selected", text="✓")
        tree.heading("description", text="Описание")
        tree.heading("code", text="Код")
        tree.heading("material", text="Материал")
        tree.heading("title", text="Название карточки")
        tree.heading("url", text="URL")
        tree.column("selected", width=45, anchor="center")
        tree.column("description", width=220)
        tree.column("code", width=130)
        tree.column("material", width=170)
        tree.column("title", width=420)
        tree.column("url", width=450)

        return tree

    def _create_alias_tree(self, parent):

        tree = self._create_tree(parent,("selected", "product", "alias"))
        tree.heading("selected", text="✓")
        tree.heading("product", text="Товар")
        tree.heading("alias", text="Новый алиас")
        tree.column("selected", width=45, anchor="center")
        tree.column("product", width=260)
        tree.column("alias", width=800)

        return tree

    def _create_dropdown_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "product",
                "code",
                "group",
                "name",
                "match",
            )
        )

        tree.heading("selected", text="✓")
        tree.heading("product", text="Dropdown")
        tree.heading("code", text="Новый код")
        tree.heading("group", text="Факт (материал/группа)")
        tree.heading("name", text="Название (автозаполнено)")
        tree.heading("match", text="Ключевые слова (автозаполнено)")
        tree.column("selected", width=45, anchor="center")
        tree.column("product", width=220)
        tree.column("code", width=130)
        tree.column("group", width=180)
        tree.column("name", width=200)
        tree.column("match", width=300)

        return tree

    def _create_dropdown_match_words_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "product",
                "code",
                "words",
            )
        )

        tree.heading("selected", text="✓")
        tree.heading("product", text="Dropdown")
        tree.heading("code", text="Существующий код")
        tree.heading("words", text="Новые ключевые слова")
        tree.column("selected", width=45, anchor="center")
        tree.column("product", width=300)
        tree.column("code", width=180)
        tree.column("words", width=500)

        return tree

    def _create_dropdown_candidate_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "product",
                "codes"
            )
        )

        tree.heading("selected", text="✓")
        tree.heading("product", text="Товар (dropdown пока нет)")
        tree.heading("codes", text="Встреченные коды (частота)")
        tree.column("selected", width=45, anchor="center")
        tree.column("product", width=300)
        tree.column("codes", width=850)

        return tree

    # ======================================================
    # FILL TABLES
    # ======================================================

    def _fill_products(self):

        for item in self.report.new_products:

            iid = self.products_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.description,
                    item.code,
                    item.material,
                    item.title,
                    item.url,
                )
            )

            self.product_rows[iid] = item

    def _fill_aliases(self):

        for item in self.report.new_aliases:

            iid = self.alias_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.product,
                    item.alias,
                )
            )

            self.alias_rows[iid] = item

    def _fill_dropdowns(self):

        for item in self.report.new_dropdown_variants:

            iid = self.dropdown_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.product,
                    item.code,
                    getattr(item, "group", ""),
                    getattr(item, "name", ""),
                    ", ".join(getattr(item, "match", ()) or ()),
                )
            )

            self.dropdown_rows[iid] = item

    def _fill_dropdown_match_words(self):

        for item in self.report.new_dropdown_match_words:

            iid = self.dropdown_match_words_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.product,
                    item.code,
                    ", ".join(item.words or ()),
                )
            )

            self.dropdown_match_words_rows[iid] = item

    def _fill_dropdown_candidates(self):

        for item in self.report.new_dropdown_candidates:

            codes_text = ", ".join(
                f"{code} ({count})"
                for code, count in item.codes
            )

            iid = self.dropdown_candidate_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.product,
                    codes_text,
                )
            )

            self.dropdown_candidate_rows[iid] = item

    def _fill_patterns(self):

        for item in self.report.new_patterns:
            iid = self.pattern_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.product,
                    item.pattern,
                )
            )

            self.pattern_rows[iid] = item

    def _fill_dictionary_words(self):

        for item in self.report.new_dictionary_words:

            label = dict(dictionary_choices()).get(
                item.dictionary, item.dictionary
            )

            iid = self.dictionary_word_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    label,
                    item.word,
                    item.count,
                    item.product,
                    "",
                )
            )

            self.dictionary_word_rows[iid] = item

    # ======================================================
    # SELECTION
    # ======================================================

    def _toggle_current(self, event=None):

        widget = event.widget

        selection = widget.selection()

        if not selection:
            return

        for iid in selection:

            if widget is self.products_tree:
                self._toggle_product(iid)

            elif widget is self.alias_tree:
                self._toggle_alias(iid)

            elif widget is self.dropdown_tree:
                self._toggle_dropdown(iid)

            elif widget is self.dropdown_match_words_tree:
                self._toggle_dropdown_match_words(iid)

            elif widget is self.dropdown_candidate_tree:
                self._toggle_dropdown_candidate(iid)

            elif widget is self.pattern_tree:
                self._toggle_pattern(iid)

            elif widget is self.dictionary_word_tree:
                self._toggle_dictionary_word(iid)

        return "break"

    def _toggle_product(self, iid):

        item = self.product_rows[iid]

        values = list(
            self.products_tree.item(
                iid,
                "values"
            )
        )

        if item in self.selected_products:

            self.selected_products.remove(item)
            values[0] = "☐"

        else:

            self.selected_products.add(item)
            values[0] = "☑"

        self.products_tree.item(
            iid,
            values=values
        )

    def _toggle_alias(self, iid):

        item = self.alias_rows[iid]

        values = list(
            self.alias_tree.item(
                iid,
                "values"
            )
        )

        if item in self.selected_aliases:

            self.selected_aliases.remove(item)
            values[0] = "☐"

        else:

            self.selected_aliases.add(item)
            values[0] = "☑"

        self.alias_tree.item(
            iid,
            values=values
        )

    def _toggle_dropdown(self, iid):

        item = self.dropdown_rows[iid]

        values = list(
            self.dropdown_tree.item(
                iid,
                "values"
            )
        )

        if item in self.selected_dropdowns:

            self.selected_dropdowns.remove(item)
            values[0] = "☐"

        else:

            self.selected_dropdowns.add(item)
            values[0] = "☑"

        self.dropdown_tree.item(
            iid,
            values=values
        )

    def _toggle_dropdown_match_words(self, iid):

        item = self.dropdown_match_words_rows[iid]

        values = list(
            self.dropdown_match_words_tree.item(
                iid,
                "values"
            )
        )

        if item in self.selected_dropdown_match_words:

            self.selected_dropdown_match_words.remove(item)
            values[0] = "☐"

        else:

            self.selected_dropdown_match_words.add(item)
            values[0] = "☑"

        self.dropdown_match_words_tree.item(
            iid,
            values=values
        )

    def _toggle_dropdown_candidate(self, iid):

        item = self.dropdown_candidate_rows[iid]

        values = list(
            self.dropdown_candidate_tree.item(
                iid,
                "values"
            )
        )

        if item in self.selected_dropdown_candidates:

            self.selected_dropdown_candidates.remove(item)
            values[0] = "☐"

        else:

            self.selected_dropdown_candidates.add(item)
            values[0] = "☑"

        self.dropdown_candidate_tree.item(
            iid,
            values=values
        )

    def _toggle_pattern(self, iid):

        item = self.pattern_rows[iid]

        values = list(
            self.pattern_tree.item(
                iid,
                "values"
            )
        )

        if item in self.selected_patterns:

            self.selected_patterns.remove(item)
            values[0] = "☐"

        else:

            self.selected_patterns.add(item)
            values[0] = "☑"

        self.pattern_tree.item(
            iid,
            values=values
        )

    def _toggle_dictionary_word(self, iid):
        """
        В отличие от остальных вкладок - здесь нельзя просто
        поставить галочку: перед подтверждением куратор обязан
        выбрать, в какой словарь и в какую группу (существующую или
        новую) добавить слово. Поэтому клик по строке открывает
        диалог, а не переключает чекбокс напрямую.
        """

        item = self.dictionary_word_rows[iid]

        dialog = DictionaryWordDialog(self, item)
        self.wait_window(dialog)

        if dialog.result is None:
            return

        target_dictionary, target_group = dialog.result

        item.target_dictionary = target_dictionary
        item.target_group = target_group
        item.selected = True

        self.selected_dictionary_words[iid] = item

        dictionary_label = dict(dictionary_choices()).get(
            target_dictionary, target_dictionary
        )

        values = list(
            self.dictionary_word_tree.item(iid, "values")
        )
        values[0] = "☑"
        values[5] = f"{dictionary_label} → {target_group}"

        self.dictionary_word_tree.item(
            iid,
            values=values
        )


    def select_all(self):

        current_tab = self.notebook.index(
            self.notebook.select()
        )

        # ------------------------------------------------------
        # 0. НОВЫЕ ТОВАРЫ
        # ------------------------------------------------------

        if current_tab == 0:

            for iid in self.product_rows:

                if self.product_rows[iid] not in self.selected_products:
                    self._toggle_product(iid)

        # ------------------------------------------------------
        # 1. АЛИАСЫ
        # ------------------------------------------------------
        elif current_tab == 1:
            for iid in self.alias_rows:
                if self.alias_rows[iid] not in self.selected_aliases:
                    self._toggle_alias(iid)
        # ------------------------------------------------------
        # 2. DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 2:

            for iid in self.dropdown_rows:

                if self.dropdown_rows[iid] not in self.selected_dropdowns:
                    self._toggle_dropdown(iid)

        # ------------------------------------------------------
        # 3. РАСШИРИТЬ DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 3:

            for iid in self.dropdown_match_words_rows:

                if (
                        self.dropdown_match_words_rows[iid]
                        not in self.selected_dropdown_match_words
                ):
                    self._toggle_dropdown_match_words(iid)

        # ------------------------------------------------------
        # 4. НУЖЕН DROPDOWN?
        # ------------------------------------------------------

        elif current_tab == 4:
            for iid in self.dropdown_candidate_rows:
                if (
                        self.dropdown_candidate_rows[iid]
                        not in self.selected_dropdown_candidates
                ):
                    self._toggle_dropdown_candidate(iid)
        # ------------------------------------------------------
        # 5. PATTERNS
        # ------------------------------------------------------
        elif current_tab == 5:
            for iid in self.pattern_rows:
                if self.pattern_rows[iid] not in self.selected_patterns:
                    self._toggle_pattern(iid)

        # ------------------------------------------------------
        # 6. НЕИЗВЕСТНЫЕ СЛОВА
        # ------------------------------------------------------
        elif current_tab == 6:
            messagebox.showinfo(
                "Обучение",
                "Для каждого слова нужно выбрать словарь и группу - "
                "кликните по строке."
            )


    def clear_all(self):

        current_tab = self.notebook.index(
            self.notebook.select()
        )

        # ------------------------------------------------------
        # 0. НОВЫЕ ТОВАРЫ
        # ------------------------------------------------------

        if current_tab == 0:

            for iid in list(self.product_rows):

                if self.product_rows[iid] in self.selected_products:
                    self._toggle_product(iid)

        # ------------------------------------------------------
        # 1. АЛИАСЫ
        # ------------------------------------------------------

        elif current_tab == 1:

            for iid in list(self.alias_rows):

                if self.alias_rows[iid] in self.selected_aliases:
                    self._toggle_alias(iid)

        # ------------------------------------------------------
        # 2. DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 2:

            for iid in list(self.dropdown_rows):

                if self.dropdown_rows[iid] in self.selected_dropdowns:
                    self._toggle_dropdown(iid)

        # ------------------------------------------------------
        # 3. РАСШИРИТЬ DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 3:

            for iid in list(self.dropdown_match_words_rows):

                if (
                        self.dropdown_match_words_rows[iid]
                        in self.selected_dropdown_match_words
                ):
                    self._toggle_dropdown_match_words(iid)

        # ------------------------------------------------------
        # 4. НУЖЕН DROPDOWN?
        # ------------------------------------------------------

        elif current_tab == 4:

            for iid in list(self.dropdown_candidate_rows):

                if (
                        self.dropdown_candidate_rows[iid]
                        in self.selected_dropdown_candidates
                ):
                    self._toggle_dropdown_candidate(iid)

        # ------------------------------------------------------
        # 5. PATTERNS
        # ------------------------------------------------------

        elif current_tab == 5:
            for iid in list(self.pattern_rows):
                if self.pattern_rows[iid] in self.selected_patterns:
                    self._toggle_pattern(iid)

        # ------------------------------------------------------
        # 6. НЕИЗВЕСТНЫЕ СЛОВА
        # ------------------------------------------------------
        elif current_tab == 6:
            for iid in list(self.selected_dictionary_words):

                item = self.dictionary_word_rows[iid]
                item.selected = False
                item.target_dictionary = ""
                item.target_group = ""

                values = list(
                    self.dictionary_word_tree.item(iid, "values")
                )
                values[0] = "☐"
                values[5] = ""

                self.dictionary_word_tree.item(iid, values=values)

            self.selected_dictionary_words.clear()





    # ======================================================
    # APPLY
    # ======================================================

    def apply(self):

        if (
            not self.selected_products
            and not self.selected_aliases
            and not self.selected_dropdowns
            and not self.selected_dropdown_match_words
            and not self.selected_dropdown_candidates
            and not self.selected_patterns
            and not self.selected_dictionary_words
        ):

            messagebox.showwarning(
                "Обучение",
                "Не выбраны элементы."
            )

            return

        applier = LearningApplier()

        applier.apply(
            products=list(self.selected_products),
            aliases=list(self.selected_aliases),
            dropdowns=list(self.selected_dropdowns),
            patterns=list(self.selected_patterns),
            dropdown_candidates=list(self.selected_dropdown_candidates),
            dropdown_match_words=list(self.selected_dropdown_match_words),
            dictionary_words=list(self.selected_dictionary_words.values()),
        )
        self.applied = True
        self.runtime.mark_learning_processed(
            self.report.processed_cards
        )

        messagebox.showinfo(
            "Обучение",
            "Изменения успешно сохранены."
        )

        self.destroy()


class DictionaryWordDialog(Toplevel):
    """
    "Куда отнести неизвестное слово" - куратор выбирает словарь
    (материал/пол/...) и группу внутри него: существующую (из
    выпадающего списка - напр. для материала это пластик/металл/
    текстиль/...) или новую, вписав своё название прямо в то же
    поле (комбобокс НЕ readonly специально для этого).

    Список групп в комбобоксе перезагружается при смене словаря -
    поэтому у "материала" и "пола" группы не перемешиваются друг
    с другом.
    """

    def __init__(self, parent, item):

        super().__init__(parent)

        self.title("Добавить в словарь")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None

        self._choices = dictionary_choices()          # [(key, label), ...]
        self._label_by_key = dict(self._choices)
        self._key_by_label = {
            label: key for key, label in self._choices
        }

        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            frame,
            text=f"Слово: «{item.word}»",
            font=("TkDefaultFont", 10, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w")

        ttk.Label(
            frame,
            text=(
                f"Встречается {item.count} раз(а), "
                f"например в товаре «{item.product}»"
            ),
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 10))

        ttk.Label(frame, text="Словарь:").grid(
            row=2, column=0, sticky="w", pady=3
        )

        default_key = item.target_dictionary or item.dictionary
        default_label = self._label_by_key.get(default_key, "")

        self.dict_var = StringVar(value=default_label)
        self.dict_combo = ttk.Combobox(
            frame,
            textvariable=self.dict_var,
            values=[label for _, label in self._choices],
            state="readonly",
            width=32,
        )
        self.dict_combo.grid(row=2, column=1, sticky="ew", pady=3)
        self.dict_combo.bind(
            "<<ComboboxSelected>>",
            self._on_dictionary_changed,
        )

        ttk.Label(frame, text="Группа:").grid(
            row=3, column=0, sticky="w", pady=3
        )

        self.group_var = StringVar(value=item.target_group)
        self.group_combo = ttk.Combobox(
            frame,
            textvariable=self.group_var,
            width=32,
        )
        self.group_combo.grid(row=3, column=1, sticky="ew", pady=3)

        ttk.Label(
            frame,
            text=(
                "Выберите существующую группу из списка\n"
                "или впишите новую."
            ),
            foreground="#666666",
        ).grid(row=4, column=0, columnspan=2, sticky="w", pady=(2, 10))

        buttons = ttk.Frame(frame)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e")

        ttk.Button(
            buttons,
            text="Отмена",
            command=self.destroy,
        ).pack(side=RIGHT, padx=(6, 0))

        ttk.Button(
            buttons,
            text="Добавить",
            command=self._confirm,
        ).pack(side=RIGHT)

        self._reload_groups(default_key)

        self.bind("<Return>", lambda event: self._confirm())
        self.bind("<Escape>", lambda event: self.destroy())

        self.update_idletasks()
        self.geometry(
            f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 80}"
        )

    def _on_dictionary_changed(self, event=None):

        key = self._key_by_label.get(self.dict_var.get())
        self._reload_groups(key)

    def _reload_groups(self, key):

        self.group_combo["values"] = (
            group_choices(key) if key else []
        )

    def _confirm(self):

        key = self._key_by_label.get(self.dict_var.get())
        group = self.group_var.get().strip().lower()

        if not key or not group:

            messagebox.showwarning(
                "Добавить в словарь",
                "Выберите словарь и укажите (или впишите) группу.",
                parent=self,
            )

            return

        self.result = (key, group)
        self.destroy()