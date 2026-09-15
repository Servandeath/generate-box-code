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
    fit_text_block,
    qr_text_layout,
    MIN_READABLE_TEXT_PT,
    _truncate_to_width,
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


DECODED = [
    "Блок 1: Альфа",
    "Дата: 16_07_2026",
    "Блок 2: Лето",
    "Блок 3: Обувь",
    "Номер: 001",
]


def test_fit_text_block_keeps_start_size_when_it_fits():
    font = register_pdf_font()
    fs, _ = fit_text_block(DECODED, 200, 200, 7, 4, font)
    assert fs == 7


def test_fit_text_block_shrinks_when_too_narrow():
    font = register_pdf_font()
    fs, _ = fit_text_block(DECODED, 40, 200, 7, 4, font)
    assert fs < 7


def test_fit_text_block_never_below_min():
    font = register_pdf_font()
    fs, _ = fit_text_block(DECODED, 1, 1, 7, 4, font)
    assert fs == 4


def test_truncate_adds_ellipsis_and_fits():
    font = register_pdf_font()
    from reportlab.pdfbase import pdfmetrics
    line = "Категория товара: Обувь женская зимняя"
    out = _truncate_to_width(line, 60, font, 7)
    assert out.endswith("…")
    assert pdfmetrics.stringWidth(out, font, 7) <= 60


def test_truncate_leaves_short_line_untouched():
    font = register_pdf_font()
    assert _truncate_to_width("Номер: 001", 200, font, 7) == "Номер: 001"


def test_qr_label_with_text_block_renders(tmp_path):
    font = register_pdf_font()
    settings = DEFAULT_LABEL_SETTINGS.copy()
    settings["label_type"] = "qr"
    out = tmp_path / "qr_text.pdf"
    content = "ALF_16_07_2026_DE_BT_R4N001\n" + "\n".join(DECODED)

    result = make_pdf_one_per_page(["ALF_16_07_2026_DE_BT_R4N001"], out, settings, font,
                                   qr_contents=[content])

    assert result.exists()
    assert result.stat().st_size > 0


QR_CONTENT = "ALF_16_07_2026_DE_BT_R4N001\n" + "\n".join(DECODED)


def _qr_settings(**overrides):
    settings = DEFAULT_LABEL_SETTINGS.copy()
    settings["label_type"] = "qr"
    settings.update(overrides)
    return settings


def test_qr_text_layout_skips_code_line():
    layout = qr_text_layout(QR_CONTENT, _qr_settings(), register_pdf_font())
    assert [text for text, _ in layout["placed"]] == DECODED


def test_qr_text_layout_none_when_only_code():
    assert qr_text_layout("ALF_16_07_2026_DE_BT_R4N001", _qr_settings(), register_pdf_font()) is None


def test_qr_text_layout_ok_for_default_label():
    layout = qr_text_layout(QR_CONTENT, _qr_settings(), register_pdf_font())
    assert layout["ok"]
    assert layout["font_size"] >= MIN_READABLE_TEXT_PT


def test_qr_text_layout_bigger_qr_squeezes_text():
    # QR и текст делят одно место: крупнее QR - мельче текст
    font = register_pdf_font()
    normal = qr_text_layout(QR_CONTENT, _qr_settings(qr_size_mm=22, qr_y=4), font)
    big_qr = qr_text_layout(QR_CONTENT, _qr_settings(qr_size_mm=32, qr_y=4), font)
    assert big_qr["font_size"] < normal["font_size"]


def test_qr_text_layout_reports_truncation_on_narrow_label():
    layout = qr_text_layout(QR_CONTENT, _qr_settings(label_w_mm=40), register_pdf_font())
    assert layout["truncated"] > 0
    assert not layout["ok"]


def test_qr_text_layout_reports_dropped_lines():
    many_lines = "CODE\n" + "\n".join(f"Строка {i}" for i in range(10))
    layout = qr_text_layout(many_lines, _qr_settings(label_h_mm=20), register_pdf_font())
    assert layout["dropped"] > 0
    assert not layout["ok"]


def test_qr_text_layout_no_room_when_qr_fills_width():
    layout = qr_text_layout(QR_CONTENT, _qr_settings(qr_size_mm=48), register_pdf_font())
    assert layout["placed"] == []
    assert layout["dropped"] == len(DECODED)
    assert not layout["ok"]


def test_qr_text_layout_small_qr_does_not_squeeze_text():
    # высота колонки не зависит от QR, иначе подсказка "уменьшите QR" врала бы
    layout = qr_text_layout(QR_CONTENT, _qr_settings(qr_size_mm=12), register_pdf_font())
    assert layout["ok"]
    assert layout["font_size"] == DEFAULT_LABEL_SETTINGS["qr_text_font_size"]


def _qr_top(settings):
    from reportlab.lib.units import mm
    return (settings["qr_y"] + settings["qr_size_mm"]) * mm


def test_qr_text_layout_aligned_with_qr_top_when_it_fits():
    settings = _qr_settings()
    layout = qr_text_layout(QR_CONTENT, settings, register_pdf_font())
    first_baseline = layout["placed"][0][1]
    assert abs(first_baseline - (_qr_top(settings) - layout["font_size"])) < 0.01


def test_qr_text_layout_rises_above_low_qr_without_losing_lines():
    settings = _qr_settings(qr_size_mm=12)
    layout = qr_text_layout(QR_CONTENT, settings, register_pdf_font())
    assert layout["placed"][0][1] > _qr_top(settings) - layout["font_size"]
    assert layout["dropped"] == 0
