"""
Вкладка "История": все сгенерированные коды коробов с человекочитаемыми
именами кабинета/сезона/категории, новые сверху.

Заголовки колонок ("Кабинет"/"Сезон"/"Категория") берутся из
настраиваемых названий разделов (dimension_labels) и обновляются
живьём через apply_dimension_labels() при переименовании во вкладке
"Справочники".

Использует QTableView + QAbstractTableModel вместо QTableWidget -
данные хранятся как обычный питоновский список, отрисовываются только
видимые строки, поэтому тысячи записей не подвешивают интерфейс.

"Перепечатать выбранный код" - печатает УЖЕ СУЩЕСТВУЮЩИЙ код повторно
(для случая утери/повреждения физической этикетки). Это НЕ создаёт
новый код и не пишет в базу заново - только рендерит тот же код в PDF.
"""

import os
import sys
import sqlite3

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from db import list_history
from label_render import make_pdf_one_per_page, load_label_settings, register_pdf_font
from dimension_labels import load_dimension_labels
from qr_content import build_qr_content_from_history_row

from openpyxl import Workbook

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTableView, QMessageBox, QFileDialog, QHeaderView, QAbstractItemView,
)
from PySide6.QtCore import Qt, QAbstractTableModel, QModelIndex


class HistoryTableModel(QAbstractTableModel):
    FIELD_KEYS = ["code", "cabinet_name", "season_name", "item_name", "created_at"]

    def __init__(self, rows=None, column_labels=None, parent=None):
        super().__init__(parent)
        self._rows = rows or []
        self.columns = column_labels or ["Код", "Категория 1", "Категория 2", "Категория 3", "Дата создания"]

    def set_columns(self, column_labels: list[str]):
        self.columns = column_labels
        top_left = self.index(0, 0)
        top_right = self.index(0, self.columnCount() - 1)
        self.headerDataChanged.emit(Qt.Horizontal, 0, self.columnCount() - 1)

    def set_rows(self, rows):
        self.beginResetModel()
        self._rows = rows
        self.endResetModel()

    def code_at(self, row_index: int) -> str | None:
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]["code"]
        return None

    def row_at(self, row_index: int):
        if 0 <= row_index < len(self._rows):
            return self._rows[row_index]
        return None

    def rowCount(self, parent=QModelIndex()):
        return len(self._rows)

    def columnCount(self, parent=QModelIndex()):
        return len(self.columns)

    def data(self, index, role=Qt.DisplayRole):
        if not index.isValid() or role != Qt.DisplayRole:
            return None
        row = self._rows[index.row()]
        key = self.FIELD_KEYS[index.column()]
        return row[key]

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role != Qt.DisplayRole:
            return None
        if orientation == Qt.Horizontal:
            return self.columns[section]
        return str(section + 1)


class HistoryTab(QWidget):
    def __init__(self, conn: sqlite3.Connection, parent=None):
        super().__init__(parent)
        self.conn = conn
        self._pdf_font_name = register_pdf_font()

        labels = load_dimension_labels()
        column_labels = ["Код", labels["cabinet"], labels["season"], labels["item"], "Дата создания"]

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(0, 0, 0, 0)

        from PySide6.QtWidgets import QSplitter, QScrollArea, QGroupBox
        splitter = QSplitter(Qt.Horizontal)

        table_widget = QWidget()
        table_layout = QVBoxLayout(table_widget)
        table_layout.addWidget(QLabel("<b>История сгенерированных кодов</b>"))

        self.model = HistoryTableModel(column_labels=column_labels)
        self.view = QTableView()
        self.view.setModel(self.model)
        self.view.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.view.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.view.setSelectionMode(QAbstractItemView.SingleSelection)
        self.view.horizontalHeader().setStretchLastSection(False)
        self.view.setSortingEnabled(False)
        table_layout.addWidget(self.view)

        table_scroll = QScrollArea()
        table_scroll.setWidgetResizable(True)
        table_scroll.setWidget(table_widget)

        side_widget = QWidget()
        side_layout = QVBoxLayout(side_widget)

        self.count_label = QLabel("")
        side_layout.addWidget(self.count_label)

        refresh_btn = QPushButton("Обновить")
        refresh_btn.clicked.connect(self.refresh)
        side_layout.addWidget(refresh_btn)

        export_btn = QPushButton("Экспорт всей истории в Excel")
        export_btn.clicked.connect(self._export_excel)
        side_layout.addWidget(export_btn)

        reprint_btn = QPushButton("Перепечатать выбранный код")
        reprint_btn.setToolTip(
            "Печатает уже существующий код повторно - для случая, если\n"
            "физическая этикетка повреждена или потеряна. НЕ создаёт\n"
            "новый код, база не изменяется."
        )
        reprint_btn.clicked.connect(self._reprint_selected)
        side_layout.addWidget(reprint_btn)

        future_group = QGroupBox("Поиск и фильтры (в разработке)")
        future_layout = QVBoxLayout()
        future_layout.addWidget(QLabel("Будет добавлено позже:\nпоиск по коду, фильтр по\nразделам и дате, сортировка."))
        future_group.setLayout(future_layout)
        side_layout.addWidget(future_group)

        side_layout.addStretch()

        side_scroll = QScrollArea()
        side_scroll.setWidgetResizable(True)
        side_scroll.setWidget(side_widget)

        splitter.addWidget(table_scroll)
        splitter.addWidget(side_scroll)
        splitter.setStretchFactor(0, 3)
        splitter.setStretchFactor(1, 1)

        outer_layout.addWidget(splitter)

        self.refresh()

    def apply_dimension_labels(self, labels: dict):
        self.model.set_columns(["Код", labels["cabinet"], labels["season"], labels["item"], "Дата создания"])

    def refresh(self):
        rows = list_history(self.conn)
        self.model.set_rows(rows)
        self.view.resizeColumnsToContents()
        self.count_label.setText(f"Всего записей: {len(rows)}")

    def _selected_row_index(self) -> int | None:
        indexes = self.view.selectionModel().selectedRows()
        if not indexes:
            return None
        return indexes[0].row()

    def _reprint_selected(self):
        row_index = self._selected_row_index()
        if row_index is None:
            QMessageBox.information(self, "Внимание", "Выберите строку с кодом в таблице слева")
            return

        row = self.model.row_at(row_index)
        if not row:
            return
        code = row["code"]

        path, _ = QFileDialog.getSaveFileName(self, "Перепечатать этикетку", f"{code}_reprint.pdf", "PDF files (*.pdf)")
        if not path:
            return

        try:
            settings = load_label_settings()
            qr_contents = None
            if settings.get("label_type") == "qr":
                labels = load_dimension_labels()
                qr_contents = [build_qr_content_from_history_row(row, labels)]
            make_pdf_one_per_page([code], path, settings, self._pdf_font_name, qr_contents=qr_contents)
            QMessageBox.information(self, "Готово", f"Этикетка перепечатана: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))

    def _export_excel(self):
        rows = list_history(self.conn)
        if not rows:
            QMessageBox.information(self, "Внимание", "История пуста - нечего экспортировать")
            return

        path, _ = QFileDialog.getSaveFileName(self, "Экспорт истории", "history.xlsx", "Excel files (*.xlsx)")
        if not path:
            return

        try:
            wb = Workbook()
            ws = wb.active
            ws.title = "История кодов"
            ws.append(self.model.columns)
            for row in rows:
                ws.append([row["code"], row["cabinet_name"], row["season_name"], row["item_name"], row["created_at"]])
            wb.save(path)
            QMessageBox.information(self, "Готово", f"История сохранена: {path}")
        except Exception as e:
            QMessageBox.critical(self, "Ошибка", str(e))
