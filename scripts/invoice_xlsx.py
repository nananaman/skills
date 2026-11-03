#!/usr/bin/env python3
"""ローカル請求書の対象月設定と、再計算済みコピーの値固定。"""
import argparse
import calendar
import json
import math
import os
import posixpath
import re
import tempfile
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from xml.dom import minidom
from zipfile import ZipFile

from openpyxl import load_workbook
from openpyxl.utils.datetime import to_excel
from openpyxl.styles.numbers import is_date_format
from openpyxl.worksheet.print_settings import PrintArea
from openpyxl.worksheet.cell_range import CellRange
from openpyxl.utils.cell import column_index_from_string

MAIN = 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'
REL = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships'


class InvalidInvoice(ValueError):
    pass


def children(node, name):
    return [n for n in node.childNodes if n.nodeType == n.ELEMENT_NODE and n.localName == name]


def text_value(node):
    return ''.join(n.data for n in node.childNodes if n.nodeType == n.TEXT_NODE)


def remove_children(node, names):
    for child in list(node.childNodes):
        if child.nodeType == child.ELEMENT_NODE and child.localName in names:
            node.removeChild(child)


def element(parent, name, text=None):
    prefix = parent.prefix + ':' if parent.prefix else ''
    result = parent.ownerDocument.createElementNS(MAIN, prefix + name)
    if text is not None:
        result.appendChild(parent.ownerDocument.createTextNode(text))
    parent.appendChild(result)
    return result


def sheet_parts(archive):
    doc = minidom.parseString(archive.read('xl/workbook.xml'))
    rels = minidom.parseString(archive.read('xl/_rels/workbook.xml.rels'))
    targets = {r.getAttribute('Id'): r.getAttribute('Target') for r in rels.documentElement.childNodes if r.nodeType == r.ELEMENT_NODE}
    result = {}
    for sheet in doc.getElementsByTagNameNS(MAIN, 'sheet'):
        target = targets[sheet.getAttributeNS(REL, 'id')]
        path = target.lstrip('/') if target.startswith('/') else posixpath.normpath('xl/' + target)
        result[sheet.getAttribute('name')] = path
    return result


def read_book(path):
    if path.suffix.lower() != '.xlsx':
        raise InvalidInvoice('入力は .xlsx が必要です')
    with ZipFile(path) as archive:
        if any(n.startswith('xl/externalLinks/') or n.endswith('vbaProject.bin') for n in archive.namelist()):
            raise InvalidInvoice('外部リンク・マクロを含むブックは対象外です')
        for name in archive.namelist():
            if name.startswith('xl/tables/') and name.endswith('.xml'):
                table = minidom.parseString(archive.read(name))
                if any(table.getElementsByTagNameNS(MAIN, tag) for tag in ('calculatedColumnFormula', 'totalsRowFormula')):
                    raise InvalidInvoice('テーブル数式を含むブックは対象外です')
    book = load_workbook(path, data_only=False)
    for sheet in book:
        for row in sheet:
            for cell in row:
                if cell.data_type == 'f' and not isinstance(cell.value, str):
                    raise InvalidInvoice('配列数式・データテーブルは対象外です')
    return book


def target_month(value):
    if not re.fullmatch(r'\d{4}-\d{2}', value):
        raise InvalidInvoice('対象月は YYYY-MM で指定してください')
    return date.fromisoformat(value + '-01')


def configured_cell(book, ref):
    sheet, address = ref['sheet'], ref['cell']
    if sheet not in book.sheetnames or not re.fullmatch(r'[A-Z]{1,3}[1-9]\d*', address):
        raise InvalidInvoice('profile のシート名・単一セル参照を確認してください')
    return book[sheet][address]


def write_package(source, output, transform):
    # 検証失敗や途中終了で既存出力を壊さず、既存ファイルは上書きしない。
    if output.exists():
        raise InvalidInvoice('出力先が既に存在します')
    with tempfile.NamedTemporaryFile(dir=output.parent, suffix='.xlsx', delete=False) as tmp:
        temporary = Path(tmp.name)
    try:
        with ZipFile(source) as src, ZipFile(temporary, 'w') as dst:
            for item in src.infolist():
                data = transform(item.filename, src.read(item.filename))
                if data is not None:
                    dst.writestr(item, data)
        # hard link の作成は既存出力へ置換しないため、同時実行でも上書きしない。
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)


def date_assignments(book, profile, dates):
    if not profile['date_inputs']:
        raise InvalidInvoice('date_inputs に設定対象セルが必要です')
    result = {}
    for ref in profile['date_inputs']:
        cell = configured_cell(book, ref)
        key = (ref['sheet'], ref['cell'])
        if key in result or cell.value is None or not is_date_format(cell.number_format):
            raise InvalidInvoice('date_inputs は重複しない既存の日付書式セルを指定してください')
        source = ref['value']
        if source not in dates or dates[source] is None:
            raise InvalidInvoice('date_inputs に対応する明示的な日付引数が必要です')
        result[key] = dates[source]
    return result


def print_areas(book, profile):
    result = {}
    for name, value in profile.get('print_areas', {}).items():
        if name not in book.sheetnames:
            raise InvalidInvoice('print_areas のシート名を確認してください')
        area = PrintArea([value])
        area.title = name
        if not str(area):
            raise InvalidInvoice('print_areas に明示的なセル範囲が必要です')
        result[name] = str(area)
    return result


def layout_changes(book, profile):
    result = profile.get('layout', {})
    for name, spec in result.items():
        sheet = book[name]
        if set(spec) - {'column_widths', 'merge_ranges'}:
            raise InvalidInvoice('layout の設定名を確認してください')
        for column, width in spec.get('column_widths', {}).items():
            if not re.fullmatch('[A-Z]{1,3}', column) or isinstance(width, bool) or not isinstance(width, (int, float)) or not math.isfinite(width) or width <= 0:
                raise InvalidInvoice('列幅は列名と正の有限数で指定してください')
            column_index_from_string(column)
        merged = list(sheet.merged_cells.ranges)
        for address in spec.get('merge_ranges', []):
            area = CellRange(address)
            if area.title or any(not area.isdisjoint(old) and area != old for old in merged):
                raise InvalidInvoice('結合範囲が既存または指定した結合と重なります')
            for row in sheet.iter_rows(min_row=area.min_row, max_row=area.max_row, min_col=area.min_col, max_col=area.max_col):
                for cell in row:
                    if (cell.row, cell.column) != (area.min_row, area.min_col) and cell.value is not None:
                        raise InvalidInvoice('結合先に空白でないセルがあります')
            merged.append(area)
    return result


def place_before(parent, node, following):
    for other in list(parent.childNodes):
        if other.nodeType == other.ELEMENT_NODE and other is not node and other.localName in following:
            parent.insertBefore(node, other)
            break


def apply_layout(doc, spec):
    root = doc.documentElement
    for column, width in spec.get('column_widths', {}).items():
        index = column_index_from_string(column)
        containers = children(root, 'cols')
        cols = containers[0] if containers else element(root, 'cols')
        place_before(root, cols, {'sheetData'})
        matches = [c for c in children(cols, 'col') if int(c.getAttribute('min')) <= index <= int(c.getAttribute('max'))]
        if len(matches) > 1:
            raise InvalidInvoice('重複した列定義は調整できません')
        if matches:
            node = matches[0]
            first, last = int(node.getAttribute('min')), int(node.getAttribute('max'))
            for low, high in ((first, index - 1), (index + 1, last)):
                if low <= high:
                    clone = node.cloneNode(deep=True)
                    clone.setAttribute('min', str(low))
                    clone.setAttribute('max', str(high))
                    cols.appendChild(clone)
        else:
            node = element(cols, 'col')
        for key, value in {'min': index, 'max': index, 'width': width, 'customWidth': 1, 'bestFit': 0}.items():
            node.setAttribute(key, str(value))
        for child in sorted(children(cols, 'col'), key=lambda c: int(c.getAttribute('min'))):
            cols.appendChild(child)
    for address in spec.get('merge_ranges', []):
        address = str(CellRange(address))
        containers = children(root, 'mergeCells')
        merged = containers[0] if containers else element(root, 'mergeCells')
        place_before(root, merged, {'phoneticPr', 'conditionalFormatting', 'dataValidations', 'hyperlinks', 'printOptions', 'pageMargins', 'pageSetup', 'headerFooter', 'rowBreaks', 'colBreaks', 'customProperties', 'cellWatches', 'ignoredErrors', 'smartTags', 'drawing', 'legacyDrawing', 'legacyDrawingHF', 'picture', 'oleObjects', 'controls', 'webPublishItems', 'tableParts', 'extLst'})
        if address not in {n.getAttribute('ref') for n in children(merged, 'mergeCell')}:
            element(merged, 'mergeCell').setAttribute('ref', address)
        merged.setAttribute('count', str(len(children(merged, 'mergeCell'))))


def without_calc_chain(name, data):
    if name == 'xl/calcChain.xml':
        return None
    if name in ('xl/_rels/workbook.xml.rels', '[Content_Types].xml'):
        doc = minidom.parseString(data)
        removed = False
        for node in list(doc.documentElement.childNodes):
            if node.nodeType != node.ELEMENT_NODE:
                continue
            if node.getAttribute('Type').endswith('/calcChain') or node.getAttribute('PartName') == '/xl/calcChain.xml':
                doc.documentElement.removeChild(node)
                removed = True
        return doc.toxml(encoding='utf-8') if removed else data
    return data


def prepare(source, output, profile, dates):
    book = read_book(source)
    assignments = date_assignments(book, profile, dates)
    areas = print_areas(book, profile)
    layouts = layout_changes(book, profile)
    with ZipFile(source) as archive:
        parts = sheet_parts(archive)
    writes = {(parts[sheet], address): value for (sheet, address), value in assignments.items()}
    sheet_paths = set(parts.values())
    layout_parts = {parts[name]: spec for name, spec in layouts.items()}

    def transform(name, data):
        data = without_calc_chain(name, data)
        if data is None:
            return None
        if name not in sheet_paths and name != 'xl/workbook.xml':
            return data
        doc = minidom.parseString(data)
        if name == 'xl/workbook.xml':
            calc = doc.getElementsByTagNameNS(MAIN, 'calcPr')
            calc = calc[0] if calc else element(doc.documentElement, 'calcPr')
            for key, value in {'calcMode': 'auto', 'fullCalcOnLoad': '1', 'forceFullCalc': '1'}.items():
                calc.setAttribute(key, value)
            if areas:
                names = doc.getElementsByTagNameNS(MAIN, 'definedNames')
                if names:
                    names = names[0]
                else:
                    names = element(doc.documentElement, 'definedNames')
                    doc.documentElement.insertBefore(names, calc)
                for sheet_name, area in areas.items():
                    sheet_id = str(book.sheetnames.index(sheet_name))
                    for node in list(children(names, 'definedName')):
                        if node.getAttribute('name') == '_xlnm.Print_Area' and node.getAttribute('localSheetId') == sheet_id:
                            names.removeChild(node)
                    node = element(names, 'definedName', area)
                    node.setAttribute('name', '_xlnm.Print_Area')
                    node.setAttribute('localSheetId', sheet_id)
        else:
            for node in doc.getElementsByTagNameNS(MAIN, 'c'):
                if children(node, 'f'):
                    remove_children(node, {'v'})
                key = (name, node.getAttribute('r'))
                if key in writes:
                    if any(f.getAttribute('t') == 'shared' for f in children(node, 'f')):
                        raise InvalidInvoice('共有数式セルの日付固定は対象外です')
                    # profile が指定したセルだけ、元の数式を明示日付へ置換する。
                    remove_children(node, {'f', 'v', 'is'})
                    node.setAttribute('t', 'n')
                    element(node, 'v', str(to_excel(writes[key], book.epoch)))
        if name in layout_parts:
            apply_layout(doc, layout_parts[name])
        return doc.toxml(encoding='utf-8')

    write_package(source, output, transform)
    return {'stage': 'prepared', 'date_inputs_set': len(assignments), 'print_areas_set': len(areas), 'recalculation_required': True}


def signature(book):
    return {sheet.title: {cell.coordinate: (cell.data_type, cell.value) for row in sheet for cell in row if cell.value is not None} for sheet in book}


def defined_names(path):
    with ZipFile(path) as archive:
        doc = minidom.parseString(archive.read('xl/workbook.xml'))
    result = []
    for node in doc.getElementsByTagNameNS(MAIN, 'definedName'):
        # 確認済みの既定 false 属性だけ、未指定と明示 false/0 を同値にする。
        attributes = tuple(sorted((name, value) for name, value in node.attributes.items()
                                  if not (name in {'function', 'hidden', 'vbProcedure'} and value in {'false', '0'})))
        result.append((attributes, text_value(node)))
    return sorted(result)


def print_settings(sheet):
    return tuple(str(value) for value in (sheet.print_area, sheet.page_setup, sheet.page_margins, sheet.print_options, sheet.print_title_rows, sheet.print_title_cols, sheet.sheet_properties.pageSetUpPr, sheet.row_breaks, sheet.col_breaks))


def inspect(book, profile, dates):
    month = dates['month_start']
    assignments = date_assignments(book, profile, dates)
    for (sheet, address), expected in assignments.items():
        value = book[sheet][address].value
        if isinstance(value, datetime):
            value = value.date()
        if value != expected:
            raise InvalidInvoice('設定日付と一致しません: ' + address)
    for ref in profile['date_checks']:
        offset = ref.get('month_offset', 0)
        index = month.year * 12 + month.month - 1 + offset
        year, m = divmod(index, 12)
        m += 1
        day = ref['day']
        if day not in ('first', 'last'):
            raise InvalidInvoice('date_checks.day は first または last が必要です')
        expected = date(year, m, 1 if day == 'first' else calendar.monthrange(year, m)[1])
        value = configured_cell(book, ref).value
        if isinstance(value, datetime):
            value = value.date()
        if value != expected:
            raise InvalidInvoice('日付検査に失敗しました: ' + ref['cell'])
    if not profile['amount_cells'] or not profile['print_sheets']:
        raise InvalidInvoice('金額セルと印刷対象シートの指定が必要です')
    for ref in profile['amount_cells']:
        value = configured_cell(book, ref).value
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            raise InvalidInvoice('金額が有限の数値ではありません: ' + ref['cell'])
        if 'expected' in ref and Decimal(str(value)) != Decimal(str(ref['expected'])):
            raise InvalidInvoice('期待金額と一致しません: ' + ref['cell'])
    for name in profile['print_sheets']:
        sheet = book[name]
        if not sheet.print_area:
            raise InvalidInvoice('印刷範囲が未設定です。profile.print_areas で確認した範囲を指定してください')
        if sheet.sheet_state != 'visible' or not sheet.page_setup.paperSize or not sheet.page_setup.orientation:
            raise InvalidInvoice('表示状態・用紙・向きを確認してください')
    for name, area in print_areas(book, profile).items():
        if str(book[name].print_area) != area:
            raise InvalidInvoice('profile.print_areas と印刷範囲が一致しません')
    return len(assignments) + len(profile['date_checks'])


def export(prepared, recalculated, output, profile, dates):
    before, after = read_book(prepared), read_book(recalculated)
    if signature(before) != signature(after) or defined_names(prepared) != defined_names(recalculated):
        raise InvalidInvoice('再計算前後で入力値・数式が変わっています')
    if before.epoch != after.epoch:
        raise InvalidInvoice('再計算前後で日付基準が変わっています')
    with ZipFile(prepared) as archive:
        parts = sheet_parts(archive)
        for path in parts.values():
            doc = minidom.parseString(archive.read(path))
            if any(children(node, 'v') for node in doc.getElementsByTagNameNS(MAIN, 'c') if children(node, 'f')):
                raise InvalidInvoice('prepare で作成した未計算ブックを指定してください')
    caches = {}
    with ZipFile(recalculated) as archive:
        for sheet, path in sheet_parts(archive).items():
            doc = minidom.parseString(archive.read(path))
            for node in doc.getElementsByTagNameNS(MAIN, 'c'):
                if node.getAttribute('t') == 'e':
                    raise InvalidInvoice('Excel エラーを含むセルがあります')
                if not children(node, 'f'):
                    continue
                values = children(node, 'v')
                kind = node.getAttribute('t')
                if not values or (kind != 'str' and not text_value(values[0]).strip()):
                    raise InvalidInvoice('数式の計算キャッシュがありません: ' + node.getAttribute('r'))
                value = text_value(values[0])
                if kind in ('', 'n') and not math.isfinite(float(value)):
                    raise InvalidInvoice('数式の計算結果が有限ではありません')
                if kind == 'b' and value not in ('0', '1'):
                    raise InvalidInvoice('真偽値キャッシュが不正です')
                if kind not in ('', 'n', 'b', 'str', 'd'):
                    raise InvalidInvoice('未対応のキャッシュ形式です')
                caches[(parts[sheet], node.getAttribute('r'))] = (kind, value)
    paths = set(parts.values())
    formula_count = 0

    def transform(name, data):
        nonlocal formula_count
        data = without_calc_chain(name, data)
        if data is None:
            return None
        if name not in paths:
            return data
        doc = minidom.parseString(data)
        for node in doc.getElementsByTagNameNS(MAIN, 'c'):
            if node.getAttribute('t') == 'e':
                raise InvalidInvoice('Excel エラーを含むセルがあります')
            if not children(node, 'f'):
                continue
            kind, value = caches[(name, node.getAttribute('r'))]
            remove_children(node, {'f', 'v', 'is'})
            node.setAttribute('t', kind or 'n')
            if kind == 'str':
                node.setAttribute('t', 'inlineStr')
                text = element(element(node, 'is'), 't', value)
                text.setAttribute('xml:space', 'preserve')
            else:
                element(node, 'v', value)
            formula_count += 1
        return doc.toxml(encoding='utf-8')

    # 一時出力で全検査を済ませてから、最終名を作る。
    with tempfile.TemporaryDirectory(dir=output.parent) as directory:
        candidate = Path(directory) / 'checked.xlsx'
        write_package(prepared, candidate, transform)
        final = load_workbook(candidate, data_only=True)
        date_check_count = inspect(final, profile, dates)
        for sheet in before:
            if print_settings(sheet) != print_settings(final[sheet.title]):
                raise InvalidInvoice('値固定後に元の印刷設定が変わっています')
        if any(cell.data_type == 'f' for sheet in read_book(candidate) for row in sheet for cell in row):
            raise InvalidInvoice('数式が残っています')
        os.link(candidate, output)
    return {'stage': 'exported', 'formulas_frozen': formula_count, 'date_checks': date_check_count, 'amount_checks': len(profile['amount_cells']), 'print_settings_checked': True, 'print_preview': 'manual_required'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest='command', required=True)
    for name in ('prepare', 'export'):
        command = commands.add_parser(name)
        command.add_argument('source', type=Path)
        if name == 'export':
            command.add_argument('recalculated', type=Path)
        command.add_argument('output', type=Path)
        command.add_argument('--profile', type=Path, required=True)
        command.add_argument('--month', required=True)
        command.add_argument('--issue-date', type=date.fromisoformat)
        command.add_argument('--due-date', type=date.fromisoformat)
    args = parser.parse_args()
    try:
        profile = json.loads(args.profile.read_text())
        dates = {'month_start': target_month(args.month), 'issue_date': args.issue_date, 'due_date': args.due_date}
        if args.output.exists():
            raise InvalidInvoice('出力先が既に存在します')
        if args.command == 'prepare':
            report = prepare(args.source, args.output, profile, dates)
        else:
            report = export(args.source, args.recalculated, args.output, profile, dates)
        print(json.dumps(report, ensure_ascii=False))
    except (InvalidInvoice, ValueError, KeyError, TypeError, OSError, InvalidOperation) as error:
        # 入力の値や数式をエラーログへ展開しない。
        message = str(error) if isinstance(error, InvalidInvoice) else 'ファイル形式・profile・出力先を確認してください'
        parser.exit(1, message + '\n')


if __name__ == '__main__':
    main()
