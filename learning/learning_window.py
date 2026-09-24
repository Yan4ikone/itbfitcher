import importlib

from tkinter import *
from tkinter import ttk, messagebox

from learning.applier import LearningApplier
from learning.review_models import (
    LearningReport,
)
from learning.dictionary_registry import dictionary_choices, group_choices
from learning import dictionary_editor


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

        ttk.Button(
            self.aliases_frame,
            text="В словарь мусора...",
            command=self._send_alias_to_trash,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
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

        ttk.Button(
            self.dictionary_words_frame,
            text="Редактор словарей...",
            command=self._open_dictionary_editor,
        ).grid(
            row=2,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(6, 0),
        )

        ttk.Button(
            self.dictionary_words_frame,
            text="Редактор match/group...",
            command=self._open_variant_editor,
        ).grid(
            row=3,
            column=0,
            columnspan=2,
            sticky="w",
            pady=(2, 0),
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

    def _send_alias_to_trash(self):
        """Отправить выделенный алиас в мусорный словарь
        (TRASH_MARKETING) - чтобы такое слово/фраза больше не
        предлагались как алиас ни для какого товара. Раз это мусор,
        а не алиас - строка убирается из списка на добавление и из
        выбранных, если была отмечена."""

        selection = self.alias_tree.selection()

        if not selection:
            messagebox.showwarning(
                "В словарь мусора",
                "Сначала выберите алиас в списке.",
            )
            return

        iid = selection[0]
        item = self.alias_rows[iid]

        dialog = TrashWordDialog(self, item.alias)
        self.wait_window(dialog)

        if dialog.result is None:
            return

        try:
            already = dictionary_editor.is_trash_word(dialog.result)
            dictionary_editor.add_trash_word(dialog.result)
        except ValueError as error:
            messagebox.showwarning("В словарь мусора", str(error))
            return

        if already:
            messagebox.showinfo(
                "В словарь мусора",
                f"«{dialog.result}» уже в словаре мусора.",
            )

        self.selected_aliases.discard(item)
        self.alias_rows.pop(iid, None)
        self.alias_tree.delete(iid)

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

    def _open_dictionary_editor(self):
        """Самостоятельный редактор словарей (материал/пол/
        характеристики) - в отличие от вкладки выше, не привязан к
        текущему прогону обучения: можно открыть в любой момент,
        посмотреть все категории и слова, добавить/удалить что угодно
        напрямую. Изменения пишутся на диск сразу, без отдельной
        кнопки "Применить"."""

        DictionaryEditorWindow(self)

    def _open_variant_editor(self):
        """Редактор match-слов и group конкретного dropdown-варианта
        товара (dictionaries/products.py) - в отличие от общих
        словарей выше (материал/пол/характеристика), это поле внутри
        конкретного товара, и раньше почистить его можно было только
        руками в products.py. Не привязан к текущему прогону, пишет
        на диск сразу."""

        VariantEditorWindow(self)


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


class DictionaryEditorWindow(Toplevel):
    """
    Самостоятельный редактор общих словарей (материал/пол/
    характеристики) - открывается кнопкой из окна обучения, но не
    привязан к конкретному прогону: можно посмотреть все категории и
    слова в любом словаре, добавить новую категорию или слово,
    удалить существующие. Каждое действие сразу пишется на диск
    (см. learning/dictionary_editor.py) - здесь нет отдельной кнопки
    "Применить".
    """

    def __init__(self, parent):

        super().__init__(parent)

        self.title("Редактор словарей")
        self.geometry("560x520")
        self.transient(parent)

        self._choices = dictionary_choices()          # [(key, label), ...]
        self._label_by_key = dict(self._choices)
        self._key_by_label = {
            label: key for key, label in self._choices
        }

        container = ttk.Frame(self, padding=10)
        container.pack(fill=BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)

        # --------------------------------------------------
        # Выбор словаря
        # --------------------------------------------------
        top = ttk.Frame(container)
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))

        ttk.Label(top, text="Словарь:").pack(side=LEFT)

        self.dict_var = StringVar(
            value=self._choices[0][1] if self._choices else ""
        )

        self.dict_combo = ttk.Combobox(
            top,
            textvariable=self.dict_var,
            values=[label for _, label in self._choices],
            state="readonly",
            width=40,
        )
        self.dict_combo.pack(side=LEFT, padx=(6, 0))
        self.dict_combo.bind(
            "<<ComboboxSelected>>",
            lambda event: self._reload_tree(),
        )

        # --------------------------------------------------
        # Дерево: категория -> слова
        # --------------------------------------------------
        tree_frame = ttk.Frame(container)
        tree_frame.grid(row=1, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, show="tree")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        # --------------------------------------------------
        # Добавление
        # --------------------------------------------------
        add_frame = ttk.LabelFrame(container, text="Добавить", padding=8)
        add_frame.grid(row=2, column=0, sticky="ew", pady=(8, 0))
        add_frame.columnconfigure(1, weight=1)

        ttk.Label(add_frame, text="Новая категория:").grid(
            row=0, column=0, sticky="w", pady=2
        )
        self.new_category_var = StringVar()
        ttk.Entry(
            add_frame, textvariable=self.new_category_var
        ).grid(row=0, column=1, sticky="ew", padx=(6, 6), pady=2)
        ttk.Button(
            add_frame, text="Добавить категорию",
            command=self._add_category,
        ).grid(row=0, column=2, pady=2)

        ttk.Label(add_frame, text="Слово в категорию:").grid(
            row=1, column=0, sticky="w", pady=2
        )
        self.new_word_var = StringVar()
        ttk.Entry(
            add_frame, textvariable=self.new_word_var
        ).grid(row=1, column=1, sticky="ew", padx=(6, 6), pady=2)
        ttk.Button(
            add_frame, text="Добавить слово",
            command=self._add_word,
        ).grid(row=1, column=2, pady=2)

        ttk.Label(
            add_frame,
            text="Слово добавляется в категорию, выбранную в дереве выше.",
            foreground="#666666",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # --------------------------------------------------
        # Удаление
        # --------------------------------------------------
        bottom = ttk.Frame(container)
        bottom.grid(row=3, column=0, sticky="e", pady=(8, 0))

        ttk.Button(
            bottom, text="Удалить выбранное",
            command=self._delete_selected,
        ).pack(side=RIGHT)

        self._reload_tree()

    # ==========================================================

    def _current_dict_key(self):
        return self._key_by_label.get(self.dict_var.get())

    def _reload_tree(self):

        self.tree.delete(*self.tree.get_children())

        key = self._current_dict_key()

        if not key:
            return

        categories = dictionary_editor.list_categories(key)

        for group, words in categories.items():

            group_id = self.tree.insert(
                "", "end", text=group, open=False,
            )

            for word in words:
                self.tree.insert(group_id, "end", text=word)

    def _selected_category(self):
        """Категория, к которой относится текущий выбор в дереве -
        сам узел категории, если выбрана она, либо родитель, если
        выбрано слово. None, если ничего не выбрано."""

        selection = self.tree.selection()

        if not selection:
            return None

        iid = selection[0]
        parent = self.tree.parent(iid)

        if parent:
            return self.tree.item(parent, "text")

        return self.tree.item(iid, "text")

    def _add_category(self):

        key = self._current_dict_key()
        group = self.new_category_var.get().strip().lower()

        if not key:
            messagebox.showwarning(
                "Редактор словарей", "Выберите словарь.", parent=self
            )
            return

        if not group:
            messagebox.showwarning(
                "Редактор словарей",
                "Введите название новой категории.",
                parent=self,
            )
            return

        try:
            dictionary_editor.create_category(key, group)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словарей", str(error), parent=self
            )
            return

        self.new_category_var.set("")
        self._reload_tree()

    def _add_word(self):

        key = self._current_dict_key()
        group = self._selected_category()
        word = self.new_word_var.get().strip().lower()

        if not key:
            messagebox.showwarning(
                "Редактор словарей", "Выберите словарь.", parent=self
            )
            return

        if not group:
            messagebox.showwarning(
                "Редактор словарей",
                "Сначала выберите категорию в дереве, "
                "в которую нужно добавить слово.",
                parent=self,
            )
            return

        if not word:
            messagebox.showwarning(
                "Редактор словарей", "Введите слово.", parent=self
            )
            return

        try:
            dictionary_editor.add_word(key, group, word)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словарей", str(error), parent=self
            )
            return

        self.new_word_var.set("")
        self._reload_tree()

    def _delete_selected(self):

        key = self._current_dict_key()
        selection = self.tree.selection()

        if not key or not selection:
            messagebox.showwarning(
                "Редактор словарей",
                "Выберите категорию или слово для удаления.",
                parent=self,
            )
            return

        iid = selection[0]
        parent = self.tree.parent(iid)

        if parent:
            # Выбрано слово - удаляем только его
            group = self.tree.item(parent, "text")
            word = self.tree.item(iid, "text")

            if not messagebox.askyesno(
                "Удалить слово",
                f"Удалить слово «{word}» из категории «{group}»?",
                parent=self,
            ):
                return

            dictionary_editor.delete_word(key, group, word)

        else:
            # Выбрана целая категория
            group = self.tree.item(iid, "text")

            usage = dictionary_editor.find_group_usage(key, group)

            if usage:

                preview = ", ".join(usage[:10])

                if len(usage) > 10:
                    preview += f" и ещё {len(usage) - 10}"

                if not messagebox.askyesno(
                    "Категория используется",
                    f"Категория «{group}» используется в товарах: "
                    f"{preview}.\n\n"
                    f"После удаления система перестанет узнавать "
                    f"этот факт для этих товаров (их dropdown-"
                    f"варианты перестанут срабатывать автоматически). "
                    f"Удалить всё равно?",
                    parent=self,
                    icon="warning",
                ):
                    return

            else:

                if not messagebox.askyesno(
                    "Удалить категорию",
                    f"Удалить категорию «{group}» целиком "
                    f"(вместе со всеми словами в ней)?",
                    parent=self,
                ):
                    return

            dictionary_editor.delete_category(key, group)

        self._reload_tree()


class VariantEditorWindow(Toplevel):
    """
    Редактор match-слов и group у dropdown-вариантов КОНКРЕТНОГО
    товара (dictionaries/products.py, dropdown.variants[]) - в
    отличие от DictionaryEditorWindow выше (общие словари материал/
    пол/характеристика на ВСЕ товары), это поле внутри отдельного
    товара, и до этого правилось только руками в products.py -
    match пополнялся только автоматически через обучение, а group
    часто оставался заглушкой "other" (см.
    products-dict-gradation-audit.md).

    Как и DictionaryEditorWindow - самостоятельный инструмент, не
    привязан к текущему прогону, каждое действие сразу пишется на
    диск (dictionaries/products.py) через
    learning/dictionary_editor.py.
    """

    def __init__(self, parent, initial_product=None):

        super().__init__(parent)

        self.title("Редактор match / group")
        self.geometry("680x860")
        self.transient(parent)

        self.current_product = None

        container = ttk.Frame(self, padding=10)
        container.pack(fill=BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(2, weight=1)

        # --------------------------------------------------
        # Поиск товара (обычный combobox на 1500+ товаров неюзабелен)
        # --------------------------------------------------
        search_frame = ttk.Frame(container)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Товар:").grid(
            row=0, column=0, sticky="w"
        )

        self.product_query_var = StringVar()
        query_entry = ttk.Entry(
            search_frame, textvariable=self.product_query_var
        )
        query_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        query_entry.bind("<KeyRelease>", lambda event: self._refresh_matches())

        matches_frame = ttk.Frame(container)
        matches_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        matches_frame.columnconfigure(0, weight=1)

        self.matches_list = Listbox(matches_frame, height=5)
        self.matches_list.grid(row=0, column=0, sticky="ew")
        self.matches_list.bind(
            "<<ListboxSelect>>", lambda event: self._load_selected_product()
        )

        # --------------------------------------------------
        # Дерево: вариант (code — group / name) -> match-слова
        # --------------------------------------------------
        tree_frame = ttk.Frame(container)
        tree_frame.grid(row=2, column=0, sticky="nsew")
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)

        self.tree = ttk.Treeview(tree_frame, show="tree")
        self.tree.grid(row=0, column=0, sticky="nsew")

        vsb = ttk.Scrollbar(
            tree_frame, orient="vertical", command=self.tree.yview
        )
        vsb.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vsb.set)

        # --------------------------------------------------
        # Group у выбранного варианта
        # --------------------------------------------------
        group_frame = ttk.LabelFrame(
            container, text="Group у выбранного варианта", padding=8
        )
        group_frame.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        group_frame.columnconfigure(1, weight=1)

        ttk.Label(group_frame, text="Новое значение:").grid(
            row=0, column=0, sticky="w"
        )
        self.new_group_var = StringVar()
        ttk.Entry(
            group_frame, textvariable=self.new_group_var
        ).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(
            group_frame, text="Сохранить group",
            command=self._save_group,
        ).grid(row=0, column=2)

        # --------------------------------------------------
        # Match-слова
        # --------------------------------------------------
        match_frame = ttk.LabelFrame(
            container, text="Match-слова выбранного варианта", padding=8
        )
        match_frame.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        match_frame.columnconfigure(1, weight=1)

        ttk.Label(match_frame, text="Новое слово:").grid(
            row=0, column=0, sticky="w"
        )
        self.new_match_word_var = StringVar()
        ttk.Entry(
            match_frame, textvariable=self.new_match_word_var
        ).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(
            match_frame, text="Добавить слово",
            command=self._add_match_word,
        ).grid(row=0, column=2)

        ttk.Label(
            match_frame,
            text="Чтобы удалить слово - выберите его в дереве выше и "
            "нажмите «Удалить выбранное слово».",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # --------------------------------------------------
        # Код выбранного варианта (изменить)
        #
        # ИСТОРИЯ ПРАВКИ: раньше редактор умел менять только
        # match/group у УЖЕ существующего варианта - структурные
        # правки (код, добавление/удаление целого варианта, перенос
        # между товарами) можно было сделать только вручную правкой
        # products.py текстом. Это не давало вычистить мусор,
        # накопленный автообучением через слепое слияние по общему
        # коду ТН ВЭД (см. products-dict-gradation-audit.md - вариант
        # "доска" с match-словами карате/шлем/носилки под чужим кодом).
        # --------------------------------------------------
        code_frame = ttk.LabelFrame(
            container, text="Код выбранного варианта", padding=8
        )
        code_frame.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        code_frame.columnconfigure(1, weight=1)

        ttk.Label(code_frame, text="Новый код:").grid(
            row=0, column=0, sticky="w"
        )
        self.new_code_var = StringVar()
        ttk.Entry(
            code_frame, textvariable=self.new_code_var
        ).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(
            code_frame, text="Изменить код",
            command=self._change_variant_code,
        ).grid(row=0, column=2)

        # --------------------------------------------------
        # Новый вариант (добавить в dropdown товара)
        # --------------------------------------------------
        new_variant_frame = ttk.LabelFrame(
            container, text="Добавить новый вариант товару", padding=8
        )
        new_variant_frame.grid(row=6, column=0, sticky="ew", pady=(8, 0))
        new_variant_frame.columnconfigure(1, weight=1)
        new_variant_frame.columnconfigure(3, weight=1)

        ttk.Label(new_variant_frame, text="Код:").grid(
            row=0, column=0, sticky="w"
        )
        self.add_variant_code_var = StringVar()
        ttk.Entry(
            new_variant_frame, textvariable=self.add_variant_code_var, width=14
        ).grid(row=0, column=1, sticky="ew", padx=(6, 6))

        ttk.Label(new_variant_frame, text="Group:").grid(
            row=0, column=2, sticky="w"
        )
        self.add_variant_group_var = StringVar()
        ttk.Entry(
            new_variant_frame, textvariable=self.add_variant_group_var
        ).grid(row=0, column=3, sticky="ew", padx=(6, 6))

        ttk.Label(new_variant_frame, text="Название:").grid(
            row=1, column=0, sticky="w", pady=(4, 0)
        )
        self.add_variant_name_var = StringVar()
        ttk.Entry(
            new_variant_frame, textvariable=self.add_variant_name_var
        ).grid(row=1, column=1, columnspan=2, sticky="ew", padx=(6, 6), pady=(4, 0))

        ttk.Button(
            new_variant_frame, text="Добавить вариант",
            command=self._add_variant,
        ).grid(row=1, column=3, pady=(4, 0))

        # --------------------------------------------------
        # Перенос варианта в другой товар
        # --------------------------------------------------
        move_frame = ttk.LabelFrame(
            container, text="Перенести выбранный вариант в другой товар", padding=8
        )
        move_frame.grid(row=7, column=0, sticky="ew", pady=(8, 0))
        move_frame.columnconfigure(1, weight=1)

        ttk.Label(move_frame, text="Товар-получатель:").grid(
            row=0, column=0, sticky="w"
        )
        self.move_target_var = StringVar()
        ttk.Entry(
            move_frame, textvariable=self.move_target_var
        ).grid(row=0, column=1, sticky="ew", padx=(6, 6))
        ttk.Button(
            move_frame, text="Перенести",
            command=self._move_variant,
        ).grid(row=0, column=2)

        ttk.Label(
            move_frame,
            text="Точное название уже существующего товара - если "
            "вариант приклеился не к тому товару автообучением.",
            foreground="#666666",
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(4, 0))

        bottom = ttk.Frame(container)
        bottom.grid(row=8, column=0, sticky="e", pady=(8, 0))

        ttk.Button(
            bottom, text="Удалить вариант целиком",
            command=self._delete_selected_variant,
        ).pack(side=RIGHT, padx=(6, 0))

        ttk.Button(
            bottom, text="Удалить выбранное слово",
            command=self._delete_selected_word,
        ).pack(side=RIGHT)

        # --------------------------------------------------
        # Открыт напрямую из ProductEditorWindow с уже известным
        # товаром ("Открыть выпадающий список...") - не заставляем
        # куратора искать его заново.
        # --------------------------------------------------
        if initial_product:
            self.product_query_var.set(initial_product)
            self._refresh_matches()
            for index in range(self.matches_list.size()):
                if self.matches_list.get(index) == initial_product:
                    self.matches_list.selection_set(index)
                    self._load_selected_product()
                    break

    # ==========================================================

    def _refresh_matches(self):

        query = self.product_query_var.get()

        self.matches_list.delete(0, END)

        if not query.strip():
            return

        for name in dictionary_editor.find_products(query):
            self.matches_list.insert(END, name)

    def _load_selected_product(self):

        selection = self.matches_list.curselection()

        if not selection:
            return

        product = self.matches_list.get(selection[0])
        self.current_product = product
        self._reload_tree()

    def _reload_tree(self):

        self.tree.delete(*self.tree.get_children())

        if not self.current_product:
            return

        variants = dictionary_editor.list_product_variants(
            self.current_product
        )

        if not variants:
            self.tree.insert(
                "", "end",
                text="(у этого товара нет dropdown-вариантов)",
            )
            return

        for variant in variants:

            code = str(variant.get("code", ""))
            group = str(variant.get("group", ""))
            name = str(variant.get("name", ""))

            label = f"{code} — {group}"

            if name:
                label += f" ({name})"

            # code хранится в самом узле (iid) - им и находим вариант
            # обратно при сохранении group/добавлении слова.
            variant_id = self.tree.insert(
                "", "end", iid=f"variant:{code}", text=label, open=False,
            )

            for word in variant.get("match", []) or []:
                self.tree.insert(variant_id, "end", text=str(word))

    def _selected_variant_code(self):
        """Код варианта, к которому относится текущий выбор - сам
        узел варианта, если выбран он, либо родитель, если выбрано
        match-слово. None, если ничего не выбрано."""

        selection = self.tree.selection()

        if not selection:
            return None

        iid = selection[0]
        parent = self.tree.parent(iid)

        node_id = parent if parent else iid

        if not node_id.startswith("variant:"):
            return None

        return node_id[len("variant:"):]

    def _require_product_and_variant(self):

        if not self.current_product:
            messagebox.showwarning(
                "Редактор match / group",
                "Сначала найдите и выберите товар.",
                parent=self,
            )
            return None

        code = self._selected_variant_code()

        if not code:
            messagebox.showwarning(
                "Редактор match / group",
                "Выберите вариант (или его слово) в дереве.",
                parent=self,
            )
            return None

        return code

    def _save_group(self):

        code = self._require_product_and_variant()

        if not code:
            return

        group = self.new_group_var.get().strip().lower()

        if not group:
            messagebox.showwarning(
                "Редактор match / group",
                "Введите новое значение group.",
                parent=self,
            )
            return

        try:
            dictionary_editor.set_variant_group(
                self.current_product, code, group
            )
        except ValueError as error:
            messagebox.showwarning(
                "Редактор match / group", str(error), parent=self
            )
            return

        self.new_group_var.set("")
        self._reload_tree()

    def _add_match_word(self):

        code = self._require_product_and_variant()

        if not code:
            return

        word = self.new_match_word_var.get().strip().lower()

        if not word:
            messagebox.showwarning(
                "Редактор match / group",
                "Введите слово.",
                parent=self,
            )
            return

        try:
            dictionary_editor.add_match_word(
                self.current_product, code, word
            )
        except ValueError as error:
            messagebox.showwarning(
                "Редактор match / group", str(error), parent=self
            )
            return

        self.new_match_word_var.set("")
        self._reload_tree()

    def _delete_selected_word(self):

        if not self.current_product:
            messagebox.showwarning(
                "Редактор match / group",
                "Сначала найдите и выберите товар.",
                parent=self,
            )
            return

        selection = self.tree.selection()

        if not selection:
            messagebox.showwarning(
                "Редактор match / group",
                "Выберите слово для удаления.",
                parent=self,
            )
            return

        iid = selection[0]
        parent = self.tree.parent(iid)

        if not parent:
            messagebox.showwarning(
                "Редактор match / group",
                "Это узел варианта, а не слово - выберите конкретное "
                "match-слово в дереве.",
                parent=self,
            )
            return

        code = parent[len("variant:"):]
        word = self.tree.item(iid, "text")

        if not messagebox.askyesno(
            "Удалить слово",
            f"Удалить слово «{word}» из match?",
            parent=self,
        ):
            return

        dictionary_editor.delete_match_word(
            self.current_product, code, word
        )
        self._reload_tree()

    def _delete_selected_variant(self):

        code = self._require_product_and_variant()

        if not code:
            return

        if not messagebox.askyesno(
            "Удалить вариант",
            f"Удалить вариант с кодом «{code}» у «{self.current_product}» "
            "целиком (код, name и все match-слова)? Отменить нельзя.",
            parent=self,
        ):
            return

        try:
            dictionary_editor.delete_variant(self.current_product, code)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор match / group", str(error), parent=self
            )
            return

        self._reload_tree()

    def _change_variant_code(self):

        code = self._require_product_and_variant()

        if not code:
            return

        new_code = self.new_code_var.get().strip()

        if not new_code:
            messagebox.showwarning(
                "Редактор match / group",
                "Введите новый код.",
                parent=self,
            )
            return

        try:
            dictionary_editor.set_variant_code(
                self.current_product, code, new_code
            )
        except ValueError as error:
            messagebox.showwarning(
                "Редактор match / group", str(error), parent=self
            )
            return

        self.new_code_var.set("")
        self._reload_tree()

    def _add_variant(self):

        if not self.current_product:
            messagebox.showwarning(
                "Редактор match / group",
                "Сначала найдите и выберите товар.",
                parent=self,
            )
            return

        code = self.add_variant_code_var.get().strip()

        if not code:
            messagebox.showwarning(
                "Редактор match / group",
                "Введите код нового варианта.",
                parent=self,
            )
            return

        try:
            dictionary_editor.add_variant(
                self.current_product,
                code,
                group=self.add_variant_group_var.get().strip(),
                name=self.add_variant_name_var.get().strip(),
            )
        except ValueError as error:
            messagebox.showwarning(
                "Редактор match / group", str(error), parent=self
            )
            return

        self.add_variant_code_var.set("")
        self.add_variant_group_var.set("")
        self.add_variant_name_var.set("")
        self._reload_tree()

    def _move_variant(self):

        code = self._require_product_and_variant()

        if not code:
            return

        target = self.move_target_var.get().strip()

        if not target:
            messagebox.showwarning(
                "Редактор match / group",
                "Введите точное название товара-получателя.",
                parent=self,
            )
            return

        if not messagebox.askyesno(
            "Перенести вариант",
            f"Перенести вариант с кодом «{code}» из «{self.current_product}» "
            f"в «{target}»?",
            parent=self,
        ):
            return

        try:
            dictionary_editor.move_variant(
                self.current_product, code, target
            )
        except ValueError as error:
            messagebox.showwarning(
                "Редактор match / group", str(error), parent=self
            )
            return

        self.move_target_var.set("")
        self._reload_tree()


class ProductEditorWindow(Toplevel):
    """
    Полный редактор ОДНОГО товара (dictionaries/products.py) -
    название, плоский код, алиасы, паттерны - плюс создание/
    переименование/удаление товара целиком. Открывается напрямую
    кнопкой "Редактор словаря" в главном окне (MainApp.py), рядом с
    "Обучение" - НЕ привязан к прогону обучения, можно открыть в
    любой момент.

    Специально НЕ дублирует редактирование dropdown-вариантов (код/
    group/match/перенос) - для этого уже есть VariantEditorWindow
    выше, кнопка "Открыть выпадающий список..." просто открывает его
    с уже выбранным товаром.

    Как и остальные редакторы в этом файле - каждое действие сразу
    пишется на диск через learning/dictionary_editor.py, без
    отдельной кнопки "Применить".
    """

    def __init__(self, parent):

        super().__init__(parent)

        self.title("Редактор словаря товаров")
        self.geometry("640x760")
        self.transient(parent)

        self.current_product = None

        container = ttk.Frame(self, padding=10)
        container.pack(fill=BOTH, expand=True)
        container.columnconfigure(0, weight=1)

        # --------------------------------------------------
        # Поиск товара - тот же UX, что в VariantEditorWindow.
        # --------------------------------------------------
        search_frame = ttk.Frame(container)
        search_frame.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        search_frame.columnconfigure(1, weight=1)

        ttk.Label(search_frame, text="Товар:").grid(
            row=0, column=0, sticky="w"
        )

        self.product_query_var = StringVar()
        query_entry = ttk.Entry(
            search_frame, textvariable=self.product_query_var
        )
        query_entry.grid(row=0, column=1, sticky="ew", padx=(6, 0))
        query_entry.bind("<KeyRelease>", lambda event: self._refresh_matches())

        ttk.Button(
            search_frame, text="Проблемы словаря...",
            command=self._open_issues,
        ).grid(row=0, column=2, padx=(6, 0))

        matches_frame = ttk.Frame(container)
        matches_frame.grid(row=1, column=0, sticky="ew", pady=(0, 8))
        matches_frame.columnconfigure(0, weight=1)

        self.matches_list = Listbox(matches_frame, height=5)
        self.matches_list.grid(row=0, column=0, sticky="ew")
        self.matches_list.bind(
            "<<ListboxSelect>>", lambda event: self._load_selected_product()
        )

        # --------------------------------------------------
        # Выбранный товар - название/код
        # --------------------------------------------------
        header_frame = ttk.LabelFrame(
            container, text="Выбранный товар", padding=8
        )
        header_frame.grid(row=2, column=0, sticky="ew", pady=(0, 8))
        header_frame.columnconfigure(1, weight=1)

        self.selected_name_var = StringVar(value="(товар не выбран)")
        ttk.Label(
            header_frame, textvariable=self.selected_name_var,
            font=("Segoe UI", 10, "bold"),
        ).grid(row=0, column=0, columnspan=3, sticky="w")

        ttk.Label(header_frame, text="Код:").grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )
        self.code_var = StringVar()
        ttk.Entry(
            header_frame, textvariable=self.code_var
        ).grid(row=1, column=1, sticky="ew", padx=(6, 6), pady=(6, 0))
        ttk.Button(
            header_frame, text="Сохранить код",
            command=self._save_code,
        ).grid(row=1, column=2, pady=(6, 0))

        ttk.Label(
            header_frame,
            text="Если у товара настоящая градация по выпадающему "
            "списку (2+ разных кода среди вариантов) - плоский код "
            "всё равно сбросится при следующем сохранении, это "
            "самозащита, а не ошибка редактора.",
            foreground="#666666", wraplength=560, justify="left",
        ).grid(row=2, column=0, columnspan=3, sticky="w", pady=(4, 0))

        ttk.Label(header_frame, text="Переименовать в:").grid(
            row=3, column=0, sticky="w", pady=(6, 0)
        )
        self.rename_var = StringVar()
        ttk.Entry(
            header_frame, textvariable=self.rename_var
        ).grid(row=3, column=1, sticky="ew", padx=(6, 6), pady=(6, 0))
        ttk.Button(
            header_frame, text="Переименовать",
            command=self._rename_product,
        ).grid(row=3, column=2, pady=(6, 0))

        actions_frame = ttk.Frame(header_frame)
        actions_frame.grid(row=4, column=0, columnspan=3, sticky="e", pady=(8, 0))

        ttk.Button(
            actions_frame, text="Открыть выпадающий список...",
            command=self._open_variant_editor,
        ).pack(side=LEFT, padx=(0, 6))
        ttk.Button(
            actions_frame, text="Удалить товар...",
            command=self._delete_product,
        ).pack(side=LEFT)

        # --------------------------------------------------
        # Алиасы
        # --------------------------------------------------
        alias_frame = ttk.LabelFrame(container, text="Алиасы", padding=8)
        alias_frame.grid(row=3, column=0, sticky="nsew", pady=(0, 8))
        alias_frame.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        self.alias_list = Listbox(alias_frame, height=6)
        self.alias_list.grid(row=0, column=0, columnspan=3, sticky="nsew")
        alias_frame.rowconfigure(0, weight=1)

        self.new_alias_var = StringVar()
        ttk.Entry(
            alias_frame, textvariable=self.new_alias_var
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(6, 0))
        ttk.Button(
            alias_frame, text="Добавить",
            command=self._add_alias,
        ).grid(row=1, column=1, pady=(6, 0))
        ttk.Button(
            alias_frame, text="Удалить выбранный",
            command=self._delete_selected_alias,
        ).grid(row=1, column=2, pady=(6, 0))

        # --------------------------------------------------
        # Паттерны
        # --------------------------------------------------
        pattern_frame = ttk.LabelFrame(container, text="Паттерны (регулярные выражения)", padding=8)
        pattern_frame.grid(row=4, column=0, sticky="nsew", pady=(0, 8))
        pattern_frame.columnconfigure(0, weight=1)
        container.rowconfigure(4, weight=1)

        self.pattern_list = Listbox(pattern_frame, height=5)
        self.pattern_list.grid(row=0, column=0, columnspan=3, sticky="nsew")
        pattern_frame.rowconfigure(0, weight=1)

        self.new_pattern_var = StringVar()
        ttk.Entry(
            pattern_frame, textvariable=self.new_pattern_var
        ).grid(row=1, column=0, sticky="ew", padx=(0, 6), pady=(6, 0))
        ttk.Button(
            pattern_frame, text="Добавить",
            command=self._add_pattern,
        ).grid(row=1, column=1, pady=(6, 0))
        ttk.Button(
            pattern_frame, text="Удалить выбранный",
            command=self._delete_selected_pattern,
        ).grid(row=1, column=2, pady=(6, 0))

        # --------------------------------------------------
        # Новый товар
        # --------------------------------------------------
        new_frame = ttk.LabelFrame(container, text="Создать новый товар", padding=8)
        new_frame.grid(row=5, column=0, sticky="ew")
        new_frame.columnconfigure(1, weight=1)
        new_frame.columnconfigure(3, weight=1)

        ttk.Label(new_frame, text="Название:").grid(row=0, column=0, sticky="w")
        self.create_name_var = StringVar()
        ttk.Entry(
            new_frame, textvariable=self.create_name_var
        ).grid(row=0, column=1, sticky="ew", padx=(6, 6))

        ttk.Label(new_frame, text="Код (необязательно):").grid(
            row=0, column=2, sticky="w"
        )
        self.create_code_var = StringVar()
        ttk.Entry(
            new_frame, textvariable=self.create_code_var, width=14
        ).grid(row=0, column=3, sticky="ew", padx=(6, 6))

        ttk.Button(
            new_frame, text="Создать",
            command=self._create_product,
        ).grid(row=0, column=4)

    # ==========================================================
    # ПОИСК / ВЫБОР ТОВАРА
    # ==========================================================

    def _refresh_matches(self):

        query = self.product_query_var.get()

        self.matches_list.delete(0, END)

        if not query.strip():
            return

        for name in dictionary_editor.find_products(query):
            self.matches_list.insert(END, name)

    def _load_selected_product(self):

        selection = self.matches_list.curselection()

        if not selection:
            return

        self._select_product(self.matches_list.get(selection[0]))

    def _select_product(self, product):

        self.current_product = product
        self.selected_name_var.set(product)
        self.rename_var.set("")

        importlib.invalidate_caches()
        importlib.reload(dictionary_editor.products_module)
        info = dictionary_editor.products_module.PRODUCTS.get(product) or {}

        self.code_var.set(str(info.get("code", "")))

        self.alias_list.delete(0, END)
        for alias in info.get("aliases", []) or []:
            self.alias_list.insert(END, alias)

        self.pattern_list.delete(0, END)
        for pattern in info.get("patterns", []) or []:
            self.pattern_list.insert(END, pattern)

    def _require_product(self):

        if not self.current_product:
            messagebox.showwarning(
                "Редактор словаря товаров",
                "Сначала найдите и выберите товар.",
                parent=self,
            )
            return None

        return self.current_product

    # ==========================================================
    # КОД / ПЕРЕИМЕНОВАНИЕ / УДАЛЕНИЕ ТОВАРА
    # ==========================================================

    def _save_code(self):

        product = self._require_product()
        if not product:
            return

        try:
            dictionary_editor.set_product_code(product, self.code_var.get())
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словаря товаров", str(error), parent=self
            )
            return

        self._select_product(product)

    def _rename_product(self):

        product = self._require_product()
        if not product:
            return

        new_name = self.rename_var.get().strip()

        if not new_name:
            messagebox.showwarning(
                "Редактор словаря товаров",
                "Введите новое название.",
                parent=self,
            )
            return

        try:
            dictionary_editor.rename_product(product, new_name)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словаря товаров", str(error), parent=self
            )
            return

        self.product_query_var.set(new_name)
        self._refresh_matches()
        self._select_product(new_name)

    def _delete_product(self):

        product = self._require_product()
        if not product:
            return

        if not messagebox.askyesno(
            "Редактор словаря товаров",
            f"Удалить товар «{product}» целиком - вместе с кодом, "
            "алиасами, паттернами и выпадающим списком (если есть)? "
            "Отменить нельзя.",
            parent=self,
        ):
            return

        try:
            dictionary_editor.delete_product(product)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словаря товаров", str(error), parent=self
            )
            return

        self.current_product = None
        self.selected_name_var.set("(товар не выбран)")
        self.code_var.set("")
        self.alias_list.delete(0, END)
        self.pattern_list.delete(0, END)
        self._refresh_matches()

    def _create_product(self):

        name = self.create_name_var.get()
        code = self.create_code_var.get()

        try:
            dictionary_editor.create_product(name, code)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словаря товаров", str(error), parent=self
            )
            return

        created_name = name.strip()
        self.create_name_var.set("")
        self.create_code_var.set("")
        self.product_query_var.set(created_name)
        self._refresh_matches()
        self._select_product(created_name)

    # ==========================================================
    # АЛИАСЫ
    # ==========================================================

    def _add_alias(self):

        product = self._require_product()
        if not product:
            return

        alias = self.new_alias_var.get().strip().lower()

        if not alias:
            return

        collisions = dictionary_editor.check_alias_collision(product, alias)

        if collisions:
            if not messagebox.askyesno(
                "Возможная коллизия",
                f"«{alias}» уже используется у: {', '.join(collisions)} - "
                "как название товара или чужой алиас. Один и тот же текст "
                "описания может начать путаться между товарами.\n\n"
                "Всё равно добавить?",
                parent=self,
            ):
                return

        try:
            dictionary_editor.add_alias(product, alias)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словаря товаров", str(error), parent=self
            )
            return

        self.new_alias_var.set("")
        self._select_product(product)

    def _delete_selected_alias(self):

        product = self._require_product()
        if not product:
            return

        selection = self.alias_list.curselection()

        if not selection:
            messagebox.showwarning(
                "Редактор словаря товаров",
                "Выберите алиас в списке.",
                parent=self,
            )
            return

        alias = self.alias_list.get(selection[0])
        dictionary_editor.delete_alias(product, alias)
        self._select_product(product)

    # ==========================================================
    # ПАТТЕРНЫ
    # ==========================================================

    def _add_pattern(self):

        product = self._require_product()
        if not product:
            return

        pattern = self.new_pattern_var.get().strip()

        if not pattern:
            return

        try:
            dictionary_editor.add_pattern(product, pattern)
        except ValueError as error:
            messagebox.showwarning(
                "Редактор словаря товаров", str(error), parent=self
            )
            return

        self.new_pattern_var.set("")
        self._select_product(product)

    def _delete_selected_pattern(self):

        product = self._require_product()
        if not product:
            return

        selection = self.pattern_list.curselection()

        if not selection:
            messagebox.showwarning(
                "Редактор словаря товаров",
                "Выберите паттерн в списке.",
                parent=self,
            )
            return

        pattern = self.pattern_list.get(selection[0])
        dictionary_editor.delete_pattern(product, pattern)
        self._select_product(product)

    # ==========================================================
    # ВЫПАДАЮЩИЙ СПИСОК / ДИАГНОСТИКА
    # ==========================================================

    def _open_variant_editor(self):

        product = self._require_product()
        if not product:
            return

        VariantEditorWindow(self, initial_product=product)

    def _open_issues(self):

        DictionaryIssuesWindow(self)


class DictionaryIssuesWindow(Toplevel):
    """
    Диагностика живого словаря - коллизии алиасов (тот же класс
    проблемы, что "держатель"/"поло", см. products-dict-gradation-
    audit.md) и товары-дубли с разницей только в пробелах/регистре
    (найдено при ревизии 2026-09-24, например 'абажур'/'абажур ').

    Ничего не правит сама - только показывает, чтобы куратор мог
    пройтись по списку и решить по каждому случаю (двойным кликом
    открывает товар в ProductEditorWindow-родителе для правки)."""

    def __init__(self, parent):

        super().__init__(parent)

        self.parent_editor = parent

        self.title("Проблемы словаря")
        self.geometry("760x560")
        self.transient(parent)

        container = ttk.Frame(self, padding=10)
        container.pack(fill=BOTH, expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(1, weight=1)
        container.rowconfigure(3, weight=1)

        ttk.Label(
            container,
            text="Алиас совпадает с названием/алиасом ДРУГОГО товара:",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=0, column=0, sticky="w")

        collisions_frame = ttk.Frame(container)
        collisions_frame.grid(row=1, column=0, sticky="nsew", pady=(2, 8))
        collisions_frame.columnconfigure(0, weight=1)
        collisions_frame.rowconfigure(0, weight=1)

        self.collisions_tree = ttk.Treeview(
            collisions_frame, columns=("owners", "collides"), show="tree headings",
        )
        self.collisions_tree.heading("#0", text="Алиас")
        self.collisions_tree.heading("owners", text="У товаров")
        self.collisions_tree.heading("collides", text="Конфликтует с")
        self.collisions_tree.column("#0", width=160)
        self.collisions_tree.grid(row=0, column=0, sticky="nsew")

        vsb1 = ttk.Scrollbar(
            collisions_frame, orient="vertical", command=self.collisions_tree.yview
        )
        vsb1.grid(row=0, column=1, sticky="ns")
        self.collisions_tree.configure(yscrollcommand=vsb1.set)
        self.collisions_tree.bind("<Double-1>", self._open_collision_product)

        ttk.Label(
            container,
            text="Товары-дубли (разное только пробелами/регистром названия):",
            font=("Segoe UI", 9, "bold"),
        ).grid(row=2, column=0, sticky="w")

        dupes_frame = ttk.Frame(container)
        dupes_frame.grid(row=3, column=0, sticky="nsew", pady=(2, 8))
        dupes_frame.columnconfigure(0, weight=1)
        dupes_frame.rowconfigure(0, weight=1)

        self.dupes_tree = ttk.Treeview(dupes_frame, show="tree")
        self.dupes_tree.grid(row=0, column=0, sticky="nsew")

        vsb2 = ttk.Scrollbar(
            dupes_frame, orient="vertical", command=self.dupes_tree.yview
        )
        vsb2.grid(row=0, column=1, sticky="ns")
        self.dupes_tree.configure(yscrollcommand=vsb2.set)
        self.dupes_tree.bind("<Double-1>", self._open_dupe_product)

        ttk.Button(
            container, text="Обновить", command=self._reload,
        ).grid(row=4, column=0, sticky="e")

        ttk.Label(
            container,
            text="Двойной клик по строке открывает товар в редакторе слева "
            "для правки. Список ничего не меняет сам - часть совпадений "
            "может быть намеренной, решать куратору по каждому случаю.",
            foreground="#666666", wraplength=720, justify="left",
        ).grid(row=5, column=0, sticky="w", pady=(4, 0))

        self._reload()

    def _reload(self):

        self.collisions_tree.delete(*self.collisions_tree.get_children())
        self.dupes_tree.delete(*self.dupes_tree.get_children())

        collisions = dictionary_editor.list_alias_collisions()

        for item in collisions:
            self.collisions_tree.insert(
                "", "end",
                text=item["alias"],
                values=(", ".join(item["owners"]), ", ".join(item["collides_with"])),
            )

        near = dictionary_editor.list_near_duplicate_products()

        for group in near:
            node = self.dupes_tree.insert("", "end", text=group["key"], open=True)
            for variant in group["variants"]:
                self.dupes_tree.insert(node, "end", text=repr(variant))

        self.title(
            f"Проблемы словаря - коллизий: {len(collisions)}, "
            f"товаров-дублей: {len(near)}"
        )

    def _open_collision_product(self, event):

        item = self.collisions_tree.focus()

        if not item:
            return

        owners = self.collisions_tree.item(item, "values")[0]
        first_owner = owners.split(", ")[0] if owners else ""

        if first_owner and hasattr(self.parent_editor, "_select_product"):
            self.parent_editor.product_query_var.set(first_owner)
            self.parent_editor._refresh_matches()
            self.parent_editor._select_product(first_owner)

    def _open_dupe_product(self, event):

        item = self.dupes_tree.focus()

        if not item:
            return

        # Двойной клик по конкретному варианту (листу) - у корня
        # (группы) текста в repr-кавычках нет.
        text = self.dupes_tree.item(item, "text")

        if not (text.startswith("'") or text.startswith('"')):
            return

        product = text[1:-1]

        if hasattr(self.parent_editor, "_select_product"):
            self.parent_editor.product_query_var.set(product)
            self.parent_editor._refresh_matches()
            self.parent_editor._select_product(product)


class TrashWordDialog(Toplevel):
    """
    Подтверждение перед отправкой алиаса в мусорный словарь
    (TRASH_MARKETING). Текст редактируемый - если в мусор нужно
    отправить не всю фразу целиком, а только её часть (например,
    из "футболка акции скидки" в мусор должно уйти "акции скидки",
    а не "футболка" - это легитимное слово), куратор может подрезать
    текст перед подтверждением.
    """

    def __init__(self, parent, alias_text):

        super().__init__(parent)

        self.title("В словарь мусора")
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()

        self.result = None

        frame = ttk.Frame(self, padding=12)
        frame.grid(row=0, column=0, sticky="nsew")

        ttk.Label(
            frame,
            text="Добавить в словарь мусора (TRASH_MARKETING):",
        ).grid(row=0, column=0, sticky="w")

        ttk.Label(
            frame,
            text=(
                "Если в мусор нужна не вся фраза, а часть - "
                "подрежьте текст перед подтверждением."
            ),
            foreground="#666666",
        ).grid(row=1, column=0, sticky="w", pady=(2, 8))

        self.text_var = StringVar(value=alias_text)

        entry = ttk.Entry(
            frame,
            textvariable=self.text_var,
            width=50,
        )
        entry.grid(row=2, column=0, sticky="ew", pady=(0, 10))
        entry.focus_set()
        entry.select_range(0, "end")

        buttons = ttk.Frame(frame)
        buttons.grid(row=3, column=0, sticky="e")

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

        self.bind("<Return>", lambda event: self._confirm())
        self.bind("<Escape>", lambda event: self.destroy())

        self.update_idletasks()
        self.geometry(
            f"+{parent.winfo_rootx() + 80}+{parent.winfo_rooty() + 80}"
        )

    def _confirm(self):

        text = self.text_var.get().strip()

        if not text:
            messagebox.showwarning(
                "В словарь мусора",
                "Текст не должен быть пустым.",
                parent=self,
            )
            return

        self.result = text
        self.destroy()