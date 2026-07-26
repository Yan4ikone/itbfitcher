from copy import copy


def copy_sheet(source_ws, target_ws):

    for row in source_ws.iter_rows():

        for cell in row:

            target = target_ws[cell.coordinate]
            target.value = cell.value

            if cell.has_style:
                target._style = copy(cell._style)

            if cell.hyperlink:
                target.hyperlink = cell.hyperlink.target