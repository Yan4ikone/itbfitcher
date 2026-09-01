from tkinter import *
from tkinter import ttk, messagebox

from learning.applier import LearningApplier
from learning.review_models import (
    LearningReport,
)


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
        self.selected_materials = set()
        self.selected_dropdowns = set()
        self.selected_dropdown_match_words = set()
        self.selected_dropdown_candidates = set()
        self.selected_patterns = set()
        self.product_rows = {}
        self.alias_rows = {}
        self.material_rows = {}
        self.dropdown_rows = {}
        self.dropdown_match_words_rows = {}
        self.dropdown_candidate_rows = {}
        self.pattern_rows = {}
        self._build_ui()
        self._fill_products()
        self._fill_aliases()
        self._fill_materials()
        self._fill_dropdowns()
        self._fill_dropdown_match_words()
        self._fill_dropdown_candidates()
        self._fill_patterns()
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
        self.materials_frame = ttk.Frame(self.notebook)
        self.dropdowns_frame = ttk.Frame(self.notebook)
        self.dropdown_match_words_frame = ttk.Frame(self.notebook)
        self.dropdown_candidates_frame = ttk.Frame(self.notebook)
        self.patterns_frame = ttk.Frame(self.notebook)
        self.notebook.add(
            self.products_frame,
            text=f"Новые товары ({len(self.report.new_products)})"
        )
        self.notebook.add(
            self.aliases_frame,
            text=f"Алиасы ({len(self.report.new_aliases)})"
        )
        self.notebook.add(
            self.materials_frame,
            text=f"Материалы ({len(self.report.new_material_codes)})"
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
        self.products_tree = self._create_products_tree(
            self.products_frame
        )
        self.alias_tree = self._create_alias_tree(
            self.aliases_frame
        )
        self.material_tree = self._create_material_tree(
            self.materials_frame
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

    def _create_material_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "product",
                "material",
                "code"
            )
        )

        tree.heading("selected", text="✓")
        tree.heading("product", text="Товар")
        tree.heading("material", text="Материал")
        tree.heading("code", text="Код")
        tree.column("selected", width=45, anchor="center")
        tree.column("product", width=240)
        tree.column("material", width=500)
        tree.column("code", width=160)

        return tree

    def _create_dropdown_tree(self, parent):

        tree = self._create_tree(
            parent,
            (
                "selected",
                "product",
                "code",
                "name",
                "match",
            )
        )

        tree.heading("selected", text="✓")
        tree.heading("product", text="Dropdown")
        tree.heading("code", text="Новый код")
        tree.heading("name", text="Название (автозаполнено)")
        tree.heading("match", text="Ключевые слова (автозаполнено)")
        tree.column("selected", width=45, anchor="center")
        tree.column("product", width=250)
        tree.column("code", width=140)
        tree.column("name", width=220)
        tree.column("match", width=350)

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

    def _fill_materials(self):

        for item in self.report.new_material_codes:

            iid = self.material_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.product,
                    item.material,
                    item.code,
                )
            )

            self.material_rows[iid] = item

    def _fill_dropdowns(self):

        for item in self.report.new_dropdown_variants:

            iid = self.dropdown_tree.insert(
                "",
                "end",
                values=(
                    "☐",
                    item.product,
                    item.code,
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

            elif widget is self.material_tree:
                self._toggle_material(iid)

            elif widget is self.dropdown_tree:
                self._toggle_dropdown(iid)

            elif widget is self.dropdown_match_words_tree:
                self._toggle_dropdown_match_words(iid)

            elif widget is self.dropdown_candidate_tree:
                self._toggle_dropdown_candidate(iid)

            elif widget is self.pattern_tree:
                self._toggle_pattern(iid)

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

    def _toggle_material(self, iid):

        item = self.material_rows[iid]

        values = list(
            self.material_tree.item(
                iid,
                "values"
            )
        )

        if item in self.selected_materials:

            self.selected_materials.remove(item)
            values[0] = "☐"

        else:

            self.selected_materials.add(item)
            values[0] = "☑"

        self.material_tree.item(
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
        # 2. МАТЕРИАЛЫ
        # ------------------------------------------------------
        elif current_tab == 2:
            for iid in self.material_rows:
                if self.material_rows[iid] not in self.selected_materials:
                    self._toggle_material(iid)
        # ------------------------------------------------------
        # 3. DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 3:

            for iid in self.dropdown_rows:

                if self.dropdown_rows[iid] not in self.selected_dropdowns:
                    self._toggle_dropdown(iid)

        # ------------------------------------------------------
        # 4. РАСШИРИТЬ DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 4:

            for iid in self.dropdown_match_words_rows:

                if (
                        self.dropdown_match_words_rows[iid]
                        not in self.selected_dropdown_match_words
                ):
                    self._toggle_dropdown_match_words(iid)

        # ------------------------------------------------------
        # 5. НУЖЕН DROPDOWN?
        # ------------------------------------------------------

        elif current_tab == 5:
            for iid in self.dropdown_candidate_rows:
                if (
                        self.dropdown_candidate_rows[iid]
                        not in self.selected_dropdown_candidates
                ):
                    self._toggle_dropdown_candidate(iid)
        # ------------------------------------------------------
        # 6. PATTERNS
        # ------------------------------------------------------
        elif current_tab == 6:
            for iid in self.pattern_rows:
                if self.pattern_rows[iid] not in self.selected_patterns:
                    self._toggle_pattern(iid)


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
        # 2. МАТЕРИАЛЫ
        # ------------------------------------------------------

        elif current_tab == 2:

            for iid in list(self.material_rows):

                if self.material_rows[iid] in self.selected_materials:
                    self._toggle_material(iid)

        # ------------------------------------------------------
        # 3. DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 3:

            for iid in list(self.dropdown_rows):

                if self.dropdown_rows[iid] in self.selected_dropdowns:
                    self._toggle_dropdown(iid)

        # ------------------------------------------------------
        # 4. РАСШИРИТЬ DROPDOWN
        # ------------------------------------------------------

        elif current_tab == 4:

            for iid in list(self.dropdown_match_words_rows):

                if (
                        self.dropdown_match_words_rows[iid]
                        in self.selected_dropdown_match_words
                ):
                    self._toggle_dropdown_match_words(iid)

        # ------------------------------------------------------
        # 5. НУЖЕН DROPDOWN?
        # ------------------------------------------------------

        elif current_tab == 5:

            for iid in list(self.dropdown_candidate_rows):

                if (
                        self.dropdown_candidate_rows[iid]
                        in self.selected_dropdown_candidates
                ):
                    self._toggle_dropdown_candidate(iid)

        # ------------------------------------------------------
        # 6. PATTERNS
        # ------------------------------------------------------

        elif current_tab == 6:
            for iid in list(self.pattern_rows):
                if self.pattern_rows[iid] in self.selected_patterns:
                    self._toggle_pattern(iid)





    # ======================================================
    # APPLY
    # ======================================================

    def apply(self):

        if (
            not self.selected_products
            and not self.selected_aliases
            and not self.selected_materials
            and not self.selected_dropdowns
            and not self.selected_dropdown_match_words
            and not self.selected_dropdown_candidates
            and not self.selected_patterns
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
            materials=list(self.selected_materials),
            dropdowns=list(self.selected_dropdowns),
            patterns=list(self.selected_patterns),
            dropdown_candidates=list(self.selected_dropdown_candidates),
            dropdown_match_words=list(self.selected_dropdown_match_words),
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