import os
import sys
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from label_render import (
    make_pdf_one_per_page,
    DEFAULT_LABEL_SETTINGS,
    MIN_DOTS_PER_MODULE,
    MIN_MODULE_MM,
    QR_ERROR_LEVEL,
    register_pdf_font,
    qr_density,
    qr_module_count,
    _fit_font_sizes,
    _qr_widget,
)


def test_make_pdf_creates_file_with_pages(tmp_path):
    font_name = register_pdf_font()
    codes = ["MAN_16_07_2026_DE_BT_R4N001", "MAN_16_07_2026_DE_BT_X9Z002"]
    out_path = tmp_path / "labels.pdf"

    result = make_pdf_one_per_page(codes, out_path, DEFAULT_LABEL_SETTINGS, font_name)

    assert result.exists()
    assert result.stat().st_size > 0


def test_make_pdf_empty_list_still_creates_valid_file(tmp_path):
    font_name = register_pdf_font()
    out_path = tmp_path / "empty.pdf"

    result = make_pdf_one_per_page([], out_path, DEFAULT_LABEL_SETTINGS, font_name)

    assert result.exists()


def test_fit_font_sizes_shrinks_for_long_code():
    font_name = register_pdf_font()
    long_code = "MIR_16_07_2026_DE_BT_ABCDEFGHIJ1234"  # длиннее реального формата, специально для теста подгонки
    settings = DEFAULT_LABEL_SETTINGS.copy()

    code_fs, seq_fs, prefix, seq_part = _fit_font_sizes(long_code, settings, font_name)

    assert code_fs <= DEFAULT_LABEL_SETTINGS["code_font_size"]
    assert seq_fs <= DEFAULT_LABEL_SETTINGS["seq_font_size"]
    assert code_fs >= DEFAULT_LABEL_SETTINGS["min_font_size"]


def test_fit_font_sizes_keeps_default_for_short_code():
    font_name = register_pdf_font()
    short_code = "MAN_16_07_2026_DE_BT_R4N001"
    settings = DEFAULT_LABEL_SETTINGS.copy()
    # увеличим этикетку, чтобы точно хватило места без уменьшения
    settings["label_w_mm"] = 100

    code_fs, seq_fs, prefix, seq_part = _fit_font_sizes(short_code, settings, font_name)

    assert code_fs == DEFAULT_LABEL_SETTINGS["code_font_size"]
    assert seq_fs == DEFAULT_LABEL_SETTINGS["seq_font_size"]


def test_fit_font_sizes_splits_prefix_and_seq_correctly():
    font_name = register_pdf_font()
    code = "MAN_16_07_2026_DE_BT_R4N001"
    settings = DEFAULT_LABEL_SETTINGS.copy()

    _, _, prefix, seq_part = _fit_font_sizes(code, settings, font_name)

    assert prefix == "MAN_16_07_2026_DE_BT_R4N"
    assert seq_part == "001"


CODE = "MAN_16_07_2026_DE_BT_R4N001"
LONG_CONTENT = CODE + "\n" + "\n".join([
    "Кабинет продавца: Альфа-Премиум",
    "Дата: 16_07_2026",
    "Сезон коллекции: Лето-Осень",
    "Категория товара: Обувь женская",
    "Номер: 001",
])


def test_qr_uses_declared_error_correction_level():
    # уровень должен попадать в конструктор: присвоение barLevel после
    # создания виджета молча не действует, и QR печатался бы уровнем L
    from reportlab.graphics.barcode.qr import QrCodeWidget

    ours = qr_module_count(LONG_CONTENT)

    declared = QrCodeWidget(LONG_CONTENT, barLevel=QR_ERROR_LEVEL)
    declared.qr.make()
    assert ours == declared.qr.getModuleCount()

    ignored_level = QrCodeWidget(LONG_CONTENT)
    ignored_level.barLevel = QR_ERROR_LEVEL
    ignored_level.qr.make()
    assert ours != ignored_level.qr.getModuleCount()


def test_qr_module_count_grows_with_content():
    assert qr_module_count(CODE) < qr_module_count(LONG_CONTENT)


def test_qr_density_ok_for_default_size_and_short_content():
    d = qr_density(CODE, DEFAULT_LABEL_SETTINGS["qr_size_mm"])
    assert d["ok"]
    assert d["mm_per_module"] >= MIN_MODULE_MM
    assert d["dots_per_module"] >= MIN_DOTS_PER_MODULE


def test_qr_density_flags_too_dense_content():
    assert not qr_density(LONG_CONTENT, DEFAULT_LABEL_SETTINGS["qr_size_mm"])["ok"]


def test_qr_density_recovers_when_qr_enlarged():
    # ровно тот выход, который предлагает предупреждение в интерфейсе
    assert qr_density(LONG_CONTENT, 26)["ok"]


def test_qr_density_matches_printed_label():
    # индикатор обязан считать по тому же пути, что и печать
    settings = DEFAULT_LABEL_SETTINGS.copy()
    settings["label_type"] = "qr"
    printed = _qr_widget(LONG_CONTENT)
    printed.qr.make()
    assert qr_density(LONG_CONTENT, 22)["modules"] == printed.qr.getModuleCount()
