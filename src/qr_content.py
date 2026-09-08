"""
Сборка человекочитаемого содержимого QR-кода для этикетки короба.

Идея: QR несёт больше данных, чем Code128. В него кладём:
  1) первую строку — сам код короба (машиночитаемая сверка с Code128);
  2) далее расшифровку по строкам «Подпись: значение» в текущем
     порядке блоков, с пользовательскими названиями разделов.

Значения в расшифровке — русские названия разделов (например «Кунц»),
а латинские коды остаются в первой строке (в самом коде короба).

Функция не зависит от GUI/БД: принимает готовые данные, возвращает
строку. Это делает её тестируемой и переиспользуемой (как ядро
generate_box_code).
"""

# Подписи блоков даты и номера в расшифровке фиксированы.
DATE_LABEL = "Дата"
SEQ_LABEL = "Номер"


def build_qr_content(
    code: str,
    order,
    include: dict,
    labels: dict,
    values_ru: dict,
    date_str: str,
    seq_str: str,
) -> str:
    """Собирает многострочное содержимое QR.

    Аргументы:
      code       — готовый код короба (первая строка QR).
      order      — кортеж/список порядка блоков, напр.
                   ('cabinet','date','season','item').
      include    — {'date':bool,'season':bool,'item':bool} — какие
                   опциональные блоки включены. cabinet всегда включён.
      labels     — {'cabinet','season','item'} пользовательские подписи
                   разделов (например 'Корабль'/'Паллет'/'Фрукт' или
                   дефолтные 'Блок 1/2/3').
      values_ru  — {'cabinet','season','item'} русские названия
                   выбранных записей справочника (например 'Кунц').
      date_str   — отформатированная дата (например '11_08_2026').
      seq_str    — порядковый номер строкой (например '001').

    Возвращает строку вида:
      КОД
      Дата: 11_08_2026
      Корабль: Кунц
      ...
      Номер: 001
    """
    lines = [code]

    for key in order:
        if key == "cabinet":
            lines.append(f"{labels['cabinet']}: {values_ru['cabinet']}")
        elif key == "date":
            if include.get("date", True):
                lines.append(f"{DATE_LABEL}: {date_str}")
        elif key == "season":
            if include.get("season", True):
                lines.append(f"{labels['season']}: {values_ru['season']}")
        elif key == "item":
            if include.get("item", True):
                lines.append(f"{labels['item']}: {values_ru['item']}")

    lines.append(f"{SEQ_LABEL}: {seq_str}")

    return "\n".join(lines)


def build_qr_content_from_history_row(row, labels: dict) -> str:
    """Собирает содержимое QR для перепечатки кода из истории.

    История (db.list_history) не хранит порядок/состав блоков и формат
    даты, использованные при генерации - только сам код, имена
    разделов, seq и created_at. Поэтому для перепечатки берётся
    порядок по умолчанию и все блоки считаются включёнными (что
    показать в расшифровке важнее, чем точно повторить исходные
    настройки формата, которые к моменту перепечатки могли уже
    измениться).

    row   — объект с полями code/cabinet_name/season_name/item_name/
            seq/created_at (например sqlite3.Row из list_history).
    labels — текущие подписи разделов (dimension_labels), например
            {'cabinet': 'Блок 1', 'season': 'Блок 2', 'item': 'Блок 3'}.
    """
    from generate_box_code import DEFAULT_BLOCK_ORDER, format_seq

    date_str = str(row["created_at"]).split(" ")[0]
    values_ru = {
        "cabinet": row["cabinet_name"],
        "season": row["season_name"],
        "item": row["item_name"],
    }
    include = {"date": True, "season": True, "item": True}

    return build_qr_content(
        row["code"], DEFAULT_BLOCK_ORDER, include, labels, values_ru,
        date_str, format_seq(row["seq"]),
    )
