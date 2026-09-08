"""
Отрисовка этикетки короба: штрихкод Code128 (растянут на всю ширину
этикетки за вычетом отступов) + текст кода, где последние seq_digits
символов (порядковый номер) печатаются увеличенным шрифтом.

ВАЖНО про превью: render_preview_image() генерирует НАСТОЯЩИЙ PDF в
памяти (той же функцией make_pdf_one_per_page, что и печать) и
растеризует его через PyMuPDF. Это не отдельная "похожая" реализация
рендера - превью буквально является снимком реального PDF, поэтому
расхождение между превью и итоговым файлом больше не может возникнуть
в принципе, каким бы способом код ни менялся в будущем.

Сетка и рамка зоны отступов рисуются ПОЛУПРОЗРАЧНЫМ слоем поверх
растрового изображения (alpha-композиция), а не сплошными линиями -
иначе они перекрывали бы штрихкод и текст жирным цветом.

Поддерживаются именованные шаблоны настроек (пресеты) - например
разные размеры этикеток под разные задачи.
"""

import io
import json
import os
from pathlib import Path

from reportlab.pdfgen import canvas
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from app_paths import get_app_data_dir

PDF_FONT_NAME = "LabelFont"
SETTINGS_FILE = get_app_data_dir() / "label_settings.json"
PRESETS_FILE = get_app_data_dir() / "label_presets.json"

# Уровень коррекции ошибок QR: M = 15% (запас на потёртости и грязь
# на складе). Выше (Q/H) - заметно плотнее при том же размере.
QR_ERROR_LEVEL = "M"

# Порог печатаемости QR. Ниже него модули на термопринтере сливаются,
# и сканер читает через раз. 203 dpi - типовой складской принтер.
DOTS_PER_MM_203DPI = 203 / 25.4
MIN_MODULE_MM = 0.33
MIN_DOTS_PER_MODULE = 3.0

FONT_CANDIDATES = [
    r"C:\Windows\Fonts\arial.ttf",
    r"C:\Windows\Fonts\segoeui.ttf",
    r"C:\Windows\Fonts\tahoma.ttf",
    r"C:\Windows\Fonts\calibri.ttf",
    r"C:\Windows\Fonts\verdana.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
    "/Library/Fonts/Arial.ttf",
    "/System/Library/Fonts/Supplemental/Arial.ttf",
]

DEFAULT_LABEL_SETTINGS = {
    "label_w_mm": 58,
    "label_h_mm": 40,
    "margin_mm": 3,

    "barcode_y": 16,
    "barcode_h": 18,

"code_y": 4,
    "code_font_size": 9,
    "seq_font_size": 18,
    "seq_digits": 3,
    "min_font_size": 4,

    "show_grid": 1,

    # --- QR ---
    "qr_size_mm": 22,
    "qr_x": 5,
    "qr_y": 10,
    "qr_show_code": 1,
    "qr_code_y": 4,
    "qr_code_font_size": 7,

    "label_type": "barcode",
}

def find_font_path() -> str | None:
    for path in FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    search_dirs = [
        r"C:\Windows\Fonts",
        "/usr/share/fonts",
        "/Library/Fonts",
        os.path.expanduser("~/.fonts"),
    ]
    for d in search_dirs:
        if os.path.isdir(d):
            for rootdir, _, files in os.walk(d):
                for fn in files:
                    if fn.lower().endswith(".ttf"):
                        return os.path.join(rootdir, fn)
    return None


FONT_PATH = find_font_path()


def register_pdf_font() -> str:
    if FONT_PATH:
        try:
            pdfmetrics.registerFont(TTFont(PDF_FONT_NAME, FONT_PATH))
            return PDF_FONT_NAME
        except Exception:
            pass
    return "Helvetica"


def load_label_settings() -> dict:
    settings = DEFAULT_LABEL_SETTINGS.copy()
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, "r", encoding="utf-8") as f:
                settings.update(json.load(f))
        except Exception:
            pass
    return settings


def save_label_settings(settings: dict) -> None:
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(settings, f, ensure_ascii=False, indent=2)


def load_presets() -> dict:
    if PRESETS_FILE.exists():
        try:
            with open(PRESETS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}


def save_preset(name: str, settings: dict) -> None:
    presets = load_presets()
    presets[name] = settings
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


def delete_preset(name: str) -> None:
    presets = load_presets()
    presets.pop(name, None)
    with open(PRESETS_FILE, "w", encoding="utf-8") as f:
        json.dump(presets, f, ensure_ascii=False, indent=2)


def list_preset_names() -> list[str]:
    return sorted(load_presets().keys())


def _fit_font_sizes(code: str, settings: dict, font_name: str) -> tuple[int, int, str, str]:
    seq_digits = int(settings["seq_digits"])
    prefix = code[:-seq_digits] if seq_digits > 0 else code
    seq_part = code[-seq_digits:] if seq_digits > 0 else ""

    available_width = (float(settings["label_w_mm"]) - 2 * float(settings["margin_mm"])) * mm

    code_fs = int(settings["code_font_size"])
    seq_fs = int(settings["seq_font_size"])
    min_fs = int(settings["min_font_size"])

    while code_fs > min_fs and seq_fs > min_fs:
        total_width = (
            pdfmetrics.stringWidth(prefix, font_name, code_fs)
            + pdfmetrics.stringWidth(seq_part, font_name, seq_fs)
        )
        if total_width <= available_width:
            break
        code_fs -= 1
        seq_fs -= 1

    return code_fs, seq_fs, prefix, seq_part


def _render_barcode_bars_pil(code: str, w_px: int, h_px: int):
    import barcode
    from barcode.writer import ImageWriter
    from PIL import Image

    code128_cls = barcode.get_barcode_class("code128")
    writer = ImageWriter()
    writer.dpi = 300

    bc = code128_cls(code, writer=writer)
    buf = io.BytesIO()
    bc.write(buf, options={"write_text": False, "quiet_zone": 2.0, "module_height": 15.0})
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    return img.resize((max(1, w_px), max(1, h_px)))


def draw_barcode_pdf(c: canvas.Canvas, code: str, settings: dict):
    margin = float(settings["margin_mm"]) * mm
    w_mm = float(settings["label_w_mm"]) - 2 * float(settings["margin_mm"])
    h_mm = float(settings["barcode_h"])
    y = float(settings["barcode_y"]) * mm

    px_per_mm = 300 / 25.4
    w_px = max(1, int(w_mm * px_per_mm))
    h_px = max(1, int(h_mm * px_per_mm))

    img = _render_barcode_bars_pil(code, w_px, h_px)
    c.drawImage(ImageReader(img), margin, y, width=w_mm * mm, height=h_mm * mm)
def _qr_widget(qr_content: str):
    """QrCodeWidget с уровнем коррекции QR_ERROR_LEVEL.

    Уровень ОБЯЗАН передаваться в конструктор: QrCodeWidget читает
    barLevel один раз, когда создаёт внутренний QRCode, и своего
    __setattr__ у него нет. Присваивание qr.barLevel уже после
    конструктора молча не действует - код печатался бы уровнем L
    (7% коррекции) вместо M (15%), никак об этом не сообщая.
    """
    from reportlab.graphics.barcode.qr import QrCodeWidget

    return QrCodeWidget(qr_content, barLevel=QR_ERROR_LEVEL)


def qr_module_count(qr_content: str) -> int:
    """Число модулей (клеток) в QR со стороны - растёт вместе с объёмом
    содержимого. Считается тем же путём, что и при печати, поэтому
    оценка плотности не может разойтись с реальной этикеткой."""
    qr = _qr_widget(qr_content)
    qr.qr.make()
    return qr.qr.getModuleCount()


def qr_density(qr_content: str, qr_size_mm: float, dots_per_mm: float = DOTS_PER_MM_203DPI) -> dict:
    """Оценка печатаемости QR: сколько миллиметров и точек принтера
    приходится на один модуль при заданном размере QR.

    Практический порог - MIN_MODULE_MM на модуль и не меньше
    MIN_DOTS_PER_MODULE точек принтера: ниже него термопринтер
    начинает "слипать" модули, и сканер читает через раз.
    """
    modules = qr_module_count(qr_content)
    mm_per_module = float(qr_size_mm) / modules
    dots_per_module = mm_per_module * dots_per_mm
    return {
        "modules": modules,
        "mm_per_module": mm_per_module,
        "dots_per_module": dots_per_module,
        "ok": mm_per_module >= MIN_MODULE_MM and dots_per_module >= MIN_DOTS_PER_MODULE,
    }


def draw_qr_pdf(c: canvas.Canvas, qr_content: str, settings: dict):
    """
    Рисует QR-код с содержимым qr_content в PDF-канвас.
    Позиция (qr_x, qr_y от нижнего-левого угла) и размер (qr_size_mm) —
    из настроек. По тому же принципу, что draw_barcode_pdf — прямо в
    канвас, чтобы превью (снимок PDF) совпало с печатью.
    """
    from reportlab.graphics.shapes import Drawing
    from reportlab.graphics import renderPDF

    size_mm = float(settings.get("qr_size_mm", 22))
    x = float(settings.get("qr_x", 5)) * mm
    y = float(settings.get("qr_y", 10)) * mm

    qr = _qr_widget(qr_content)
    bounds = qr.getBounds()
    qr_w = bounds[2] - bounds[0]
    qr_h = bounds[3] - bounds[1]

    d = Drawing(
        size_mm * mm, size_mm * mm,
        transform=[size_mm * mm / qr_w, 0, 0, size_mm * mm / qr_h, 0, 0],
    )
    d.add(qr)
    renderPDF.draw(d, c, x, y)
def draw_qr_code_label(c: canvas.Canvas, code: str, settings: dict, font_name: str):
    """Подпись сырого кода под QR (если включена галочка qr_show_code).
    Размещается по qr_code_y, шрифтом qr_code_font_size, с автоподгонкой
    под ширину этикетки."""
    available_width = (float(settings["label_w_mm"]) - 2 * float(settings["margin_mm"])) * mm
    fs = int(settings.get("qr_code_font_size", 7))
    min_fs = int(settings.get("min_font_size", 4))
    while fs > min_fs and pdfmetrics.stringWidth(code, font_name, fs) > available_width:
        fs -= 1
    x = float(settings["margin_mm"]) * mm
    y = float(settings.get("qr_code_y", 4)) * mm
    c.setFont(font_name, fs)
    c.drawString(x, y, code)

def draw_code_text(c: canvas.Canvas, code: str, settings: dict, font_name: str):
    code_fs, seq_fs, prefix, seq_part = _fit_font_sizes(code, settings, font_name)

    x = float(settings["margin_mm"]) * mm
    y = float(settings["code_y"]) * mm

    c.setFont(font_name, code_fs)
    c.drawString(x, y, prefix)

    if seq_part:
        prefix_width = pdfmetrics.stringWidth(prefix, font_name, code_fs)
        c.setFont(font_name, seq_fs)
        c.drawString(x + prefix_width, y, seq_part)


def draw_label(c: canvas.Canvas, code: str, settings: dict, font_name: str, qr_content=None):
    """Рисует этикетку. Тип определяется settings['label_type']:
      'barcode' (по умолчанию) — Code128 + текст кода;
      'qr'                      — QR + опциональная подпись кода снизу.
    qr_content — готовая строка содержимого QR (собирается в GUI).
    При label_type='qr' без qr_content подставляется сам код (запасной путь).
    """
    label_type = settings.get("label_type", "barcode")
    if label_type == "qr":
        content = qr_content if qr_content is not None else code
        draw_qr_pdf(c, content, settings)
        if int(settings.get("qr_show_code", 1)):
            draw_qr_code_label(c, code, settings, font_name)
    else:
        draw_barcode_pdf(c, code, settings)
        draw_code_text(c, code, settings, font_name)


def make_pdf_one_per_page(codes, out_path, settings: dict, font_name: str, qr_contents=None):
    w = float(settings["label_w_mm"]) * mm
    h = float(settings["label_h_mm"]) * mm

    is_path = isinstance(out_path, (str, Path))
    target = str(out_path) if is_path else out_path

    c = canvas.Canvas(target, pagesize=(w, h))
    for i, code in enumerate(codes):
        qc = qr_contents[i] if qr_contents is not None and i < len(qr_contents) else None
        draw_label(c, code, settings, font_name, qr_content=qc)
        c.showPage()
    c.save()

    return Path(out_path) if is_path else out_path


def render_preview_image(code: str, settings: dict, font_name: str, px_per_mm: int = 8,
                         qr_content: str | None = None):
    """
    Рендер этикетки в PIL.Image для живого превью в GUI. Генерирует
    настоящий PDF в памяти и растеризует его через PyMuPDF - превью
    физически является снимком реального PDF. Сетка (шаг 5 мм) и рамка
    зоны отступов рисуются полупрозрачным слоем поверх - видны на белом
    фоне, но не перекрывают штрихкод/текст сплошным цветом.

    qr_content - содержимое QR для превью. Его обязательно передавать
    таким же, каким оно уйдёт в печать: от объёма содержимого зависит
    плотность QR (число модулей), поэтому превью с одним лишь кодом
    выглядело бы заметно реже реальной этикетки.
    """
    import fitz
    from PIL import Image, ImageDraw, ImageFont

    buf = io.BytesIO()
    qr_contents = None
    if settings.get("label_type") == "qr":
        # запасной путь: без готового содержимого показываем сам код
        qr_contents = [qr_content if qr_content is not None else code]
    make_pdf_one_per_page([code], buf, settings, font_name, qr_contents=qr_contents)
    buf.seek(0)

    dpi = px_per_mm * 25.4
    doc = fitz.open(stream=buf.getvalue(), filetype="pdf")
    page = doc[0]
    zoom = dpi / 72.0
    pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
    base_img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGBA")
    doc.close()

    W, H = base_img.size
    label_w_mm = float(settings["label_w_mm"])
    label_h_mm = float(settings["label_h_mm"])
    margin_mm = float(settings["margin_mm"])

    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    odraw = ImageDraw.Draw(overlay)

    GRID_COLOR = (90, 90, 255, 70)       # полупрозрачный синий - сетка 5мм
    MARGIN_COLOR = (255, 120, 0, 160)    # полупрозрачный оранжевый - зона отступов
    AXIS_TEXT_COLOR = (60, 60, 180, 220)

    if int(settings.get("show_grid", 1)):
        try:
            axis_font = ImageFont.truetype(FONT_PATH, 9) if FONT_PATH else ImageFont.load_default()
        except Exception:
            axis_font = ImageFont.load_default()

        gx = 0
        while gx <= label_w_mm:
            px = gx * px_per_mm
            odraw.line([(px, 0), (px, H)], fill=GRID_COLOR, width=1)
            gx += 5
        gy = 0
        while gy <= label_h_mm:
            py = H - gy * px_per_mm
            odraw.line([(0, py), (W, py)], fill=GRID_COLOR, width=1)
            gy += 5

        gx = 0
        while gx <= label_w_mm:
            odraw.text((gx * px_per_mm + 1, 1), str(int(gx)), fill=AXIS_TEXT_COLOR, font=axis_font)
            gx += 10
        gy = 10
        while gy <= label_h_mm:
            odraw.text((1, H - gy * px_per_mm + 1), str(int(gy)), fill=AXIS_TEXT_COLOR, font=axis_font)
            gy += 10

        # рамка зоны отступов - показывает, где реально начинается контент
        # (margin_mm от каждого края), отдельным цветом от сетки
        mx = margin_mm * px_per_mm
        my = margin_mm * px_per_mm
        odraw.rectangle(
            [(mx, my), (W - mx, H - my)],
            outline=MARGIN_COLOR, width=2,
        )

    composed = Image.alpha_composite(base_img, overlay).convert("RGB")

    # внешняя рамка = граница настоящей PDF-страницы (не отдельно нарисованный прямоугольник)
    final_draw = ImageDraw.Draw(composed)
    final_draw.rectangle([(0, 0), (W - 1, H - 1)], outline=(0, 0, 0), width=2)

    return composed
