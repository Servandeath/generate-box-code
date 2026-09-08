from datetime import date
import sys
import os
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))
from generate_box_code import (
    generate_box_code, format_seq, MIN_RANDOM_CHARS, MAX_RANDOM_CHARS,
    DATE_FORMATS, DEFAULT_BLOCK_ORDER,
)

FIXED_DATE = date(2026, 7, 16)


def test_basic_format():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE)
    assert code.startswith("ALF_16_07_2026_DE_BT_")
    assert code.endswith("001")


def test_seq_below_min_raises():
    with pytest.raises(ValueError):
        generate_box_code("ALF", "DE", "BT", 0, gen_date=FIXED_DATE)


def test_no_upper_limit_seq_grows_digits():
    code_small = generate_box_code("ALF", "DE", "BT", 5, gen_date=FIXED_DATE)
    assert code_small.endswith("005")

    code_big = generate_box_code("ALF", "DE", "BT", 1234, gen_date=FIXED_DATE)
    assert code_big.endswith("1234")


def test_very_large_seq_eventually_raises_no_budget():
    huge_seq = 10**20
    with pytest.raises(ValueError):
        generate_box_code("ALF", "DE", "BT", huge_seq, gen_date=FIXED_DATE)


def test_all_three_cabinets_fit():
    for cab in ("ALF", "BET", "GAM"):
        code = generate_box_code(cab, "DE", "BT", 1, gen_date=FIXED_DATE)
        assert len(code) <= 30


def test_too_long_inputs_raise():
    with pytest.raises(ValueError):
        generate_box_code("ALF", "SEASON123456", "ITEMTYPE123456", 1, gen_date=FIXED_DATE)


def test_random_part_has_minimum_entropy():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE)
    randomseq_block = code.split("_")[-1]
    random_part = randomseq_block[:-3]
    assert len(random_part) >= MIN_RANDOM_CHARS


def test_no_wb_prefix():
    with pytest.raises(ValueError):
        generate_box_code("WBC", "DE", "BT", 1, gen_date=FIXED_DATE)


def test_include_date_false_omits_date_entirely():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, include_date=False)
    assert code.startswith("ALF_DE_BT_")
    assert "16_07_2026" not in code
    assert "2026" not in code


def test_date_format_dd_dash_mm_dash_yyyy():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format="dd-MM-YYYY")
    assert "16-07-2026" in code


def test_date_format_ddmmyy_compact():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format="ddMMYY")
    assert "160726" in code


def test_date_format_yymmdd():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format="YYMMDD")
    assert "260716" in code


def test_date_format_yyyymmdd():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format="YYYYMMDD")
    assert "20260716" in code


def test_date_format_mm_yy():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format="MM_YY")
    assert "07_26" in code


def test_date_format_dmonyy_uses_english_month_no_locale_dependency():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format="DMonYY")
    assert "16Jul26" in code


def test_unknown_date_format_raises():
    with pytest.raises(ValueError):
        generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format="not_a_real_format")


def test_all_date_formats_produce_valid_codes():
    for fmt_key in DATE_FORMATS:
        code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, date_format=fmt_key)
        assert len(code) <= 30
        assert code.upper().startswith("ALF")


def test_random_part_capped_at_max_even_with_lots_of_free_budget():
    code = generate_box_code("A", "D", "B", 1, include_date=False)
    randomseq_block = code.split("_")[-1]
    random_part = randomseq_block[:-3]
    assert len(random_part) == MAX_RANDOM_CHARS
    assert len(code) < 30


def test_random_part_uses_available_when_less_than_max():
    code = generate_box_code("ALF", "SEA", "ITE", 1, gen_date=FIXED_DATE)
    randomseq_block = code.split("_")[-1]
    random_part = randomseq_block[:-3]
    assert MIN_RANDOM_CHARS <= len(random_part) < MAX_RANDOM_CHARS


def test_default_block_order_matches_original_format():
    code = generate_box_code("ALF", "DE", "BT", 1, gen_date=FIXED_DATE, block_order=DEFAULT_BLOCK_ORDER)
    assert code.startswith("ALF_16_07_2026_DE_BT_")


def test_custom_block_order_date_first():
    code = generate_box_code(
        "ALF", "DE", "BT", 1, gen_date=FIXED_DATE,
        block_order=("date", "cabinet", "season", "item"),
    )
    assert code.startswith("16_07_2026_ALF_DE_BT_")


def test_custom_block_order_item_before_cabinet():
    code = generate_box_code(
        "ALF", "DE", "BT", 1, gen_date=FIXED_DATE,
        block_order=("item", "cabinet", "date", "season"),
    )
    assert code.startswith("BT_ALF_16_07_2026_DE_")


def test_block_order_skips_disabled_blocks_but_keeps_relative_order():
    code = generate_box_code(
        "ALF", "DE", "BT", 1, gen_date=FIXED_DATE,
        include_season=False,
        block_order=("season", "date", "cabinet", "item"),
    )
    # season выключен - пропускается, порядок остальных сохраняется: date, cabinet, item
    assert code.startswith("16_07_2026_ALF_BT_")


def test_random_seq_block_always_last_regardless_of_order():
    code = generate_box_code(
        "ALF", "DE", "BT", 42, gen_date=FIXED_DATE,
        block_order=("item", "date", "season", "cabinet"),
    )
    assert code.endswith("042")
    assert not code.startswith("042")


def test_invalid_block_order_missing_key_raises():
    with pytest.raises(ValueError):
        generate_box_code(
            "ALF", "DE", "BT", 1, gen_date=FIXED_DATE,
            block_order=("cabinet", "date", "season"),  # нет "item"
        )


def test_invalid_block_order_duplicate_key_raises():
    with pytest.raises(ValueError):
        generate_box_code(
            "ALF", "DE", "BT", 1, gen_date=FIXED_DATE,
            block_order=("cabinet", "cabinet", "season", "item"),
        )


def test_invalid_block_order_unknown_key_raises():
    with pytest.raises(ValueError):
        generate_box_code(
            "ALF", "DE", "BT", 1, gen_date=FIXED_DATE,
            block_order=("cabinet", "date", "season", "unknown_key"),
        )


def test_format_seq_pads_to_min_digits():
    assert format_seq(1) == "001"
    assert format_seq(42) == "042"


def test_format_seq_grows_with_value():
    assert format_seq(1234) == "1234"


def test_format_seq_matches_code_suffix():
    code = generate_box_code("ALF", "DE", "BT", 7, gen_date=FIXED_DATE)
    assert code.endswith(format_seq(7))
