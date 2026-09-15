"""Печать на принтер - через PDF-вывод Qt вместо физического принтера:
тот же QPrinter и тот же код рисования, но результат можно проверить."""
import io
import os
import sys

# без QT_QPA_PLATFORM=offscreen: с ним QPrinter на Windows бросает COM-исключение 0x80040155
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import fitz
import pytest
from PySide6.QtPrintSupport import QPrinter
from PySide6.QtWidgets import QApplication

from label_render import DEFAULT_LABEL_SETTINGS, make_pdf_one_per_page, register_pdf_font
from gui.printing import label_page_layout, pages_to_print, render_pdf_to_printer

CODES = ["ALF_16_07_2026_DE_BT_R4N001", "ALF_16_07_2026_DE_BT_X9Z002", "ALF_16_07_2026_DE_BT_K7Q003"]


@pytest.fixture(scope="module")
def qapp():
    return QApplication.instance() or QApplication([])


def _labels_pdf(label_w=58, label_h=40) -> bytes:
    settings = {**DEFAULT_LABEL_SETTINGS, "label_w_mm": label_w, "label_h_mm": label_h}
    buf = io.BytesIO()
    make_pdf_one_per_page(CODES, buf, settings, register_pdf_font(), label_types=("barcode",))
    return buf.getvalue()


def _pdf_printer(path, label_w, label_h) -> QPrinter:
    printer = QPrinter(QPrinter.HighResolution)
    printer.setOutputFormat(QPrinter.PdfFormat)
    printer.setOutputFileName(str(path))
    printer.setPageLayout(label_page_layout(label_w, label_h))
    printer.setFullPage(True)
    return printer


@pytest.mark.parametrize("label_w, label_h", [(58, 40), (40, 58), (50, 50)])
def test_printed_pages_have_exact_label_size(qapp, tmp_path, label_w, label_h):
    out = tmp_path / "printed.pdf"
    printed = render_pdf_to_printer(_pdf_printer(out, label_w, label_h), _labels_pdf(label_w, label_h))

    assert printed == len(CODES)
    with fitz.open(out) as doc:
        assert len(doc) == len(CODES)
        for page in doc:
            assert round(page.rect.width / 72 * 25.4) == label_w
            assert round(page.rect.height / 72 * 25.4) == label_h


def test_printed_label_has_content_not_blank_or_solid(qapp, tmp_path):
    out = tmp_path / "printed.pdf"
    render_pdf_to_printer(_pdf_printer(out, 58, 40), _labels_pdf())

    with fitz.open(out) as doc:
        pix = doc[0].get_pixmap()
    pixels = pix.width * pix.height
    dark = sum(1 for i in range(0, len(pix.samples), pix.n) if pix.samples[i] < 128)
    assert 0 < dark < pixels / 2


def test_all_pages_when_no_range_chosen(qapp, tmp_path):
    printer = _pdf_printer(tmp_path / "all.pdf", 58, 40)
    assert list(pages_to_print(printer, 3)) == [0, 1, 2]


def test_page_range_from_dialog_is_respected(qapp, tmp_path):
    out = tmp_path / "range.pdf"
    printer = _pdf_printer(out, 58, 40)
    printer.setPrintRange(QPrinter.PageRange)
    printer.setFromTo(2, 3)

    assert list(pages_to_print(printer, 3)) == [1, 2]
    assert render_pdf_to_printer(printer, _labels_pdf()) == 2
