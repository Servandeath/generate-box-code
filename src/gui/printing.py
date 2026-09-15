"""
Печать этикеток на принтер через системный диалог: выбор принтера,
копии, диапазон страниц, свойства драйвера.

На принтер уходит тот же PDF, что сохраняется в файл и показывается в
превью: его страницы растеризуются под разрешение принтера и кладутся
на страницу размером с этикетку без полей. Отдельного рендера для
принтера нет - поэтому напечатанное не может разойтись с превью.
"""

from PySide6.QtCore import QMarginsF, QSizeF
from PySide6.QtGui import QImage, QPageLayout, QPageSize, QPainter
from PySide6.QtPrintSupport import QPrintDialog, QPrinter


def label_page_layout(label_w_mm: float, label_h_mm: float) -> QPageLayout:
    # размер как есть + книжная ориентация: с альбомной Qt разворачивает
    # уже горизонтальный размер ещё раз, и 58x40 печатается как 40x58
    size = QPageSize(QSizeF(label_w_mm, label_h_mm), QPageSize.Millimeter, "Этикетка", QPageSize.ExactMatch)
    return QPageLayout(size, QPageLayout.Portrait, QMarginsF(0, 0, 0, 0), QPageLayout.Millimeter)


def pages_to_print(printer: QPrinter, page_count: int) -> range:
    """Индексы страниц, выбранные в диалоге; по умолчанию - все."""
    if printer.printRange() == QPrinter.PageRange and printer.fromPage() > 0:
        return range(printer.fromPage() - 1, min(printer.toPage(), page_count))
    return range(page_count)


def render_pdf_to_printer(printer: QPrinter, pdf_bytes: bytes) -> int:
    """Печатает страницы PDF на уже настроенный принтер. Возвращает число
    напечатанных страниц."""
    import fitz

    zoom = printer.resolution() / 72.0
    printed = 0
    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        painter = QPainter()
        if not painter.begin(printer):
            raise RuntimeError("Не удалось начать печать: принтер недоступен")
        try:
            for index in pages_to_print(printer, len(doc)):
                if printed:
                    printer.newPage()
                pix = doc[index].get_pixmap(matrix=fitz.Matrix(zoom, zoom))
                image = QImage(pix.samples, pix.width, pix.height, pix.stride, QImage.Format_RGB888)
                painter.drawImage(painter.viewport(), image)
                printed += 1
        finally:
            painter.end()
    return printed


def print_pdf_with_dialog(parent, pdf_bytes: bytes, label_w_mm: float, label_h_mm: float) -> int:
    """Показывает системный диалог печати и печатает. Возвращает число
    напечатанных страниц; 0 - если печать отменили."""
    import fitz

    with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
        page_count = len(doc)

    printer = QPrinter(QPrinter.HighResolution)
    printer.setPageLayout(label_page_layout(label_w_mm, label_h_mm))
    printer.setFullPage(True)

    dialog = QPrintDialog(printer, parent)
    dialog.setWindowTitle("Печать этикеток")
    dialog.setMinMax(1, page_count)
    if not dialog.exec():
        return 0
    return render_pdf_to_printer(printer, pdf_bytes)
