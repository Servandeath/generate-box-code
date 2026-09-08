"""
Генерация уникального кода короба для Wildberries.

Формат состоит из 5 блоков:
1-4: cabinet, date, season, item - порядок между собой НАСТРАИВАЕМЫЙ
     через block_order (по умолчанию cabinet_date_season_item, как
     раньше). cabinet присутствует ВСЕГДА (обязателен, с ним связан
     суточный счётчик seq); date/season/item можно индивидуально
     отключить (include_date/include_season/include_item), не меняя
     их место в порядке - выключенный блок просто пропускается.
5:   RANDOMSEQ (случайные символы + порядковый номер) - ВСЕГДА
     последний, не участвует в переупорядочивании.

Формат даты выбирается через date_format - см. DATE_FORMATS.
Случайная часть не превышает MAX_RANDOM_CHARS даже при большом
свободном бюджете.

Порядковый номер не ограничен сверху - ширина (кол-во цифр) считается
динамически под ТЕКУЩЕЕ значение seq (минимум 3 цифры, растёт по мере
роста номера: 001..999, затем 1000, 1001...).
"""

import random
import re
import string
from datetime import date

MIN_CODE_LENGTH = 6
MAX_CODE_LENGTH = 30
MIN_RANDOM_CHARS = 3
MAX_RANDOM_CHARS = 5
SEQ_MIN = 1
MIN_SEQ_DIGITS = 3

CABINET_CODE_LEN = 3
SEASON_CODE_LEN = 2
ITEM_CODE_LEN = 2

RANDOM_ALPHABET = string.ascii_uppercase + string.digits
_VALID_CHARS_RE = re.compile(r"^[A-Za-z0-9_-]+$")

BLOCK_KEYS = ("cabinet", "date", "season", "item")
DEFAULT_BLOCK_ORDER = ("cabinet", "date", "season", "item")

_MONTH_ABBR_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                  "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def _fmt_dmonyy(d: date) -> str:
    return f"{d.day}{_MONTH_ABBR_EN[d.month - 1]}{d.strftime('%y')}"


DATE_FORMATS = {
    "dd_MM_YYYY": lambda d: d.strftime("%d_%m_%Y"),
    "dd-MM-YYYY": lambda d: d.strftime("%d-%m-%Y"),
    "ddMMYY": lambda d: d.strftime("%d%m%y"),
    "YYMMDD": lambda d: d.strftime("%y%m%d"),
    "YYYYMMDD": lambda d: d.strftime("%Y%m%d"),
    "MM_YY": lambda d: d.strftime("%m_%y"),
    "MM-YY": lambda d: d.strftime("%m-%y"),
    "DMonYY": _fmt_dmonyy,
}
DEFAULT_DATE_FORMAT = "dd_MM_YYYY"


def _random_chars(n: int) -> str:
    return "".join(random.choices(RANDOM_ALPHABET, k=n))


def format_seq(seq: int) -> str:
    """Форматирует порядковый номер так же, как в самом коде короба:
    минимум MIN_SEQ_DIGITS цифр, ширина растёт вместе со значением
    (001..999, затем 1000, 1001...). Вынесено отдельно, чтобы то же
    форматирование можно было использовать вне генерации кода
    (например, в расшифровке QR)."""
    seq_digits = max(MIN_SEQ_DIGITS, len(str(seq)))
    return str(seq).zfill(seq_digits)


def _validate_block_order(block_order):
    order = tuple(block_order)
    if set(order) != set(BLOCK_KEYS) or len(order) != len(BLOCK_KEYS):
        raise ValueError(
            f"block_order должен быть перестановкой {BLOCK_KEYS} без повторов, получено {order}"
        )
    return order


def generate_box_code(
    cabinet: str,
    season: str,
    item: str,
    seq: int,
    gen_date: date | None = None,
    include_date: bool = True,
    date_format: str = DEFAULT_DATE_FORMAT,
    include_season: bool = True,
    include_item: bool = True,
    block_order=DEFAULT_BLOCK_ORDER,
) -> str:
    """
    Собирает код короба из блоков 1-4 (cabinet/date/season/item) в
    порядке block_order, плюс всегда последний блок RANDOMSEQ.

    Бросает ValueError, если seq < 1, block_order не является
    перестановкой ('cabinet','date','season','item'), date_format
    не найден в DATE_FORMATS, любая ВКЛЮЧЁННАЯ часть содержит
    недопустимые символы, или не остаётся места даже на минимальную
    случайную часть (MIN_RANDOM_CHARS).
    """
    if seq < SEQ_MIN:
        raise ValueError(f"seq должен быть >= {SEQ_MIN}, получено {seq}")

    order = _validate_block_order(block_order)

    if not cabinet or not _VALID_CHARS_RE.match(cabinet):
        raise ValueError(f"cabinet='{cabinet}' содержит недопустимые символы")
    if include_season and (not season or not _VALID_CHARS_RE.match(season)):
        raise ValueError(f"season='{season}' содержит недопустимые символы")
    if include_item and (not item or not _VALID_CHARS_RE.match(item)):
        raise ValueError(f"item='{item}' содержит недопустимые символы")

    if include_date:
        if date_format not in DATE_FORMATS:
            raise ValueError(f"Неизвестный формат даты: '{date_format}'. Доступные: {list(DATE_FORMATS)}")
        gen_date = gen_date or date.today()
        date_part = DATE_FORMATS[date_format](gen_date)
    else:
        date_part = None

    seq_part = format_seq(seq)
    seq_digits = len(seq_part)

    segment_values = {
        "cabinet": cabinet,
        "date": date_part,
        "season": season if include_season else None,
        "item": item if include_item else None,
    }

    parts = [segment_values[key] for key in order if segment_values[key] is not None]
    if not parts:
        raise ValueError("Все блоки отключены - код не может состоять из одного случайного номера")

    fixed_len = sum(len(p) for p in parts) + len(parts)  # +1 разделитель "_" после каждой части
    fixed_len += seq_digits
    available_budget = MAX_CODE_LENGTH - fixed_len

    if available_budget < MIN_RANDOM_CHARS:
        raise ValueError(
            f"Не хватает места под случайную часть: доступно {available_budget}, "
            f"минимум {MIN_RANDOM_CHARS}. Сократите блоки, "
            f"выберите более короткий формат даты, либо номер {seq} стал "
            f"слишком большим для формата."
        )

    random_len = min(available_budget, MAX_RANDOM_CHARS)

    code = "_".join(parts) + f"_{_random_chars(random_len)}{seq_part}"

    if not (MIN_CODE_LENGTH <= len(code) <= MAX_CODE_LENGTH):
        raise ValueError(f"Итоговая длина кода {len(code)} вне диапазона 6-30")
    if code.upper().startswith("WB"):
        raise ValueError("Код не должен начинаться с 'WB'")
    if not _VALID_CHARS_RE.match(code):
        raise ValueError(f"Код содержит недопустимые символы: {code}")

    return code
