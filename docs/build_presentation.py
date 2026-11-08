"""Build the 5-minute PPC EV Siting Lab presentation.

Run with the bundled Python:
    python docs/build_presentation.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / "docs" / "assets"
OUT = ROOT / "docs" / "PPC_EV_Siting_Lab_5min.pptx"

NAVY = RGBColor(0x0B, 0x23, 0x40)
BLUE = RGBColor(0x00, 0x57, 0xB8)
TEAL = RGBColor(0x00, 0xA6, 0xA6)
ORANGE = RGBColor(0xFF, 0x7A, 0x00)
GOLD = RGBColor(0xFF, 0xD2, 0x3F)
MIST = RGBColor(0xF4, 0xF7, 0xFB)
MUTED = RGBColor(0x5E, 0x76, 0x8E)
LINE = RGBColor(0xD5, 0xE3, 0xF2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SOFT_ORANGE = RGBColor(0xFF, 0xF1, 0xE2)
SOFT_TEAL = RGBColor(0xE5, 0xF7, 0xF5)
SOFT_BLUE = RGBColor(0xE8, 0xF1, 0xFF)
RED = RGBColor(0xB4, 0x2A, 0x2A)

FONT_DISPLAY = "Arial"
FONT_BODY = "Arial"
SW, SH = 13.333, 7.5
M = 0.65


def add_text(
    slide,
    x,
    y,
    w,
    h,
    text,
    *,
    size=18,
    color=NAVY,
    bold=False,
    font=FONT_BODY,
    align=PP_ALIGN.LEFT,
    anchor=MSO_ANCHOR.TOP,
    spacing=1.0,
    space_after=0,
):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    tf.auto_size = None
    for index, line in enumerate(str(text).split("\n")):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        p.space_after = Pt(space_after)
        run = p.add_run()
        run.text = line
        run.font.name = font
        run.font.size = Pt(size)
        run.font.bold = bold
        run.font.color.rgb = color
    return box


def add_rect(slide, x, y, w, h, fill, line=None, radius=False, line_width=1.2):
    shape = slide.shapes.add_shape(
        MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE,
        Inches(x), Inches(y), Inches(w), Inches(h)
    )
    shape.fill.solid()
    shape.fill.fore_color.rgb = fill
    if line is None:
        shape.line.fill.background()
    else:
        shape.line.color.rgb = line
        shape.line.width = Pt(line_width)
    if radius:
        try:
            shape.adjustments[0] = 0.08
        except Exception:
            pass
    return shape


def add_kicker(slide, text, color=BLUE):
    add_rect(slide, M, 0.42, 0.07, 0.26, color)
    add_text(slide, M + 0.16, 0.38, 7.5, 0.3, text.upper(), size=10.5, color=color, bold=True)


def add_title(slide, text, *, size=32, width=12.0, y=0.72, color=NAVY):
    add_text(slide, M, y, width, 1.2, text, size=size, color=color, bold=True, font=FONT_DISPLAY, spacing=0.95)


def add_footer(slide, index, dark=False):
    y = 7.12
    color = RGBColor(0xB9, 0xCD, 0xE1) if dark else MUTED
    line_color = RGBColor(0x2C, 0x4A, 0x68) if dark else LINE
    add_rect(slide, M, y - 0.13, SW - 2 * M, 0.01, line_color)
    add_text(slide, M, y, 8.2, 0.2, "PPC EV Siting Lab  ·  Smarthack 2026  ·  benchmark sintetic", size=8.5, color=color)
    add_text(slide, SW - 1.25, y, 0.6, 0.2, f"{index:02d}", size=8.5, color=color, bold=True, align=PP_ALIGN.RIGHT)


def add_bullets(slide, x, y, w, h, items, *, size=15, color=NAVY, bullet_color=ORANGE, gap=0.1):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    for index, item in enumerate(items):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.space_after = Pt(gap * 72)
        p.line_spacing = 1.12
        run = p.add_run()
        run.text = "•  "
        run.font.name = FONT_BODY
        run.font.size = Pt(size)
        run.font.bold = True
        run.font.color.rgb = bullet_color
        run2 = p.add_run()
        run2.text = item
        run2.font.name = FONT_BODY
        run2.font.size = Pt(size)
        run2.font.color.rgb = color
    return box


def add_pill(slide, x, y, w, h, text, fill=WHITE, color=NAVY, line=LINE, size=10):
    add_rect(slide, x, y, w, h, fill, line, radius=True)
    add_text(slide, x + 0.12, y, w - 0.24, h, text, size=size, color=color, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)


def add_image_contain(slide, path, x, y, w, h, border=True):
    image = Image.open(path)
    iw, ih = image.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    dx, dy = x + (w - dw) / 2, y + (h - dh) / 2
    if border:
        add_rect(slide, dx - 0.04, dy - 0.04, dw + 0.08, dh + 0.08, WHITE, LINE, radius=True)
    slide.shapes.add_picture(str(path), Inches(dx), Inches(dy), Inches(dw), Inches(dh))
    return dx, dy, dw, dh


def add_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def add_step(slide, number, title, body, x, y, w=3.35, h=2.55, color=ORANGE):
    add_rect(slide, x, y, w, h, WHITE, LINE, radius=True)
    add_rect(slide, x, y, 0.09, h, color, radius=True)
    add_text(slide, x + 0.28, y + 0.2, 0.5, 0.5, number, size=28, color=color, bold=True, font=FONT_DISPLAY)
    add_text(slide, x + 0.78, y + 0.22, w - 1.0, 0.55, title, size=17, color=NAVY, bold=True)
    add_text(slide, x + 0.28, y + 0.95, w - 0.55, h - 1.05, body, size=12.5, color=MUTED, spacing=1.18)


def add_number_card(slide, x, y, w, h, number, label, *, fill=MIST, color=NAVY):
    add_rect(slide, x, y, w, h, fill, LINE, radius=True)
    add_text(slide, x + 0.16, y + 0.12, w - 0.32, 0.3, label.upper(), size=8.5, color=MUTED, bold=True)
    add_text(slide, x + 0.16, y + 0.42, w - 0.32, 0.55, number, size=26, color=color, bold=True, font=FONT_DISPLAY)


def slides():
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)
    blank = prs.slide_layouts[6]

    # ---------------------------------------------------------------- 1
    s = prs.slides.add_slide(blank)
    add_rect(s, 0, 0, SW, SH, WHITE)
    add_rect(s, M, 0.52, 0.09, 0.32, ORANGE)
    add_text(s, M + 0.18, 0.48, 6.6, 0.3, "PPC EV SITING LAB  ·  SMARTHACK 2026", size=11, color=BLUE, bold=True)
    add_text(s, M, 1.05, 6.5, 2.15, "Unde pui\n8 stații de\nîncărcare?", size=39, color=NAVY, bold=True, font=FONT_DISPLAY, spacing=0.92)
    add_text(s, M, 3.35, 5.8, 0.8, "Un agent care optimizează rețeaua, nu doar stațiile.", size=19, color=BLUE, bold=True)
    add_text(s, M, 3.95, 5.75, 0.8, "Benchmark sintetic, K configurabil și o explicație pentru fiecare sit recomandat.", size=13, color=MUTED, spacing=1.18)
    add_pill(s, M, 5.05, 2.0, 0.38, "Benchmark sintetic", fill=MIST, size=9.5)
    add_pill(s, M + 2.12, 5.05, 1.75, 0.38, "K = 1…12", fill=SOFT_ORANGE, color=RGBColor(0x93, 0x44, 0x00), line=ORANGE, size=9.5)
    add_pill(s, M + 3.99, 5.05, 1.9, 0.38, "Explicație per sit", fill=SOFT_TEAL, color=RGBColor(0x06, 0x6B, 0x46), line=TEAL, size=9.5)
    add_text(s, M, 6.55, 5.9, 0.3, "Prezentare de 5 minute  ·  demo live în interfața română", size=10, color=MUTED)
    add_image_contain(s, ASSETS / "map-canvas.png", 7.05, 0.58, 5.65, 5.65)
    add_pill(s, 7.45, 6.38, 2.35, 0.42, "85,5% din oracol", fill=NAVY, color=WHITE, line=NAVY, size=11)
    add_text(s, 9.95, 6.42, 2.6, 0.3, "K=8  ·  40 de orașe de test", size=9, color=MUTED)
    add_notes(s, "[0:00–0:20] Întrebarea de start: unde pui opt stații de încărcare într-un oraș? Răspunsul naiv este «unde e multă lume». În următoarele cinci minute arătăm de ce nu este suficient și cum am construit un agent care optimizează rețeaua, nu doar stațiile. Interfața este în română și este demo-ul nostru.")

    # ---------------------------------------------------------------- 2
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Decizia 1  ·  obiectivul")
    add_title(s, "Nu optimizăm stații.\nOptimizăm rețeaua.", size=31)
    add_rect(s, M, 2.12, 5.55, 1.18, NAVY, radius=True)
    add_text(s, M + 0.25, 2.25, 5.1, 0.3, "FUNCÈšIA DE DECIZIE", size=8.5, color=RGBColor(0x9F, 0xC5, 0xE8), bold=True)
    add_text(s, M + 0.25, 2.53, 5.1, 0.55, "beneficiu = rețeaua după − rețeaua înainte", size=16.5, color=WHITE, bold=True, font=FONT_DISPLAY)
    add_bullets(s, M, 3.65, 5.6, 2.5, [
        "Două stații apropiate își fură clienții reciproc.",
        "Utilizarea stației noi nu este beneficiul real.",
        "Penalizarea de canibalizare schimbă complet alegerea.",
    ], size=14.5)
    # simple diagram
    add_text(s, 7.15, 1.95, 5.5, 0.3, "CE SE ÎNTÂMPLĂ FIZIC", size=9, color=MUTED, bold=True)
    add_rect(s, 7.15, 2.35, 5.55, 3.35, MIST, LINE, radius=True)
    for cx, label, fill in ((8.05, "Stație existentă", RGBColor(0xDC, 0xE8, 0xF7)), (9.95, "Stație nouă", SOFT_ORANGE)):
        add_rect(s, cx, 2.85, 1.3, 1.3, fill, NAVY, radius=True)
        add_text(s, cx + 0.15, 3.26, 1.0, 0.4, "EV", size=23, color=NAVY, bold=True, align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        add_text(s, cx - 0.1, 4.27, 1.55, 0.3, label, size=9, color=MUTED, bold=True, align=PP_ALIGN.CENTER)
    add_text(s, 9.4, 3.15, 0.55, 0.4, "↔", size=25, color=ORANGE, bold=True, align=PP_ALIGN.CENTER)
    add_text(s, 7.5, 4.78, 4.85, 0.55, "O parte din cererea noii stații este doar cerere mutată.", size=11.5, color=NAVY, bold=True, align=PP_ALIGN.CENTER)
    add_rect(s, M, 6.35, SW - 2 * M, 0.44, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, M + 0.2, 6.38, SW - 2 * M - 0.4, 0.36, "Decizie: optimizăm utilizarea totală a rețelei, nu cererea brută a fiecărei stații.", size=12, color=RGBColor(0x7A, 0x3D, 0x00), bold=True, anchor=MSO_ANCHOR.MIDDLE)
    add_footer(s, 2)
    add_notes(s, "[0:20–1:10] Aici este ideea centrală. Dacă pui o stație lângă alta, a doua nu creează toată cererea de la zero: o parte din clienți ar fi mers oricum la prima. De aceea optimizăm diferența dintre rețeaua cu stații și rețeaua fără ele. Nu optimizăm stații izolate; optimizăm rețeaua. Această decizie explică de ce un clasament naiv după cerere nu este suficient.")

    # ---------------------------------------------------------------- 3
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Decizia 2  ·  datele")
    add_title(s, "Un benchmark controlat,\nnu o promisiune despre București.", size=30)
    cards = [
        ("DATE REALE", "Ne lipsesc contrafactualele.", "Nu știm cât ar fi fost utilizarea dacă stația ar fi fost în altă parte. Stațiile existente sunt deja selectate de operatori.", SOFT_ORANGE),
        ("SIMULATOR", "Știm răspunsul pentru orice amplasare.", "400 de orașe, cerere latentă ascunsă, stații existente și competiție Huff. Putem rula orice portofoliu.", SOFT_BLUE),
        ("SEPARARE", "Modelul nu vede adevărul.", "Cererea latentă, utilizarea observată și flagul de stație sunt interzise ca inputuri. Antrenare pe orașe, test pe orașe noi.", SOFT_TEAL),
    ]
    for i, (tag, title, body, fill) in enumerate(cards):
        x = M + i * 4.05
        add_rect(s, x, 2.05, 3.75, 2.15, fill, LINE, radius=True)
        add_text(s, x + 0.2, 2.2, 3.3, 0.25, tag, size=8.5, color=BLUE if i != 0 else ORANGE, bold=True)
        add_text(s, x + 0.2, 2.48, 3.35, 0.62, title, size=14.5, color=NAVY, bold=True)
        add_text(s, x + 0.2, 3.15, 3.32, 0.9, body, size=10.2, color=MUTED, spacing=1.13)
    add_text(s, M, 4.55, 3.0, 0.25, "SCARA BENCHMARK-ULUI", size=8.5, color=MUTED, bold=True)
    numbers = [
        ("400", "orașe sintetice"),
        ("501.812", "noduri"),
        ("36.809", "stații existente"),
        ("40", "orașe de test"),
    ]
    for i, (num, label) in enumerate(numbers):
        add_number_card(s, M + i * 3.03, 4.9, 2.78, 0.92, num, label)
    add_rect(s, M, 6.2, SW - 2 * M, 0.48, NAVY, radius=True)
    add_text(s, M + 0.2, 6.23, SW - 2 * M - 0.4, 0.4, '„Sintetic” nu înseamnă „fals”. Înseamnă controlat: știm răspunsul corect pentru fiecare decizie.', size=11.5, color=WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    add_footer(s, 3)
    add_notes(s, "[1:10–1:55] De ce nu folosim date reale? Pentru că nu avem contrafactualul. Nu știm ce s-ar fi întâmplat dacă stația ar fi fost în altă parte, iar stațiile existente sunt deja amplasate de operatori. Simulatorul ne dă un profesor care știe răspunsul pentru orice amplasare. Modelul vede doar caracteristici observabile; adevărul rămâne ascuns. Avem 400 de orașe, 501.812 noduri, 36.809 stații existente și 40 de orașe de test.")

    # ---------------------------------------------------------------- 4
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Decizia 3  ·  agentul")
    add_title(s, "Agentul, în trei pași.", size=33)
    add_text(s, M, 1.7, 11.8, 0.35, "Suficient de simplu pentru a-l explica; suficient de riguros pentru a-l măsura.", size=13, color=MUTED)
    add_step(s, "1", "Simulează lumea", "400 de orașe-graf cu cerere ascunsă, stații existente și competiție Huff. Aici se naște adevărul de referință.", M, 2.35, color=ORANGE)
    arrow1 = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(4.06), Inches(3.43), Inches(0.34), Inches(0.34))
    arrow1.fill.solid(); arrow1.fill.fore_color.rgb = ORANGE; arrow1.line.fill.background()
    add_step(s, "2", "Estimează țintele", 'Un model prezice utilizarea; altul prezice creșterea incrementală. Al doilea răspunde la întrebarea „merită aici?”.', M + 3.6, 2.35, color=BLUE)
    arrow2 = s.shapes.add_shape(MSO_SHAPE.CHEVRON, Inches(7.66), Inches(3.43), Inches(0.34), Inches(0.34))
    arrow2.fill.solid(); arrow2.fill.fore_color.rgb = ORANGE; arrow2.line.fill.background()
    add_step(s, "3", "Alege K situri", "Optimizator greedy: alege un sit, penalizează vecinătatea, recalculează. Se oprește la K.", M + 7.2, 2.35, color=TEAL)
    add_rect(s, M, 5.35, 5.85, 1.15, MIST, LINE, radius=True)
    add_text(s, M + 0.2, 5.47, 5.45, 0.25, "ML LA NIVEL GENERAL", size=8.5, color=BLUE, bold=True)
    add_text(s, M + 0.2, 5.72, 5.45, 0.62, "Rețele mici pe date tabelare; două ținte separate; fără formule în prezentare.", size=11, color=NAVY, bold=True)
    add_rect(s, 6.85, 5.35, 5.85, 1.15, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 7.05, 5.47, 5.45, 0.25, "CE NU ESTE", size=8.5, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_text(s, 7.05, 5.72, 5.45, 0.62, "Nu este un LLM și nu inventează explicații. Este un pipeline de predicție, optimizare și verificare.", size=11, color=RGBColor(0x7A, 0x3D, 0x00), bold=True)
    add_footer(s, 4)
    add_notes(s, "[1:55–2:35] Agentul nu este un chatbot. Este un pipeline în trei pași: simulatorul creează lumea și adevărul de referință; două modele mici estimează utilizarea și creșterea incrementală; optimizatorul greedy alege K situri, cu penalizare pentru vecinătate. Detaliile ML sunt în anexă și în README. Aici important este că fiecare etapă are un rol în decizie.")

    # ---------------------------------------------------------------- 5
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Decizia 4  ·  bugetul")
    add_title(s, "K este o intrare,\nnu o constantă.", size=32)
    add_rect(s, M, 2.0, 1.55, 0.95, NAVY, radius=True)
    add_text(s, M + 0.12, 2.06, 1.3, 0.25, "BUGET LIVE", size=8.5, color=RGBColor(0x9F, 0xC5, 0xE8), bold=True)
    add_text(s, M + 0.12, 2.32, 1.3, 0.45, "1–12", size=25, color=WHITE, bold=True, font=FONT_DISPLAY)
    add_text(s, 2.35, 2.02, 4.2, 0.75, "K=8 este benchmark-ul.\nK=1–8 taie din clasament; 9–12 este extensie demo.", size=13, color=NAVY, bold=True, spacing=1.1)
    add_bullets(s, M, 3.25, 5.6, 2.45, [
        "Harta, lista și clasamentul se filtrează după K.",
        "Captura din oracol și regretul se recalculează pentru fiecare K.",
        "Peste K=8, rândul CSV este marcat indisponibil: artefactul original este K=8.",
        "K=1 are captură mai mare pentru că decizia este mai ușoară, nu pentru că modelul ar fi altul.",
    ], size=12.6, gap=0.08)
    add_image_contain(s, ASSETS / "k-card.png", 6.8, 1.9, 2.9, 3.55)
    add_text(s, 6.8, 5.55, 2.9, 0.3, "Exemplu: K=3 pe un oraș", size=8.5, color=MUTED, align=PP_ALIGN.CENTER)
    add_rect(s, 9.95, 1.95, 2.75, 2.15, MIST, LINE, radius=True)
    add_text(s, 10.1, 2.08, 2.45, 0.25, "CAPTURÄ' DIN ORACOL", size=8.5, color=MUTED, bold=True)
    for i, (k, v, active) in enumerate((("K=1", "87,6%", False), ("K=3", "87,3%", False), ("K=8", "85,5%", True), ("K=12", "84,4%", False))):
        yy = 2.38 + i * 0.39
        add_text(s, 10.1, yy, 0.6, 0.24, k, size=9, color=MUTED, bold=True)
        add_text(s, 10.72, yy - 0.02, 0.95, 0.28, v, size=13, color=ORANGE if active else NAVY, bold=True)
        if active:
            add_text(s, 11.65, yy, 0.85, 0.24, "benchmark", size=7, color=ORANGE, bold=True)
    add_rect(s, 9.95, 4.35, 2.75, 0.95, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 10.1, 4.47, 2.45, 0.25, "DE CE CONTEAZÄ'", size=8.5, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_text(s, 10.1, 4.7, 2.45, 0.52, "Aceeași interfață, alt buget: decizia rămâne verificabilă.", size=9.5, color=RGBColor(0x7A, 0x3D, 0x00), bold=True)
    add_footer(s, 5)
    add_notes(s, "[2:35–3:15] K nu mai este o constantă. În stânga alegi K; în interfață se schimbă numărul de recomandări, markerii, clasamentul și captura din oracol. K=8 este benchmark-ul original. K=1–8 folosesc prefixul selecției greedy, iar K=9–12 este o extensie demo generată cu același model. Pentru K>8 nu avem rând CSV, pentru că artefactul original este K=8; interfața spune asta explicit.")

    # ---------------------------------------------------------------- 6
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Produsul  ·  explicația")
    add_title(s, 'Harta răspunde la „unde?”.\nTrasabilitatea răspunde la „de ce?”.', size=28)
    add_image_contain(s, ASSETS / "map-canvas.png", M, 1.92, 5.55, 4.55)
    add_image_contain(s, ASSETS / "why.png", 6.55, 1.55, 5.95, 4.8)
    add_text(s, M, 6.55, 5.6, 0.3, "Fundal alb: doar nodurile, nu străzile sau granițele.", size=8.5, color=MUTED, align=PP_ALIGN.CENTER)
    add_text(s, 6.55, 6.55, 5.95, 0.3, "Rang, factori, mediana orașului, încredere și rândul CSV.", size=8.5, color=MUTED, align=PP_ALIGN.CENTER)
    add_footer(s, 6)
    add_notes(s, "[3:15–4:10] Aici este produsul. Harta este albă intenționat: nu sugerează o precizie geografică pe care nu o avem. Fiecare sit are rang, halou proporțional cu creșterea estimată și, la dublu-click, o trasabilitate completă. Arătăm de ce agentul l-a ales: rangul din K, comparația cu media, factorii locali cu valoare și mediană, contextul, încrederea și rândul CSV. Nu ascundem artefactul.")

    # ---------------------------------------------------------------- 7
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Rezultatele  ·  onestitate")
    add_title(s, "85,5% din oracol,\ncu limitele la vedere.", size=31)
    add_text(s, M, 2.0, 4.35, 0.3, "K=8  ·  40 DE ORAȘE DE TEST", size=9, color=MUTED, bold=True)
    add_text(s, M, 2.32, 3.4, 1.15, "85,5%", size=58, color=ORANGE, bold=True, font=FONT_DISPLAY)
    add_text(s, M, 3.42, 4.3, 0.7, "din beneficiul incremental al oracolului", size=13, color=NAVY, bold=True)
    add_text(s, M, 4.25, 4.2, 0.75, "88,4% pe orașele OOD  ·  14 cazuri de verificare  ·  320 acțiuni", size=11, color=MUTED)
    add_rect(s, M, 5.15, 4.55, 1.05, MIST, LINE, radius=True)
    add_text(s, M + 0.2, 5.25, 4.2, 0.25, "CE NU PRETINDEM", size=8.5, color=BLUE, bold=True)
    add_text(s, M + 0.2, 5.5, 4.2, 0.55, "Nu este 100%, nu este optim global și nu este o prognoză reală pentru București.", size=10.5, color=NAVY, bold=True)
    # bar comparison
    add_text(s, 5.75, 1.98, 6.8, 0.3, "PONDERE DIN UTILITATEA INCREMENTALÄ'", size=9, color=MUTED, bold=True)
    bars = [
        ("Model + optimizator", 85.5, "85,5%", ORANGE, True),
        ("Populație", 11.3, "11,3%", BLUE, False),
        ("Aleator", 8.7, "8,7%", TEAL, False),
        ("Index manual", 7.5, "7,5%", NAVY, False),
        ("Activitate", 5.2, "5,2%", MUTED, False),
    ]
    for i, (label, value, text, color, active) in enumerate(bars):
        y = 2.45 + i * 0.72
        add_text(s, 5.75, y, 1.6, 0.25, label, size=9.5, color=NAVY, bold=active)
        add_rect(s, 7.55, y + 0.03, 3.7, 0.18, RGBColor(0xEC, 0xF2, 0xF9), None, radius=True)
        add_rect(s, 7.55, y + 0.03, max(0.08, 3.7 * value / 100), 0.18, color, None, radius=True)
        add_text(s, 11.38, y - 0.02, 0.75, 0.28, text, size=11, color=color, bold=True, align=PP_ALIGN.RIGHT)
    add_text(s, 7.55, 6.15, 4.9, 0.3, "K=8 benchmark; baseline-urile folosesc același buget.", size=8.5, color=MUTED)
    add_footer(s, 7)
    add_notes(s, "[4:10–4:45] Pe 40 de orașe nevăzute, capturăm 85,5% din beneficiul oracolului. Baseline-ul cu populația ia 11,3%, aleatorul 8,7%, indexul manual 7,5%. Pe orașele OOD, cu parametri schimbați, capturăm 88,4%. Nu pretindem 100%, nu pretindem optim global și nu pretindem că este o prognoză reală pentru București. Cele 14 cazuri de verificare sunt vizibile în interfață.")

    # ---------------------------------------------------------------- 8
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Închidere  ·  decizii")
    add_title(s, "Ce am decis și ce urmează.", size=34)
    columns = [
        ("AM DECIS", [
            "Să optimizăm utilizarea totală, nu cererea brută.",
            "Să controlăm adevărul printr-un simulator, nu să promitem date reale.",
            "Să facem K configurabil și să marcăm clar extensia >8.",
            "Să explicăm fiecare sit, nu doar să afișăm un punct.",
        ], SOFT_TEAL, TEAL, RGBColor(0x06, 0x6B, 0x46)),
        ("NU PRETINDEM", [
            "Că 85,5% se transferă direct pe București.",
            "Că optimizatorul este optim global.",
            "Că acoperim costuri, permisare, rețea sau echitate.",
            "Că încrederea este o probabilitate calibrată.",
        ], SOFT_ORANGE, ORANGE, RGBColor(0x7A, 0x3D, 0x00)),
        ("URMEAZÄ'", [
            "Calibrare pe date reale de utilizare.",
            "Costuri, capacitate de rețea și permisare.",
            "Pilot pe un oraș, cu revizuire umană.",
            "Extinderea explicațiilor pentru factori de politici publice.",
        ], SOFT_BLUE, BLUE, RGBColor(0x0B, 0x3A, 0x6B)),
    ]
    for i, (head, items, fill, line, color) in enumerate(columns):
        x = M + i * 4.05
        add_rect(s, x, 2.0, 3.75, 3.8, fill, line, radius=True)
        add_text(s, x + 0.2, 2.15, 3.35, 0.3, head, size=9, color=color, bold=True)
        add_bullets(s, x + 0.2, 2.55, 3.35, 3.0, items, size=10.8, bullet_color=line, gap=0.1)
    add_text(s, M, 6.25, 12.0, 0.5, "Un model care nu poate fi explicat nu este o decizie.  ·  Întrebări?", size=15, color=NAVY, bold=True)
    add_footer(s, 8)
    add_notes(s, "[4:45–5:00] Închidem cu ce am decis și ce nu pretindem. Decizia centrală este să optimizăm rețeaua, nu stații izolate. Am construit un benchmark controlat, am făcut K configurabil și am legat fiecare recomandare de o explicație și de un rând CSV. Următorul pas este calibrarea pe date reale, cu costuri, rețea și permisare. Vă mulțumim; întrebări?")

    # ---------------------------------------------------------------- appendix A
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Anexă  ·  pentru Q&A", MUTED)
    add_title(s, "Registru de decizii", size=29)
    add_text(s, M, 1.65, 11.8, 0.3, "Ce am ales, ce alternativă exista și ce compromis acceptăm.", size=12, color=MUTED)
    rows = [
        ("Date sintetice", "Date reale", "Contrafactuale + control", "Nu este București real"),
        ("Două modele", "Un singur model", "Utilizare și creștere sunt ținte diferite", "Mai multă complexitate"),
        ("Greedy K", "Top K naiv", "Penalizează canibalizarea", "Nu este optim global"),
        ("K=1–12", "K=8 fix", "Demonstrație de buget configurabil", ">8 este extensie demo"),
        ("Hartă albă", "Hartă geografică", "Evită precizia falsă", "Mai puțin context vizual"),
        ("Why trace", "Doar rang", "Decizie verificabilă", "Mai mult spațiu în UI"),
    ]
    table = s.shapes.add_table(len(rows) + 1, 4, Inches(M), Inches(2.1), Inches(12.0), Inches(4.35)).table
    table.columns[0].width = Inches(2.25)
    table.columns[1].width = Inches(2.25)
    table.columns[2].width = Inches(4.2)
    table.columns[3].width = Inches(3.3)
    for row in table.rows:
        row.height = Inches(0.52)
    headers = ["Decizie", "Alternativă", "De ce", "Compromis"]
    for j, h in enumerate(headers):
        cell = table.cell(0, j)
        cell.text = h
        for p in cell.text_frame.paragraphs:
            for r in p.runs:
                r.font.name = FONT_BODY
                r.font.size = Pt(10)
                r.font.bold = True
                r.font.color.rgb = WHITE
        cell.fill.solid()
        cell.fill.fore_color.rgb = NAVY
    for i, row in enumerate(rows, start=1):
        for j, value in enumerate(row):
            cell = table.cell(i, j)
            cell.text = value
            for p in cell.text_frame.paragraphs:
                for r in p.runs:
                    r.font.name = FONT_BODY
                    r.font.size = Pt(9.5)
                    r.font.color.rgb = NAVY
            cell.fill.solid()
            cell.fill.fore_color.rgb = WHITE if i % 2 else MIST
    add_text(s, M, 6.62, 12.0, 0.3, "Anexă — nu se prezintă în cele 5 minute; se folosește la întrebări.", size=8.5, color=MUTED)
    add_footer(s, 9)
    add_notes(s, "Anexă pentru Q&A. Aici intră întrebările despre compromisuri: de ce sintetic, de ce două modele, de ce greedy, de ce K=12, de ce hartă albă. Răspunsurile sunt scurte; nu citi tabelul.")

    # ---------------------------------------------------------------- appendix B
    s = prs.slides.add_slide(blank)
    add_kicker(s, "Anexă  ·  ML în puține cuvinte", MUTED)
    add_title(s, "Ce face modelul, fără formule", size=30)
    add_step(s, "A", "24 de caracteristici", "Populație, activitate, acces, competiție, distanțe și context urban. Toate ar fi observabile înainte de construcție.", M, 2.0, w=3.6, h=2.0, color=ORANGE)
    add_step(s, "B", "Două ținte", "Utilizarea absolută a unei stații și creșterea incrementală a unui candidat. A doua este folosită la clasare.", M + 3.95, 2.0, w=3.6, h=2.0, color=BLUE)
    add_step(s, "C", "Trei seed-uri", "Media a trei rețele mici; dezacordul dintre ele devine semnal de incertitudine și trimite cazurile în review.", M + 7.9, 2.0, w=3.6, h=2.0, color=TEAL)
    add_rect(s, M, 4.35, 5.9, 1.45, MIST, LINE, radius=True)
    add_text(s, M + 0.2, 4.47, 5.5, 0.25, "CE NE PROTEJEAZÄ'", size=8.5, color=BLUE, bold=True)
    add_bullets(s, M + 0.2, 4.75, 5.4, 0.95, [
        "Split pe orașe, nu pe rânduri.",
        "Fără cerere latentă sau utilizare observată ca input.",
        "Baseline-uri calculate pe aceleași orașe.",
    ], size=9.5, gap=0.02)
    add_rect(s, 6.9, 4.35, 5.8, 1.45, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 7.1, 4.47, 5.4, 0.25, "CE RĂMÂNE DIFICIL", size=8.5, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_bullets(s, 7.1, 4.75, 5.35, 0.95, [
        "Creșterea este o diferență între două simulări.",
        "Oracolul este greedy, nu optim global.",
        "Încrederea nu este calibrată.",
    ], size=9.5, gap=0.02, bullet_color=ORANGE)
    add_text(s, M, 6.15, 12.0, 0.55, "R² utilizare 0,871  ·  Spearman 0,931  ·  R² creștere 0,735  ·  captură 85,5%  ·  OOD 88,4%", size=12, color=NAVY, bold=True)
    add_footer(s, 10)
    add_notes(s, "Anexă tehnică scurtă. Dacă întrebarea merge spre ML: 24 de caracteristici observabile, două modele cu aceeași arhitectură mică, trei seed-uri și dezacordul lor ca semnal de incertitudine. Split pe orașe, fără scurgeri de adevăr. Rezultatele sunt bune, dar creșterea rămâne mai greu de prezis decât utilizarea.")

    prs.save(OUT)
    print(f"wrote {OUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    slides()

