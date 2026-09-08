"""Тесты сборки содержимого QR (qr_content.build_qr_content)."""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qr_content import build_qr_content, build_qr_content_from_history_row


BASE_LABELS = {"cabinet": "Блок 1", "season": "Блок 2", "item": "Блок 3"}
CUSTOM_LABELS = {"cabinet": "Корабль", "season": "Паллет", "item": "Фрукт"}
VALUES = {"cabinet": "Кунц", "season": "лето", "item": "шмот"}
ORDER = ("cabinet", "date", "season", "item")
ALL_ON = {"date": True, "season": True, "item": True}


def test_first_line_is_raw_code():
    out = build_qr_content("KUN_11_08_2026_LE_SH_X001", ORDER, ALL_ON,
                           BASE_LABELS, VALUES, "11_08_2026", "001")
    assert out.splitlines()[0] == "KUN_11_08_2026_LE_SH_X001"


def test_default_labels_used_when_not_renamed():
    out = build_qr_content("C", ORDER, ALL_ON, BASE_LABELS, VALUES, "11_08_2026", "001")
    assert "Блок 1: Кунц" in out
    assert "Блок 2: лето" in out
    assert "Блок 3: шмот" in out


def test_custom_labels_used_when_renamed():
    out = build_qr_content("C", ORDER, ALL_ON, CUSTOM_LABELS, VALUES, "11_08_2026", "001")
    assert "Корабль: Кунц" in out
    assert "Паллет: лето" in out
    assert "Фрукт: шмот" in out


def test_values_are_russian_names_not_codes():
    out = build_qr_content("C", ORDER, ALL_ON, CUSTOM_LABELS, VALUES, "11_08_2026", "001")
    # значение — русское имя, латинский код не в расшифровке (он в 1-й строке)
    assert "Кунц" in out
    assert "Корабль: KUN" not in out


def test_date_included_and_labeled():
    out = build_qr_content("C", ORDER, ALL_ON, CUSTOM_LABELS, VALUES, "11_08_2026", "001")
    assert "Дата: 11_08_2026" in out


def test_seq_line_last():
    out = build_qr_content("C", ORDER, ALL_ON, CUSTOM_LABELS, VALUES, "11_08_2026", "042")
    assert out.splitlines()[-1] == "Номер: 042"


def test_disabled_blocks_excluded():
    include = {"date": False, "season": False, "item": True}
    out = build_qr_content("C", ORDER, include, CUSTOM_LABELS, VALUES, "11_08_2026", "001")
    assert "Дата:" not in out
    assert "Паллет:" not in out       # season выключен
    assert "Фрукт: шмот" in out       # item включён
    assert "Корабль: Кунц" in out     # cabinet всегда


def test_order_reflected_in_output():
    # порядок: сначала item, потом cabinet — расшифровка должна следовать
    order = ("item", "cabinet", "date", "season")
    out = build_qr_content("C", order, ALL_ON, CUSTOM_LABELS, VALUES, "11_08_2026", "001")
    body = out.splitlines()[1:]  # без первой строки-кода
    # первая содержательная строка — Фрукт (item), затем Корабль (cabinet)
    assert body[0].startswith("Фрукт")
    assert body[1].startswith("Корабль")


HISTORY_ROW = {
    "code": "KUN_11_08_2026_LE_SH_X001",
    "cabinet_name": "Кунц",
    "season_name": "лето",
    "item_name": "шмот",
    "seq": 1,
    "created_at": "2026-08-11 14:30:05",
}


def test_history_row_first_line_is_code():
    out = build_qr_content_from_history_row(HISTORY_ROW, BASE_LABELS)
    assert out.splitlines()[0] == "KUN_11_08_2026_LE_SH_X001"


def test_history_row_uses_names_and_date_only_part():
    out = build_qr_content_from_history_row(HISTORY_ROW, BASE_LABELS)
    assert "Блок 1: Кунц" in out
    assert "Блок 2: лето" in out
    assert "Блок 3: шмот" in out
    assert "Дата: 2026-08-11" in out


def test_history_row_seq_padded_and_last():
    out = build_qr_content_from_history_row(HISTORY_ROW, BASE_LABELS)
    assert out.splitlines()[-1] == "Номер: 001"


def test_history_row_uses_current_custom_labels():
    out = build_qr_content_from_history_row(HISTORY_ROW, CUSTOM_LABELS)
    assert "Корабль: Кунц" in out
