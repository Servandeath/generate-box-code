"""
Галочки «что печатать»: штрихкод, QR или оба. Стоят рядом с каждой
кнопкой печати (генератор, история), выбор между ними общий и
запоминается между запусками.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from label_render import LABEL_TYPES, load_print_types, save_print_types

from PySide6.QtWidgets import QWidget, QHBoxLayout, QLabel, QCheckBox
from PySide6.QtCore import Signal

CAPTIONS = {"barcode": "ШК", "qr": "QR"}


class PrintTypesWidget(QWidget):
    types_changed = Signal(tuple)

    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(QLabel("Печатать:"))

        self.boxes = {}
        for label_type in LABEL_TYPES:
            box = QCheckBox(CAPTIONS[label_type])
            box.toggled.connect(lambda checked, t=label_type: self._on_toggled(t, checked))
            self.boxes[label_type] = box
            layout.addWidget(box)
        layout.addStretch()

        self.set_types(load_print_types())

    def types(self) -> tuple[str, ...]:
        return tuple(t for t, box in self.boxes.items() if box.isChecked())

    def set_types(self, types):
        for label_type, box in self.boxes.items():
            box.blockSignals(True)
            box.setChecked(label_type in types)
            box.blockSignals(False)

    def _on_toggled(self, label_type: str, checked: bool):
        # снять последнюю галочку нельзя - печатать было бы нечего
        if not checked and not self.types():
            self.set_types((label_type,))
            return
        types = self.types()
        save_print_types(types)
        self.types_changed.emit(types)
