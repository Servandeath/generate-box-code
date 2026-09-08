"""
Вкладка "Генератор": слева - выбор кабинета/сезона/категории (сверху),
порядок и состав блоков кода (перетаскиваемый список), настройка даты
(формат/значение), генерация, компактная таблица кодов, экспорт
PDF/Excel. Справа - превью и настройки этикетки (LabelSettingsWidget).

"Порядок и состав кода" - список из 4 блоков (Кабинет/Дата/Блок2/Блок3),
которые можно перетаскивать мышкой для смены порядка в итоговом коде.
Кабинет всегда включён (обязателен - с ним связан суточный счётчик),
у остальных есть чекбокс включения/выключения. 5-й блок (случайное +
порядковый номер) всегда последний, не участвует в списке.
"""

import os
import sys
import sqlite3
from datetime import date as date_cls

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import list_active, get_next_seq, code_exists, add_box_code
from generate_box_code import generate_box_code, format_seq, DATE_FORMATS, DEFAULT_DATE_FORMAT, DEFAULT_BLOCK_ORDER
from label_render import make_pdf_one_per_page, load_label_settings, register_pdf_font
from dimension_labels import load_dimension_labels
from qr_content import build_qr_content
from gui.label_settings_widget import LabelSettingsWidget

from openpyxl import Workbook

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QSpinBox,
    QPushButton, QTableWidget, QTableWidgetItem, QMessageBox, QFileDialog,
    QScrollArea, QSplitter, QHeaderView, QGroupBox, QDateEdit,
    QAbstractItemView, QFrame, QListWidget, QListWidgetItem, QGridLayout,
)
from PySide6.QtCore import Qt, QDate

MAX_ATTEMPTS_PER_CODE = 5

DATE_FORMAT_EXAMPLES = {
    "dd_MM_YYYY": "01_01_2026",
    "dd-MM-YYYY": "01-01-2026",
    "ddMMYY": "010126",
    "YYMMDD": "260101",
    "YYYYMMDD": "20260101",
    "MM_YY": "01_26",
    "MM-YY": "01-26",
    "DMonYY": "1Jan26",
}


BLOCK_DISPLAY_NAMES = {
    "cabinet": None,  # берётся из dimension_labels
    "date": "Дата",
    "season": None,
    "item": None,
}


class GeneratorTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._last_batch = []
        self._code_meta = {}
        self._pdf_font_name = register_pdf_font()

        labels = load_dimension_labels()

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        main_splitter = QSplitter(Qt.Horizontal)

        # ---- левая колонка ----
        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        # ==== верхняя зона: крупные группы (QGroupBox) в сетке ====
        # Двухуровневая группировка: крупная рамка-группа, внутри — мелкие рамки полей.
        top_grid = QGridLayout()
        top_grid.setContentsMargins(4, 2, 4, 2)
        top_grid.setHorizontalSpacing(8)
        top_grid.setVerticalSpacing(2)

        # -- поля (создаём заранее, раскладываем ниже) --
        self.cabinet_combo = QComboBox()
        self.season_combo = QComboBox()
        self.item_combo = QComboBox()
        self.qty_spin = QSpinBox()
        self.qty_spin.setRange(1, 9999)
        self.qty_spin.setValue(1)

        self.cabinet_label_widget = QLabel(f"{labels['cabinet']}")
        self.season_label_widget = QLabel(f"{labels['season']}")
        self.item_label_widget = QLabel(f"{labels['item']}")

        # -- крупная группа "Справочники": внутри 3 мелкие рамки --
        refs_group = QGroupBox("Справочники")
        refs_inner = QHBoxLayout()
        for lbl, combo in (
            (self.cabinet_label_widget, self.cabinet_combo),
            (self.season_label_widget, self.season_combo),
            (self.item_label_widget, self.item_combo),
        ):
            cell = QGroupBox()
            cell_lay = QVBoxLayout()
            cell_lay.setContentsMargins(4, 1, 4, 1)
            cell_lay.addWidget(lbl)
            cell_lay.addWidget(combo)
            cell_lay.addStretch()
            cell.setLayout(cell_lay)
            refs_inner.addWidget(cell)
        refs_group.setLayout(refs_inner)
        top_grid.addWidget(refs_group, 0, 0, 1, 3)

        # -- отдельная группа "Количество" --
        qty_group = QGroupBox("Количество")
        qty_lay = QVBoxLayout()
        qty_lay.setContentsMargins(4, 1, 4, 1)
        qty_lay.addWidget(self.qty_spin)
        qty_lay.addStretch()
        qty_group.setLayout(qty_lay)
        top_grid.addWidget(qty_group, 0, 3)

        # -- поля даты --
        self.date_format_combo = QComboBox()
        for key in DATE_FORMATS:
            self.date_format_combo.addItem(f"{key} ({DATE_FORMAT_EXAMPLES.get(key, '?')})", key)
        idx = self.date_format_combo.findData(DEFAULT_DATE_FORMAT)
        if idx >= 0:
            self.date_format_combo.setCurrentIndex(idx)
        self.date_format_combo.currentIndexChanged.connect(self._update_date_example)

        self.date_edit = QDateEdit(QDate.currentDate())
        self.date_edit.setCalendarPopup(True)
        self.date_edit.dateChanged.connect(self._update_date_example)

        self.date_example_label = QLabel("")
        self.date_example_label.setFixedHeight(28)
        self.date_example_label.setFrameShape(QFrame.StyledPanel)
        self.date_example_label.setContentsMargins(4, 0, 4, 0)

        # -- крупная группа "Дата": Формат + Дата (в ряд) + Пример (снизу) --
        date_group = QGroupBox("Дата")
        date_outer = QVBoxLayout()
        date_row = QHBoxLayout()

        fmt_cell = QGroupBox()
        fmt_lay = QVBoxLayout()
        fmt_lay.setContentsMargins(4, 1, 4, 1)
        fmt_lay.addWidget(QLabel("Формат"))
        fmt_lay.addWidget(self.date_format_combo)
        fmt_lay.addStretch()
        fmt_cell.setLayout(fmt_lay)

        dt_cell = QGroupBox()
        dt_lay = QVBoxLayout()
        dt_lay.setContentsMargins(4, 1, 4, 1)
        dt_lay.addWidget(QLabel("Дата"))
        dt_lay.addWidget(self.date_edit)
        dt_lay.addStretch()
        dt_cell.setLayout(dt_lay)

        date_row.addWidget(fmt_cell)
        date_row.addWidget(dt_cell)
        date_outer.addLayout(date_row)
        date_outer.addWidget(self.date_example_label)
        date_group.setLayout(date_outer)
        top_grid.addWidget(date_group, 1, 0, 1, 2)

        # -- крупная группа "Порядок и состав": список (2 строки высоты) --
        self.block_order_list = QListWidget()
        self.block_order_list.setDragDropMode(QAbstractItemView.InternalMove)
        self.block_order_list.setDefaultDropAction(Qt.MoveAction)
        self.block_order_list.setFlow(QListWidget.LeftToRight)
        self.block_order_list.setMaximumHeight(48)
        self.block_order_list.model().rowsMoved.connect(self._update_date_example)
        self._build_block_items(labels)

        order_group = QGroupBox("Порядок и состав (перетащите)")
        order_lay = QVBoxLayout()
        order_lay.addWidget(self.block_order_list)

        self.full_example_label = QLabel("")
        self.full_example_label.setWordWrap(True)
        self.full_example_label.setFrameShape(QFrame.StyledPanel)
        self.full_example_label.setContentsMargins(4, 0, 4, 0)
        
        order_lay.addWidget(self.full_example_label)
        order_lay.addStretch()
        order_group.setLayout(order_lay)
        top_grid.addWidget(order_group, 1, 2, 1, 2)

        # растяжка колонок
        top_grid.setColumnStretch(0, 3)
        top_grid.setColumnStretch(1, 3)
        top_grid.setColumnStretch(2, 3)
        top_grid.setColumnStretch(3, 2)

        from PySide6.QtWidgets import QSizePolicy
        top_container = QWidget()
        top_container.setLayout(top_grid)
        top_container.setSizePolicy(QSizePolicy.Preferred, QSizePolicy.Maximum)
        left_layout.addWidget(top_container)

        gen_btn = QPushButton("Сгенерировать и записать в БД")
        gen_btn.clicked.connect(self._generate_and_write)
        left_layout.addWidget(gen_btn)

        left_splitter = QSplitter(Qt.Vertical)

        table_container = QWidget()
        table_layout = QVBoxLayout(table_container)
        table_layout.addWidget(QLabel("Сгенерированные коды (выделите строки для печати/экспорта части списка):"))

        self.table = QTableWidget(0, 1)
        self.table.setHorizontalHeaderLabels(["Код короба"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        self.table.horizontalHeader().setStretchLastSection(False)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.ExtendedSelection)
        table_layout.addWidget(self.table)
        left_splitter.addWidget(table_container)

        export_container = QWidget()
        export_layout = QVBoxLayout(export_container)
        export_row = QHBoxLayout()
        self.pdf_btn = QPushButton("Сохранить PDF")
        self.pdf_btn.setToolTip("Печатает выделенные строки; если ничего не выделено - последний сгенерированный пакет")
        self.pdf_btn.clicked.connect(self._save_pdf)
        self.pdf_btn.setEnabled(False)
        self.excel_btn = QPushButton("Экспорт в Excel")
        self.excel_btn.setToolTip("Экспортирует выделенные строки; если ничего не выделено - последний сгенерированный пакет")
        self.excel_btn.clicked.connect(self._save_excel)
        self.excel_btn.setEnabled(False)
        export_row.addWidget(self.pdf_btn)
        export_row.addWidget(self.excel_btn)
        export_layout.addLayout(export_row)
        export_layout.addStretch()
        left_splitter.addWidget(export_container)

        left_splitter.setStretchFactor(0, 3)
        left_splitter.setStretchFactor(1, 1)

        left_layout.addWidget(left_splitter)

        # ---- правая колонка ----
        self.label_settings = LabelSettingsWidget()
        self.label_settings.qr_content_provider = self._preview_qr_content

        right_scroll = QScrollArea()
        right_scroll.setWidgetResizable(True)
        right_scroll.setWidget(self.label_settings)

        main_splitter.addWidget(left_widget)
        main_splitter.addWidget(right_scroll)
        main_splitter.setStretchFactor(0, 1)
        main_splitter.setStretchFactor(1, 1)
        main_splitter.setChildrenCollapsible(False)

        outer_layout.addWidget(main_splitter)

        self.cabinet_combo.currentIndexChanged.connect(self._update_full_example)
        self.season_combo.currentIndexChanged.connect(self._update_full_example)
        self.item_combo.currentIndexChanged.connect(self._update_full_example)
        self.refresh_lists()
        self._update_date_example()

    def _build_block_items(self, labels: dict):
        self.block_order_list.clear()
        block_texts = {
            "cabinet": labels["cabinet"],
            "date": "Дата",
            "season": labels["season"],
            "item": labels["item"],
        }
        for key in DEFAULT_BLOCK_ORDER:
            item = QListWidgetItem(block_texts[key])
            item.setData(Qt.UserRole, key)
            if key == "cabinet":
                # обязателен: чекбокс есть и отмечен, но снять его нельзя
                item.setFlags((item.flags() | Qt.ItemIsUserCheckable) & ~Qt.ItemIsEnabled)
                item.setCheckState(Qt.Checked)
            else:
                item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
                item.setCheckState(Qt.Checked)
            self.block_order_list.addItem(item)

    def apply_dimension_labels(self, labels: dict):
        """Живое обновление подписей полей и списка блоков при переименовании разделов."""
        self.cabinet_label_widget.setText(f"{labels['cabinet']}:")
        self.season_label_widget.setText(f"{labels['season']}:")
        self.item_label_widget.setText(f"{labels['item']}:")

        block_texts = {"cabinet": labels["cabinet"], "season": labels["season"], "item": labels["item"]}
        for i in range(self.block_order_list.count()):
            it = self.block_order_list.item(i)
            key = it.data(Qt.UserRole)
            if key in block_texts:
                it.setText(block_texts[key])

    def _get_block_order_and_flags(self):
        """Читает текущий порядок и состояния чекбоксов из block_order_list."""
        order = []
        include = {"date": True, "season": True, "item": True}
        for i in range(self.block_order_list.count()):
            it = self.block_order_list.item(i)
            key = it.data(Qt.UserRole)
            order.append(key)
            if key != "cabinet":
                include[key] = it.checkState() == Qt.Checked
        return tuple(order), include

    def _on_no_date_toggled(self):
        self._update_date_example()

    def _update_date_example(self, *args):
        _, include = self._get_block_order_and_flags()
        if include["date"]:
            date_key = self.date_format_combo.currentData()
            qd = self.date_edit.date()
            py_date = date_cls(qd.year(), qd.month(), qd.day())
            try:
                formatted = DATE_FORMATS[date_key](py_date)
                self.date_example_label.setText(f"Пример даты: {formatted}")
            except Exception:
                self.date_example_label.setText("Пример даты: -")
        else:
            self.date_example_label.setText("Дата не включена в код")
        self._update_full_example()

    def _update_full_example(self):
        """Собирает структуру кода БЕЗ random-части, в текущем порядке блоков.
        Берёт те же значения, что пойдут в generate_box_code — чтобы не разойтись."""
        order, include = self._get_block_order_and_flags()

        cab = self.cabinet_combo.currentData()
        sea = self.season_combo.currentData()
        itm = self.item_combo.currentData()
        cabinet_code = cab[1] if cab else "?"
        season_code = sea[1] if sea else "?"
        item_code = itm[1] if itm else "?"

        date_key = self.date_format_combo.currentData()
        qd = self.date_edit.date()
        py_date = date_cls(qd.year(), qd.month(), qd.day())
        try:
            date_str = DATE_FORMATS[date_key](py_date)
        except Exception:
            date_str = "?"

        segment_values = {
            "cabinet": cabinet_code,
            "date": date_str if include["date"] else None,
            "season": season_code if include["season"] else None,
            "item": item_code if include["item"] else None,
        }
        parts = [segment_values[k] for k in order if segment_values[k] is not None]
        preview = "_".join(parts) + "_"
        self.full_example_label.setText(f"Пример кода: {preview}")

        # состав/порядок блоков и выбранные разделы влияют на содержимое QR,
        # а объём содержимого - на плотность QR, поэтому превью пересобираем
        label_settings = getattr(self, "label_settings", None)
        if label_settings is not None:
            label_settings.refresh_preview()

    def _preview_qr_content(self, code: str) -> str:
        """Содержимое QR для превью и тестовой печати - из текущего состояния
        вкладки (выбранные разделы, дата, порядок и состав блоков). Номер
        показывается условный: реальный присвоится только при генерации."""
        order, include = self._get_block_order_and_flags()

        cab = self.cabinet_combo.currentData()
        sea = self.season_combo.currentData()
        itm = self.item_combo.currentData()
        values_ru = {
            "cabinet": cab[2] if cab else "-",
            "season": sea[2] if sea else "-",
            "item": itm[2] if itm else "-",
        }

        date_key = self.date_format_combo.currentData()
        qd = self.date_edit.date()
        try:
            date_str = DATE_FORMATS[date_key](date_cls(qd.year(), qd.month(), qd.day()))
        except Exception:
            date_str = ""

        return build_qr_content(
            code, order, include, load_dimension_labels(), values_ru,
            date_str, format_seq(1),
        )

    def refresh_lists(self):
        self.cabinet_combo.clear()
        self.season_combo.clear()
        self.item_combo.clear()
        for row in list_active(self.conn, "cabinets"):
            self.cabinet_combo.addItem(f"{row['name_ru']} ({row['code_latin']})", (row["id"], row["code_latin"], row["name_ru"]))
        for row in list_active(self.conn, "seasons"):
            self.season_combo.addItem(f"{row['name_ru']} ({row['code_latin']})", (row["id"], row["code_latin"], row["name_ru"]))
        for row in list_active(self.conn, "item_types"):
            self.item_combo.addItem(f"{row['name_ru']} ({row['code_latin']})", (row["id"], row["code_latin"], row["name_ru"]))

    def _generate_and_write(self):
        if self.cabinet_combo.count() == 0 or self.season_combo.count() == 0 or self.item_combo.count() == 0:
            QMessageBox.warning(self, "Ошибка", "Сначала добавьте записи во все справочники (вкладка Справочники)")
            return

        cabinet_id, cabinet_code, cabinet_name_ru = self.cabinet_combo.currentData()
        season_id, season_code, season_name_ru = self.season_combo.currentData()
        item_id, item_code, item_name_ru = self.item_combo.currentData()
        qty = self.qty_spin.value()

        block_order, include = self._get_block_order_and_flags()
        include_date = include["date"]
        include_season = include["season"]
        include_item = include["item"]

        date_format = self.date_format_combo.currentData()
        qd = self.date_edit.date()
        gen_date = date_cls(qd.year(), qd.month(), qd.day())
        date_str = DATE_FORMATS[date_format](gen_date) if include_date else ""

        dimension_labels = load_dimension_labels()
        values_ru = {"cabinet": cabinet_name_ru, "season": season_name_ru, "item": item_name_ru}

        start_seq = get_next_seq(self.conn, cabinet_id)

        written_codes = []
        skipped_count = 0

        for offset in range(qty):
            seq = start_seq + offset
            code = None
            for _ in range(MAX_ATTEMPTS_PER_CODE):
                try:
                    candidate = generate_box_code(
                        cabinet_code, season_code, item_code, seq,
                        gen_date=gen_date, include_date=include_date, date_format=date_format,
                        include_season=include_season, include_item=include_item,
                        block_order=block_order,
                    )
                except ValueError as e:
                    QMessageBox.critical(self, "Ошибка генерации", str(e))
                    self._finish_batch(written_codes)
                    return

                if code_exists(self.conn, candidate):
                    continue

                try:
                    add_box_code(self.conn, candidate, cabinet_id, season_id, item_id, seq)
                    code = candidate
                    break
                except sqlite3.IntegrityError:
                    continue

            if code is None:
                skipped_count += 1
                continue

            written_codes.append(code)
            # метаданные для расшифровки QR (см. _qr_content_for_code) -
            # сохраняются на момент генерации, т.к. история (list_history)
            # не хранит порядок/состав блоков и формат даты
            self._code_meta[code] = {
                "order": block_order,
                "include": include,
                "labels": dimension_labels,
                "values_ru": values_ru,
                "date_str": date_str,
                "seq": seq,
            }

        self._finish_batch(written_codes)

        msg = f"Записано в БД: {len(written_codes)}"
        if skipped_count:
            msg += f"\nПропущено из-за дублей (не напечатаны, не записаны): {skipped_count}"
        QMessageBox.information(self, "Готово", msg)

    def _finish_batch(self, codes: list[str]):
        start_row = self.table.rowCount()
        self.table.setRowCount(start_row + len(codes))
        for i, code in enumerate(codes):
            self.table.setItem(start_row + i, 0, QTableWidgetItem(code))
        self.table.resizeColumnsToContents()

        self._last_batch = codes
        has_rows = self.table.rowCount() > 0
        self.pdf_btn.setEnabled(has_rows)
        self.excel_btn.setEnabled(has_rows)

    def _get_export_codes(self) -> list[str]:
        selected_rows = sorted({idx.row() for idx in self.table.selectedIndexes()})
        if selected_rows:
            return [self.table.item(r, 0).text() for r in selected_rows]
        return self._last_batch

    def _qr_content_for_code(self, code: str) -> str | None:
        meta = self._code_meta.get(code)
        if meta is None:
            return None
        return build_qr_content(
            code, meta["order"], meta["include"], meta["labels"],
            meta["values_ru"], meta["date_str"], format_seq(meta["seq"]),
        )

    def _save_pdf(self):
        codes = self._get_export_codes()
        if not codes:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Сохранить этикетки", "labels.pdf", "PDF files (*.pdf)")
        if not path:
            return
        try:
            settings = load_label_settings()
            qr_contents = None
            if settings.get("label_type") == "qr":
                qr_contents = [self._qr_content_for_code(code) for code in codes]
            make_pdf_one_per_page(codes, path, settings, self._pdf_font_name, qr_contents=qr_contents)
            QMessageBox.information(self, "Готово", f"Этикетки сохранены ({len(codes)} шт.): {path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _save_excel(self):
        codes = self._get_export_codes()
        if not codes:
            return
        path, _ = QFileDialog.getSaveFileName(self, "Экспорт в Excel", "codes.xlsx", "Excel files (*.xlsx)")
        if not path:
            return
        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "Коды коробов"
            for code in codes:
                ws.append([code])
            wb.save(path)
            QMessageBox.information(self, "Готово", f"Excel сохранён ({len(codes)} шт.): {path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
