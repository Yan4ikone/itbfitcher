import openpyxl
import pandas as pd


def load_dataframe(input_path):

    return pd.read_excel(
        input_path,
        sheet_name=None,
    )


def load_source_sheet(input_path):

    workbook = openpyxl.load_workbook(input_path)

    return workbook.active


def find_sheet(dataframes):

    for name, dataframe in dataframes.items():

        if any(
            "опис" in str(column).lower()
            for column in dataframe.columns
        ):
            return name

    raise Exception(
        "Лист с 'Описание' не найден."
    )


def find_column(dataframe, keyword):

    for column in dataframe.columns:

        if keyword in str(column).lower():
            return column

    return None


def get_columns(dataframe):

    description = find_column(
        dataframe,
        "опис",
    )

    code = find_column(
        dataframe,
        "тнвэд",
    )

    characteristics = find_column(
        dataframe,
        "характер",
    )

    if description is None:
        raise Exception(
            "Колонка 'Описание' не найдена."
        )

    if code is None:
        raise Exception(
            "Колонка 'ТН ВЭД' не найдена."
        )

    return {
        "description": description,
        "code": code,
        "characteristics": characteristics,
    }


def count_rows(dataframe, description_column):

    return sum(

        1

        for value in dataframe[description_column]

        if (
            str(value).strip()
            and str(value).lower() != "nan"
        )

    )


def load_input(input_path):

    workbooks = load_dataframe(
        input_path
    )

    sheet_name = find_sheet(
        workbooks
    )

    dataframe = workbooks[sheet_name]

    columns = get_columns(
        dataframe
    )

    return {
        "sheet_name": sheet_name,
        "dataframe": dataframe,
        "columns": columns,
        "rows": count_rows(
            dataframe,
            columns["description"],
        ),
    }