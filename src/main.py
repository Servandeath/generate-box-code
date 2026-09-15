"""
Точка входа GUI-приложения generate_box_code.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(__file__))

from db import init_db, get_connection
from app_paths import get_resource_path
from gui.references_tab import ReferencesTab
from gui.generator_tab import GeneratorTab
from gui.history_tab import HistoryTab
from gui.settings_tab import SettingsTab
from theme import apply_theme, load_theme_mode
from PySide6.QtWidgets import QApplication, QMainWindow, QTabWidget
from PySide6.QtGui import QIcon


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("generate_box_code")
        self.resize(1100, 650)
        self.setMinimumSize(1050, 650)

        icon_path = get_resource_path("app_icon.ico")
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        init_db()
        self.conn = get_connection()

        self.tabs = QTabWidget()

        self.generator_tab = GeneratorTab(self.conn)
        self.references_tab = ReferencesTab(self.conn)
        # перепечатка из истории идёт по тем же настройкам, что на экране генератора
        self.history_tab = HistoryTab(self.conn, lambda: self.generator_tab.label_settings.settings)

        # выбор «что печатать» общий для обеих вкладок
        self.generator_tab.print_types.types_changed.connect(self.history_tab.print_types.set_types)
        self.history_tab.print_types.types_changed.connect(self.generator_tab.print_types.set_types)

        self.settings_tab = SettingsTab()
        self.tabs.addTab(self.generator_tab, "Генератор")
        self.tabs.addTab(self.history_tab, "История")
        self.tabs.addTab(self.references_tab, "Справочники")
        self.tabs.addTab(self.settings_tab, "Настройки")
        self.tabs.setCurrentWidget(self.generator_tab)
        self.settings_tab.theme_changed.connect(self._apply_theme_live)
        self.tabs.currentChanged.connect(self._on_tab_changed)

        # переименование разделов (кабинет/сезон/категория) применяется
        # живьём на остальных вкладках через этот сигнал
        self.references_tab.labels_changed.connect(self.generator_tab.apply_dimension_labels)
        self.references_tab.labels_changed.connect(self.history_tab.apply_dimension_labels)

        self.setCentralWidget(self.tabs)

    def _on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        if widget is self.generator_tab:
            self.generator_tab.refresh_lists()
        elif widget is self.history_tab:
            self.history_tab.refresh()

    def _apply_theme_live(self, mode: str):
        app = QApplication.instance()
        if app is not None:
            apply_theme(app, mode)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    apply_theme(app, load_theme_mode())
    icon_path = get_resource_path("app_icon.ico")
    if os.path.exists(icon_path):
        app.setWindowIcon(QIcon(icon_path))

    window = MainWindow()
    window.show()
    sys.exit(app.exec())
