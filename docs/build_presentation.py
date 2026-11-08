"""Build the 5-minute PPC EV Siting Lab presentation.

The deck is deliberately narrative: one idea per slide, few keywords, and
speaker notes that explain the project without requiring ML background.

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
SOFT_BLUE = RGBColor(0xE8, 0xF1, 0xFF)
SOFT_TEAL = RGBColor(0xE5, 0xF7, 0xF5)

FONT = "Arial"
SW, SH = 13.333, 7.5
M = 0.72


def add_text(slide, x, y, w, h, text, *, size=18, color=NAVY, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.05):
    box = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    tf = box.text_frame
    tf.clear()
    tf.word_wrap = True
    tf.margin_left = 0
    tf.margin_right = 0
    tf.margin_top = 0
    tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    for index, line in enumerate(str(text).split("\n")):
        p = tf.paragraphs[0] if index == 0 else tf.add_paragraph()
        p.alignment = align
        p.line_spacing = spacing
        r = p.add_run()
        r.text = line
        r.font.name = FONT
        r.font.size = Pt(size)
        r.font.bold = bold
        r.font.color.rgb = color
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
            shape.adjustments[0] = 0.07
        except Exception:
            pass
    return shape


def add_top(slide, number, label, title, *, title_size=32, title_width=11.8):
    add_text(slide, M, 0.36, 0.55, 0.3, f"{number:02d}", size=10, color=ORANGE, bold=True)
    add_text(slide, M + 0.48, 0.36, 6.0, 0.3, label.upper(), size=9.5, color=MUTED, bold=True)
    add_text(slide, M, 0.78, title_width, 1.35, title, size=title_size, color=NAVY, bold=True, spacing=0.98)


def add_footer(slide, number):
    add_rect(slide, M, 7.05, SW - 2 * M, 0.01, LINE)
    add_text(slide, M, 7.15, 8.8, 0.2,
             "PPC EV Siting Lab  ·  24h to Power PPC  ·  Smarthack XI 2026",
             size=8.5, color=MUTED)
    add_text(slide, SW - 1.1, 7.15, 0.4, 0.2, f"{number:02d}", size=8.5, color=MUTED,
             bold=True, align=PP_ALIGN.RIGHT)


def add_body(slide, x, y, w, h, text, *, size=17, color=NAVY, bold=False, spacing=1.18):
    add_text(slide, x, y, w, h, text, size=size, color=color, bold=bold, spacing=spacing)


def add_image(slide, path, x, y, w, h, border=True):
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


def slide_title(prs, blank):
    s = prs.slides.add_slide(blank)
    add_rect(s, 0, 0, SW, SH, WHITE)
    add_rect(s, M, 0.55, 0.09, 0.32, ORANGE)
    add_text(s, M + 0.18, 0.51, 6.6, 0.3,
             "24H TO POWER PPC  ·  SMARTHACK XI 2026",
             size=10.5, color=BLUE, bold=True)
    add_text(s, M, 1.12, 6.4, 2.15,
             "Unde punem\n8 stații de\nîncărcare?",
             size=38, color=NAVY, bold=True, spacing=0.92)
    add_text(s, M, 3.48, 5.85, 0.8,
             "Un agent care alege pentru întreaga rețea,\nnu pentru o singură stație.",
             size=18, color=BLUE, bold=True, spacing=1.15)
    add_text(s, M, 4.42, 5.4, 0.6,
             "O poveste despre date, decizie și explicație.",
             size=13, color=MUTED)
    add_text(s, M, 6.55, 6.0, 0.3,
             "Prezentare de 5 minute  ·  demo live în română",
             size=9.5, color=MUTED)
    add_image(s, ASSETS / "map-canvas.png", 7.0, 0.58, 5.7, 5.65)
    add_rect(s, 7.35, 6.35, 2.45, 0.42, NAVY, NAVY, radius=True)
    add_text(s, 7.45, 6.37, 2.25, 0.36,
             "85,5% la K=8", size=11, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 9.95, 6.42, 2.7, 0.3, "40 de orașe de test", size=9, color=MUTED)
    add_notes(s, "[0:00–0:20] Întrebarea este simplă: ai buget pentru opt stații într-un oraș. Unde le pui? În următoarele cinci minute arătăm de ce răspunsul evident nu este suficient și cum am construit un agent care alege pentru întreaga rețea. Interfața este în română și o folosim ca demo.")
    return s


def slide_naive(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 2, "Răspunsul evident", "Unde e multă lume.", title_size=36, title_width=9.5)
    add_body(s, M, 2.35, 6.3, 0.8,
             "Punem stațiile în zonele aglomerate.\nPare cea mai simplă alegere.",
             size=18, spacing=1.2)
    add_text(s, M, 4.25, 6.7, 0.7, "Dar o stație nu funcționează singură.", size=22,
             color=ORANGE, bold=True)
    # population dots
    for i, (x, y) in enumerate([
        (8.3, 2.35), (8.9, 2.15), (9.5, 2.55), (10.1, 2.3), (10.7, 2.6),
        (8.7, 3.0), (9.3, 3.25), (10.0, 3.05), (10.6, 3.35), (11.1, 3.0),
        (9.0, 3.8), (9.7, 3.65), (10.3, 3.9), (11.0, 3.75),
    ]):
        c = s.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(0.17), Inches(0.17))
        c.fill.solid(); c.fill.fore_color.rgb = RGBColor(0x9D, 0xB8, 0xD6); c.line.fill.background()
    add_text(s, 8.35, 4.35, 4.0, 0.3, "multe puncte = multă cerere", size=9.5, color=MUTED,
             align=PP_ALIGN.CENTER)
    add_text(s, 9.55, 4.95, 1.8, 1.1, "?", size=68, color=ORANGE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(s, 8.3, 5.95, 4.1, 0.5, "Dar unde anume?", size=15, color=NAVY, bold=True,
             align=PP_ALIGN.CENTER)
    add_footer(s, 2)
    add_notes(s, "[0:20–0:40] Răspunsul naiv este «unde e multă lume». Este o intuiție bună, dar incompletă. O stație nu există izolat: ea concurează cu stațiile din jur. De aici începe problema noastră.")
    return s


def slide_cannibalization(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 3, "Ce se întâmplă de fapt", "A doua stație nu adaugă toată cererea.")
    add_body(s, M, 2.15, 11.4, 0.65,
             "O parte din clienții noii stații ar fi mers oricum la stația vecină.",
             size=18)
    # cards
    add_rect(s, 1.05, 3.05, 3.0, 1.55, SOFT_BLUE, LINE, radius=True)
    add_text(s, 1.25, 3.28, 2.6, 0.3, "STAȚIE EXISTENTĂ", size=9, color=BLUE, bold=True)
    add_text(s, 1.25, 3.65, 2.6, 0.55, "clienți", size=26, color=NAVY, bold=True)
    add_rect(s, 8.55, 3.05, 3.0, 1.55, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 8.75, 3.28, 2.6, 0.3, "STAȚIE NOUĂ", size=9, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_text(s, 8.75, 3.65, 2.6, 0.55, "aceiași clienți?", size=20, color=RGBColor(0x7A, 0x3D, 0x00), bold=True)
    # arrow
    arrow = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(5.25), Inches(3.5), Inches(2.1), Inches(0.5))
    arrow.fill.solid(); arrow.fill.fore_color.rgb = ORANGE; arrow.line.fill.background()
    add_text(s, 5.15, 4.12, 2.35, 0.3, "o parte se mută", size=10, color=ORANGE, bold=True,
             align=PP_ALIGN.CENTER)
    add_rect(s, M, 5.45, SW - 2 * M, 0.92, NAVY, radius=True)
    add_text(s, M + 0.35, 5.58, SW - 2 * M - 0.7, 0.62,
             "Beneficiul real = rețeaua după  −  rețeaua înainte",
             size=20, color=WHITE, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    add_footer(s, 3)
    add_notes(s, "[0:40–1:05] Dacă punem o stație lângă alta, a doua nu creează toată cererea de la zero. O parte din clienți se mută de la prima. De aceea nu întrebăm cât de folosită este stația în sine, ci câtă cerere nouă aduce pentru întreaga rețea.")
    return s


def slide_question(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 4, "Întrebarea corectă", "Așa că întrebarea se schimbă.", title_size=34)
    add_rect(s, M, 2.2, 11.9, 2.0, MIST, LINE, radius=True)
    add_text(s, M + 0.45, 2.45, 11.0, 0.85,
             "Câtă cerere nouă aduce acest sit\npentru întreaga rețea?",
             size=27, color=NAVY, bold=True, spacing=1.1)
    add_body(s, M, 4.75, 11.2, 0.65,
             "Nu cât de folosită este stația în sine.",
             size=18, color=MUTED)
    add_text(s, M, 5.65, 11.2, 0.55,
             "Aceasta este întrebarea pe care o optimizăm.",
             size=18, color=ORANGE, bold=True)
    add_footer(s, 4)
    add_notes(s, "[1:05–1:25] Aici apare schimbarea importantă. Nu ne interesează doar cât de bună este o stație. Ne interesează diferența pe care o aduce pentru rețea. Este întrebarea care transformă problema într-una de decizie, nu doar de predicție.")
    return s


def slide_data_gap(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 5, "De ce nu ajung datele reale", "Datele reale nu pot răspunde la această întrebare.")
    # two columns
    add_rect(s, M, 3.05, 5.7, 2.5, SOFT_BLUE, LINE, radius=True)
    add_text(s, M + 0.25, 3.22, 5.2, 0.3, "CE ȘTIM", size=9, color=BLUE, bold=True)
    add_text(s, M + 0.25, 3.55, 5.15, 1.5,
             "Unde sunt stațiile.\nCât se folosesc astăzi.",
             size=22, color=NAVY, bold=True, spacing=1.3)
    add_rect(s, 6.6, 3.05, 5.9, 2.5, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 6.85, 3.22, 5.35, 0.3, "CE NU ȘTIM", size=9, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_text(s, 6.85, 3.55, 5.3, 1.5,
             "Ce s-ar fi întâmplat\ndacă stația ar fi fost\nîn altă parte.",
             size=22, color=RGBColor(0x7A, 0x3D, 0x00), bold=True, spacing=1.25)
    add_text(s, M, 6.0, 11.4, 0.5,
             "Iar stațiile existente au fost deja puse în locuri bune. Nu sunt o probă aleatoare.",
             size=14, color=MUTED)
    add_footer(s, 5)
    add_notes(s, "[1:25–1:50] Datele reale ne spun unde sunt stațiile și cât se folosesc. Nu ne spun ce s-ar fi întâmplat dacă erau în altă parte. Iar stațiile existente nu sunt amplasate aleatoriu: operatorii le-au pus deja în locuri în care se așteptau la cerere. Așa că avem nevoie de altceva.")
    return s


def slide_simulator(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 6, "Soluția", "Așa că am construit un oraș pe care îl putem întreba.")
    add_image(s, ASSETS / "map-canvas.png", M, 2.0, 5.1, 4.75)
    add_text(s, 6.2, 2.0, 5.9, 0.45, "400 de orașe sintetice.", size=25, color=NAVY, bold=True)
    add_text(s, 6.2, 2.55, 6.0, 0.55, "501.812 noduri. 36.809 stații existente.", size=15, color=BLUE, bold=True)
    add_body(s, 6.2, 3.3, 6.0, 1.35,
             "Fiecare nod are o cerere ascunsă și vecini.\nPutem muta stațiile oriunde și putem vedea\nce se întâmplă cu întreaga rețea.",
             size=16, spacing=1.25)
    add_text(s, 6.2, 5.2, 5.95, 0.5,
             "Nu este București. Este un loc controlat.",
             size=14, color=ORANGE, bold=True)
    add_footer(s, 6)
    add_notes(s, "[1:50–2:15] Am construit un simulator cu 400 de orașe. Fiecare are o cerere ascunsă și stații existente. Pentru că totul este generat de cod, putem pune stații oriunde și putem măsura rezultatul. Nu pretindem că este București: este un teren controlat în care putem experimenta.")
    return s


def slide_separation(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 7, "Cum rămâne testul corect", "Simulatorul știe răspunsul. Modelul vede doar indiciile.")
    add_rect(s, M, 2.55, 5.6, 3.2, SOFT_BLUE, LINE, radius=True)
    add_text(s, M + 0.25, 2.75, 5.1, 0.3, "SIMULATORUL", size=9, color=BLUE, bold=True)
    add_body(s, M + 0.25, 3.1, 5.1, 2.3,
             "•  cererea ascunsă\n•  efectul oricărei stații\n•  răspunsul corect",
             size=18, spacing=1.5)
    add_rect(s, 6.55, 2.55, 5.95, 3.2, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 6.8, 2.75, 5.4, 0.3, "MODELUL", size=9, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_body(s, 6.8, 3.1, 5.4, 2.3,
             "•  populație și activitate\n•  acces și infrastructură\n•  competiția existentă",
             size=18, spacing=1.5)
    add_text(s, M, 6.15, 11.3, 0.5, "Așa modelul nu poate trișa.", size=16, color=ORANGE, bold=True)
    add_footer(s, 7)
    add_notes(s, "[2:15–2:35] Separarea este esențială. Simulatorul știe cererea reală și poate spune ce se întâmplă în orice scenariu. Modelul vede doar lucruri pe care un operator le-ar putea ști înainte să construiască: populație, activitate, acces, competiție. Nu vede răspunsul.")
    return s


def slide_two_questions(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 8, "Partea de învățare", "Modelul învață două întrebări diferite.")
    add_rect(s, M, 2.15, 5.8, 2.8, WHITE, LINE, radius=True)
    add_text(s, M + 0.25, 2.35, 5.3, 0.3, "ÎNTREBAREA 1", size=9, color=BLUE, bold=True)
    add_text(s, M + 0.25, 2.75, 5.3, 0.8, "Cât se folosește\no stație?", size=24, color=NAVY, bold=True, spacing=1.1)
    add_text(s, M + 0.25, 3.85, 5.2, 0.7, "Ne ajută să estimăm valoarea absolută.", size=13, color=MUTED)
    add_rect(s, 6.8, 2.15, 5.7, 2.8, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 7.05, 2.35, 5.2, 0.3, "ÎNTREBAREA 2", size=9, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_text(s, 7.05, 2.75, 5.2, 0.8, "Câtă cerere nouă\naduce?", size=24, color=NAVY, bold=True, spacing=1.1)
    add_text(s, 7.05, 3.85, 5.1, 0.7, "Este întrebarea care decide unde punem stația.", size=13, color=RGBColor(0x7A, 0x3D, 0x00))
    add_text(s, M, 5.55, 11.4, 0.65,
             "A doua întrebare este cea care contează pentru business.",
             size=17, color=ORANGE, bold=True)
    add_text(s, M, 6.25, 11.2, 0.35,
             "Aici intră partea de machine learning; restul este decizie.",
             size=11, color=MUTED)
    add_footer(s, 8)
    add_notes(s, "[2:35–2:55] Modelul nu învață un singur lucru. Primul model estimează cât se folosește o stație. Al doilea estimează câtă cerere nouă aduce pentru rețea. A doua întrebare este cea care contează pentru alegerea amplasării. Aici este partea de ML; nu trebuie să știm formulele ca să înțelegem decizia.")
    return s


def slide_greedy(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 9, "Cum se alege", "Alegerea se face pas cu pas.")
    add_body(s, M, 2.1, 11.2, 0.55,
             "După fiecare alegere, siturile vecine devin mai puțin atractive.",
             size=18)
    # eight steps
    for i in range(8):
        x = 1.35 + i * 1.42
        fill = ORANGE if i < 3 else (RGBColor(0xFF, 0xF1, 0xE2) if i == 3 else MIST)
        line = ORANGE if i < 4 else LINE
        add_rect(s, x, 3.55, 1.0, 0.72, fill, line, radius=True)
        add_text(s, x, 3.62, 1.0, 0.55, str(i + 1), size=22,
                 color=WHITE if i < 3 else NAVY, bold=True, align=PP_ALIGN.CENTER,
                 anchor=MSO_ANCHOR.MIDDLE)
    # connecting line
    add_rect(s, 1.8, 4.82, 9.9, 0.02, LINE)
    add_text(s, 1.35, 5.02, 10.7, 0.45,
             "La fiecare pas, modelul recalculează toți candidații rămași.",
             size=12, color=MUTED)
    add_rect(s, M, 5.85, SW - 2 * M, 0.78, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, M + 0.3, 5.95, SW - 2 * M - 0.6, 0.55,
             "Altfel, toate cele opt stații ar putea ajunge în același cartier.",
             size=15, color=RGBColor(0x7A, 0x3D, 0x00), bold=True,
             anchor=MSO_ANCHOR.MIDDLE)
    add_footer(s, 9)
    add_notes(s, "[2:55–3:20] Alegerea nu se face dintr-o singură formulă globală. Se face pas cu pas: alegem un sit, apoi recalculăm și penalizăm candidații apropiați. Altfel, toate cele opt stații ar putea ajunge în același cartier și ar intra în competiție una cu alta.")
    return s


def slide_k(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 10, "Bugetul", "Câte stații punem? K este bugetul.", title_size=32)
    add_image(s, ASSETS / "k-card.png", 7.0, 1.85, 3.25, 3.9)
    add_text(s, M, 2.0, 5.5, 0.45, "K=8 este benchmark-ul.", size=24, color=NAVY, bold=True)
    add_body(s, M, 2.65, 5.4, 1.05,
             "În interfață poți alege orice valoare\nîntre 1 și 12.",
             size=18, spacing=1.25)
    add_body(s, M, 3.95, 5.5, 1.1,
             "Schimbi K și se schimbă lista, harta,\nclasamentul și captura din referință.",
             size=14, color=MUTED, spacing=1.2)
    add_text(s, M, 5.35, 5.7, 0.45,
             "Peste 8 este o extensie demo; CSV-ul original rămâne K=8.",
             size=11, color=ORANGE, bold=True)
    add_text(s, 7.0, 5.95, 3.4, 0.3, "Exemplu: K=3 pe un oraș", size=9, color=MUTED,
             align=PP_ALIGN.CENTER)
    add_footer(s, 10)
    add_notes(s, "[3:20–3:45] K este bugetul. Benchmark-ul nostru este K=8, dar interfața permite și K=1–12. Când schimbi K, se schimbă lista, harta și captura din referință. Peste 8 este o extensie demo, iar CSV-ul original rămâne K=8. Nu ascundem diferența.")
    return s


def slide_why(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 11, "Explicația", "Fiecare alegere poate fi întrebată: de ce aici?")
    add_image(s, ASSETS / "why.png", 6.8, 1.75, 5.1, 5.0)
    add_text(s, M, 2.05, 5.7, 0.4, "Nu arătăm doar un punct.", size=22, color=NAVY, bold=True)
    add_text(s, M, 2.55, 5.7, 0.4, "Arătăm decizia din spatele lui.", size=22, color=ORANGE, bold=True)
    add_body(s, M, 3.35, 5.55, 2.1,
             "•  rangul în buget\n•  factorii care au contat\n•  contextul și încrederea",
             size=17, spacing=1.45)
    add_text(s, M, 5.75, 5.5, 0.5,
             "Fiecare explicație se termină cu rândul CSV.",
             size=11, color=MUTED)
    add_footer(s, 11)
    add_notes(s, "[3:45–4:05] Aici este partea de produs care ne place cel mai mult. Nu arătăm doar un punct pe hartă. Când apeși pe un sit, vezi rangul, factorii care au contat, contextul și încrederea. Iar la final vezi rândul CSV exact. Decizia poate fi verificată.")
    return s


def slide_results(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 12, "Rezultatul", "85,5% din beneficiul unei soluții perfecte.")
    add_text(s, M, 2.0, 4.4, 0.3, "K=8  ·  40 DE ORAȘE DE TEST", size=9, color=MUTED, bold=True)
    add_text(s, M, 2.35, 3.9, 1.2, "85,5%", size=62, color=ORANGE, bold=True)
    add_text(s, M, 3.55, 4.3, 0.7, "din beneficiul incremental\n al referinței perfecte", size=14, color=NAVY, bold=True, spacing=1.1)
    add_text(s, M, 4.55, 4.4, 0.6, "Aproape opt ori mai bine\ndecât „unde e populație”.", size=13, color=MUTED, spacing=1.15)
    # bars
    add_text(s, 5.85, 2.0, 6.6, 0.3, "CÂT DIN BENEFICIU CAPTUREAZĂ", size=9, color=MUTED, bold=True)
    bars = [
        ("Modelul nostru", 85.5, "85,5%", ORANGE),
        ("După populație", 11.3, "11,3%", BLUE),
        ("Aleator", 8.7, "8,7%", TEAL),
        ("Index manual", 7.5, "7,5%", NAVY),
        ("După activitate", 5.2, "5,2%", MUTED),
    ]
    for i, (label, value, text, color) in enumerate(bars):
        y = 2.5 + i * 0.68
        add_text(s, 5.85, y, 1.8, 0.25, label, size=10.5, color=NAVY, bold=(i == 0))
        add_rect(s, 7.75, y + 0.02, 3.6, 0.16, RGBColor(0xEC, 0xF2, 0xF9), None, radius=True)
        add_rect(s, 7.75, y + 0.02, max(0.08, 3.6 * value / 100), 0.16, color, None, radius=True)
        add_text(s, 11.45, y - 0.04, 0.85, 0.28, text, size=10.5, color=color, bold=True,
                 align=PP_ALIGN.RIGHT)
    add_text(s, M, 6.1, 11.5, 0.55,
             "Nu este 100% și nu este optim global. Este un rezultat măsurat pe orașe nevăzute.",
             size=11.5, color=MUTED)
    add_footer(s, 12)
    add_notes(s, "[4:05–4:30] Pe 40 de orașe nevăzute, modelul capturează 85,5% din beneficiul unei soluții care știe adevărul. O regulă simplă care pune stații după populație ia 11,3%. Este o diferență de aproape opt ori. Nu este 100% și nu este optim global: este un rezultat măsurat, cu limitele la vedere.")
    return s


def slide_close(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 13, "Închidere", "Ce am decis și ce nu pretindem.", title_size=34)
    # decisions
    decisions = [
        ("AM OPTIMIZAT", "rețeaua,\nnu stația izolată", SOFT_TEAL, TEAL),
        ("AM CONSTRUIT", "un benchmark\ncontrolat", SOFT_BLUE, BLUE),
        ("AM LĂSAT", "omul în buclă\npentru cazurile incerte", SOFT_ORANGE, ORANGE),
    ]
    for i, (head, body, fill, line) in enumerate(decisions):
        x = M + i * 4.05
        add_rect(s, x, 2.1, 3.7, 1.9, fill, line, radius=True)
        add_text(s, x + 0.2, 2.25, 3.3, 0.25, head, size=8.5, color=line, bold=True)
        add_text(s, x + 0.2, 2.6, 3.25, 0.95, body, size=17, color=NAVY, bold=True, spacing=1.12)
    add_text(s, M, 4.45, 5.4, 0.3, "CE NU PRETINDEM", size=8.5, color=ORANGE, bold=True)
    add_body(s, M, 4.75, 11.4, 1.0,
             "Nu este o prognoză reală pentru București.  ·  Nu include costuri, permisare sau rețea reală.  ·  Nu este optim global.",
             size=13, spacing=1.25)
    add_text(s, M, 6.05, 11.5, 0.55,
             "Un model care nu poate fi explicat nu este o decizie.",
             size=18, color=NAVY, bold=True)
    add_text(s, SW - 2.8, 6.1, 2.0, 0.4, "Întrebări?", size=16, color=ORANGE, bold=True,
             align=PP_ALIGN.RIGHT)
    add_footer(s, 13)
    add_notes(s, "[4:30–5:00] Am optimizat rețeaua, nu stația izolată. Am construit un benchmark controlat și am lăsat omul în buclă pentru cazurile incerte. Nu pretindem că este o prognoză pentru București, nu avem costuri sau permisare și nu este optim global. Un model care nu poate fi explicat nu este o decizie. Vă mulțumim; întrebări?")
    return s


def slide_appendix(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 14, "Anexă pentru întrebări", "Dacă întreabă de partea tehnică.", title_size=30)
    cards = [
        ("24", "indicii pentru fiecare nod:\npopulație, acces, competiție,\ncontext urban", ORANGE),
        ("2", "întrebări învățate:\ncât se folosește o stație\nși câtă cerere nouă aduce", BLUE),
        ("3", "modele mici, cu seed-uri\ndiferite; dezacordul lor\neste semnal de incertitudine", TEAL),
    ]
    for i, (num, text, color) in enumerate(cards):
        x = M + i * 4.05
        add_rect(s, x, 2.0, 3.7, 2.0, WHITE, LINE, radius=True)
        add_text(s, x + 0.2, 2.12, 0.7, 0.5, num, size=30, color=color, bold=True)
        add_text(s, x + 0.85, 2.2, 2.65, 1.4, text, size=11.5, color=NAVY, spacing=1.2)
    add_text(s, M, 4.35, 11.3, 0.4, "Testul este pe orașe, nu pe rânduri.", size=15, color=NAVY, bold=True)
    add_text(s, M, 4.8, 11.3, 0.4, "Erorile sunt analizate pe orașe, nu ascunse într-o medie.", size=13, color=MUTED)
    add_text(s, M, 5.3, 11.3, 0.4, "K=9–12 este extensie demo; CSV-ul original este K=8.", size=12, color=ORANGE, bold=True)
    add_footer(s, 14)
    add_notes(s, "Anexă pentru Q&A. Dacă întrebarea merge spre ML: 24 de indicii observabile, două întrebări diferite, trei modele mici cu seed-uri diferite. Testul este pe orașe, nu pe rânduri. Erorile sunt analizate pe orașe. K=9–12 este extensie demo; CSV-ul original este K=8.")
    return s


def main():
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)
    blank = prs.slide_layouts[6]

    slide_title(prs, blank)
    slide_naive(prs, blank)
    slide_cannibalization(prs, blank)
    slide_question(prs, blank)
    slide_data_gap(prs, blank)
    slide_simulator(prs, blank)
    slide_separation(prs, blank)
    slide_two_questions(prs, blank)
    slide_greedy(prs, blank)
    slide_k(prs, blank)
    slide_why(prs, blank)
    slide_results(prs, blank)
    slide_close(prs, blank)
    slide_appendix(prs, blank)

    prs.save(OUT)
    print(f"wrote {OUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
