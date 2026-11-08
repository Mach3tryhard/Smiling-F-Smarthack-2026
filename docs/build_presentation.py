"""Build the concise 5-minute PPC EV Siting Lab presentation.

Eight slides: problem, Huff simulator, MLP models, greedy selection, results,
product, and limits. No appendix, no narrative filler.

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
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.08):
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


def add_top(slide, number, label, title, *, size=31, width=12.0):
    add_text(slide, M, 0.35, 0.5, 0.28, f"{number:02d}", size=9.5, color=ORANGE, bold=True)
    add_text(slide, M + 0.45, 0.35, 7.2, 0.28, label.upper(), size=9, color=MUTED, bold=True)
    add_text(slide, M, 0.76, width, 1.2, title, size=size, color=NAVY, bold=True, spacing=0.98)


def add_footer(slide, number):
    add_rect(slide, M, 7.04, SW - 2 * M, 0.01, LINE)
    add_text(slide, M, 7.14, 9.0, 0.2,
             "PPC EV Siting Lab  ·  24h to Power PPC  ·  Smarthack XI 2026",
             size=8.2, color=MUTED)
    add_text(slide, SW - 1.0, 7.14, 0.3, 0.2, f"{number:02d}", size=8.2, color=MUTED,
             bold=True, align=PP_ALIGN.RIGHT)


def add_image(slide, path, x, y, w, h, border=True):
    image = Image.open(path)
    iw, ih = image.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    dx, dy = x + (w - dw) / 2, y + (h - dh) / 2
    if border:
        add_rect(slide, dx - 0.04, dy - 0.04, dw + 0.08, dh + 0.08, WHITE, LINE, radius=True)
    slide.shapes.add_picture(str(path), Inches(dx), Inches(dy), Inches(dw), Inches(dh))


def add_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def box_text(slide, x, y, w, h, text, *, fill=WHITE, line=LINE, size=11, color=NAVY,
             bold=False, radius=True):
    add_rect(slide, x, y, w, h, fill, line, radius=radius)
    add_text(slide, x + 0.18, y + 0.14, w - 0.36, h - 0.24, text, size=size, color=color,
             bold=bold, spacing=1.15)


def slide_title(prs, blank):
    s = prs.slides.add_slide(blank)
    add_rect(s, 0, 0, SW, SH, WHITE)
    add_rect(s, M, 0.55, 0.09, 0.31, ORANGE)
    add_text(s, M + 0.18, 0.51, 7.0, 0.3,
             "24H TO POWER PPC  ·  SMARTHACK XI 2026",
             size=10, color=BLUE, bold=True)
    add_text(s, M, 1.13, 6.2, 1.0, "PPC EV Siting Lab", size=34, color=NAVY, bold=True)
    add_text(s, M, 2.05, 6.1, 0.95,
             "Amplasarea stațiilor EV\nsub un buget K",
             size=27, color=NAVY, bold=True, spacing=1.05)
    add_text(s, M, 3.35, 6.0, 0.6,
             "Simulator Huff  ·  două MLP-uri  ·  optimizator greedy",
             size=15, color=BLUE, bold=True)
    add_text(s, M, 4.15, 5.8, 1.1,
             "Recomandări cu rang, încredere și explicație,\nverificabile până la rândul CSV.",
             size=13, color=MUTED, spacing=1.2)
    add_image(s, ASSETS / "map-canvas.png", 7.0, 0.62, 5.7, 5.7)
    add_rect(s, 7.4, 6.45, 2.35, 0.38, NAVY, NAVY, radius=True)
    add_text(s, 7.5, 6.47, 2.15, 0.34, "85,5% la K=8", size=10.5, color=WHITE, bold=True,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, 9.95, 6.5, 2.6, 0.28, "40 de orașe de test", size=8.5, color=MUTED)
    add_notes(s, "[0:00–0:20] Proiectul rezolvă o problemă de amplasare: K stații de încărcare într-un oraș. Decizia este susținută de un simulator Huff, două MLP-uri antrenate local și un optimizator greedy. Prezentarea explică alegerile și rezultatele; demo-ul arată explicația pentru fiecare sit.")
    return s


def slide_problem(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 2, "Problema", "Obiectivul este utilizarea totală a rețelei.", size=31)
    add_text(s, M, 1.95, 5.9, 0.7,
             "Buget K stații. Se maximizează diferența dintre rețeaua cu și fără ele.",
             size=15, color=MUTED, spacing=1.2)
    add_rect(s, M, 2.95, 5.95, 1.3, NAVY, NAVY, radius=True)
    add_text(s, M + 0.25, 3.05, 5.45, 0.3, "FUNCȚIA DE DECIZIE", size=8.5, color=RGBColor(0x9F, 0xC5, 0xE8), bold=True)
    add_text(s, M + 0.25, 3.35, 5.45, 0.6,
             "max  U(S ∪ A) − U(S),   |A| = K",
             size=20, color=WHITE, bold=True)
    add_text(s, M, 4.55, 5.9, 0.45,
             "U = suma utilizării estimate a tuturor stațiilor.",
             size=12, color=MUTED)
    add_text(s, M, 5.35, 5.9, 0.45,
             "Top-K după cerere grupează stațiile în aceleași zone.",
             size=13, color=ORANGE, bold=True)
    # diagram
    box_text(s, 7.1, 2.1, 2.5, 1.35, "Stație\nexistentă", fill=SOFT_BLUE, line=BLUE, size=16, bold=True)
    box_text(s, 10.2, 2.1, 2.5, 1.35, "Stație\nnouă", fill=SOFT_ORANGE, line=ORANGE, size=16, bold=True)
    arrow = s.shapes.add_shape(MSO_SHAPE.LEFT_RIGHT_ARROW, Inches(9.05), Inches(2.62), Inches(0.8), Inches(0.32))
    arrow.fill.solid(); arrow.fill.fore_color.rgb = ORANGE; arrow.line.fill.background()
    add_text(s, 8.65, 3.65, 3.6, 0.35, "o parte din cerere se mută", size=10, color=ORANGE, bold=True,
             align=PP_ALIGN.CENTER)
    add_text(s, 7.1, 4.35, 5.6, 0.5,
             "Canibalizarea intră în beneficiul total.",
             size=12, color=NAVY, bold=True)
    # output chips
    for i, (label, fill, line) in enumerate([
        ("ranking", MIST, LINE),
        ("CSV K=8", MIST, LINE),
        ("review uman", MIST, LINE),
    ]):
        add_rect(s, 7.1 + i * 1.85, 5.45, 1.68, 0.36, fill, line, radius=True)
        add_text(s, 7.1 + i * 1.85, 5.47, 1.68, 0.32, label, size=8.5, color=NAVY, bold=True,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_footer(s, 2)
    add_notes(s, "[0:20–0:55] Obiectivul este utilizarea totală a rețelei, nu utilizarea izolată a fiecărei stații. Formula scade utilizarea de bază din utilizarea după adăugarea celor K stații. O selecție top-K după cerere tinde să grupeze stațiile, iar o parte din cererea lor se mută între ele. De aceea avem nevoie de un model pentru creșterea incrementală și de un optimizator care penalizează vecinătatea.")
    return s


def slide_huff(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 3, "Date și simulator", "Datele de referință: cerere latentă și competiție Huff.", size=28)
    add_rect(s, M, 1.9, 6.2, 2.45, NAVY, NAVY, radius=True)
    add_text(s, M + 0.22, 2.03, 5.8, 0.25, "MODELUL DE UTILIZARE", size=8.5, color=RGBColor(0x9F, 0xC5, 0xE8), bold=True)
    add_text(s, M + 0.22, 2.35, 5.75, 1.75,
             "competition_i = Σ_{j≠i} cap_j · exp(−d_ij / λ)\n"
             "share_i = cap_i / (cap_i + competition_i)\n"
             "usage_i = demand_i · share_i",
             size=12.5, color=WHITE, spacing=1.45)
    add_text(s, 7.0, 1.95, 5.5, 0.4, "400 de orașe sintetice", size=22, color=NAVY, bold=True)
    add_text(s, 7.0, 2.45, 5.5, 0.4, "501.812 noduri · 36.809 stații existente", size=12, color=BLUE, bold=True)
    add_text(s, 7.0, 3.15, 5.6, 1.4,
             "Huff distribuie cererea între stații după capacitate și distanță. Simulatorul poate calcula astfel U(S ∪ {i}) − U(S) pentru orice candidat.",
             size=11.5, color=NAVY, spacing=1.25)
    add_text(s, 7.0, 4.85, 5.6, 0.7,
             "Datele reale nu conțin acest contrafactual și sunt afectate de selecția operatorilor.",
             size=10.5, color=ORANGE, bold=True)
    add_text(s, M, 5.0, 6.0, 1.2,
             "Separare strictă:\nmodelul nu vede cererea latentă, utilizarea observată sau flagul de stație.",
             size=11, color=MUTED, spacing=1.2)
    add_text(s, M, 6.3, 6.0, 0.3, "24 de features observabile per nod", size=9, color=NAVY, bold=True)
    add_footer(s, 3)
    add_notes(s, "[0:55–1:35] Utilizarea este generată cu un model Huff: fiecare stație are o capacitate, iar competiția scade exponențial cu distanța. Împărțim cererea latentă între stații proporțional cu capacitatea și competiția. Astfel putem calcula exact ce se întâmplă dacă adăugăm o stație oriunde. Datele reale nu au acest contrafactual, iar stațiile existente sunt deja alese de operatori. Modelul vede doar 24 de features observabile; cererea latentă și utilizarea observată rămân în simulator.")
    return s


def slide_mlp(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 4, "Model", "Două MLP-uri, două ținte separate.", size=30)
    # architecture
    add_text(s, M, 1.9, 5.2, 0.3, "ARHITECTURĂ", size=8.5, color=BLUE, bold=True)
    for i, (label, x) in enumerate([("24", 0.9), ("256", 1.9), ("128", 2.9), ("64", 3.9), ("1", 4.9)]):
        add_rect(s, x, 2.25, 0.7, 0.5, MIST if i < 4 else SOFT_ORANGE, LINE if i < 4 else ORANGE, radius=True)
        add_text(s, x, 2.3, 0.7, 0.35, label, size=9, color=NAVY, bold=True,
                 align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    add_text(s, M, 2.95, 5.4, 0.35, "3 seed-uri independente · predicția = media lor", size=9, color=MUTED)
    # target cards
    box_text(s, M, 3.55, 2.65, 1.45,
             "UTILIZARE\n27.324 stații\nlog(observed_usage)",
             fill=SOFT_BLUE, line=BLUE, size=10, bold=False)
    box_text(s, M + 2.9, 3.55, 2.65, 1.45,
             "CREȘTERE\n350.187 candidați\nlog(U(S∪{i})−U(S))",
             fill=SOFT_ORANGE, line=ORANGE, size=10, bold=False)
    add_text(s, M, 5.35, 5.9, 1.3,
             "MLP pentru că datele sunt tabelare, cu interacțiuni neliniare între competiție, acces și cerere. Inferența rulează local, pe CPU.",
             size=10.5, color=NAVY, spacing=1.2)
    add_text(s, M, 6.55, 5.9, 0.3,
             "HGB a fost antrenat ca artefact de robustețe; validarea a ales MLP-ul (w=1.0).",
             size=7.5, color=MUTED)
    # split + test
    add_rect(s, 7.0, 2.1, 5.5, 1.5, MIST, LINE, radius=True)
    add_text(s, 7.18, 2.22, 5.0, 0.25, "SPLIT PE ORAȘE", size=8.5, color=MUTED, bold=True)
    add_text(s, 7.18, 2.5, 5.0, 0.9,
             "300 train  ·  40 validation\n40 test  ·  20 OOD",
             size=16, color=NAVY, bold=True, spacing=1.25)
    add_rect(s, 7.0, 3.85, 5.5, 1.5, SOFT_TEAL, TEAL, radius=True)
    add_text(s, 7.18, 3.97, 5.0, 0.25, "TEST", size=8.5, color=RGBColor(0x06, 0x6B, 0x46), bold=True)
    add_text(s, 7.18, 4.25, 5.0, 0.95,
             "R² utilizare 0,871\nR² creștere 0,735",
             size=15, color=RGBColor(0x06, 0x6B, 0x46), bold=True, spacing=1.25)
    add_text(s, 7.0, 5.55, 5.4, 0.6,
             "Fără latent demand, observed usage sau is_station în input.",
             size=9.5, color=MUTED)
    add_footer(s, 4)
    add_notes(s, "[1:35–2:15] Antrenăm două MLP-uri cu aceeași arhitectură: 24 de inputuri, straturi 256, 128 și 64, o ieșire. Primul prezice utilizarea stațiilor existente. Al doilea prezice creșterea incrementală pentru candidați; aceasta este ținta relevantă pentru decizie. Folosim trei seed-uri, iar media lor este predicția; dezacordul dintre ele este semnalul de incertitudine. MLP-ul se potrivește datelor tabelare, are interacțiuni neliniare și rulează local. Splitul este pe orașe: 300 train, 40 validation, 40 test, 20 OOD.")
    return s


def slide_greedy(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 5, "Selecție", "Greedy cu penalizare de canibalizare.", size=30)
    add_rect(s, M, 1.9, 6.2, 1.35, NAVY, NAVY, radius=True)
    add_text(s, M + 0.22, 2.03, 5.8, 0.25, "SCORUL FIECĂRUI CANDIDAT", size=8.5, color=RGBColor(0x9F, 0xC5, 0xE8), bold=True)
    add_text(s, M + 0.22, 2.35, 5.8, 0.65,
             "score_i = creștere_i / (1 + α · Σ_selected exp(−d_ij / λ))",
             size=13.5, color=WHITE, bold=True)
    add_text(s, M, 3.45, 6.0, 1.0,
             "Se alege un sit, se recalculează candidații, se penalizează vecinătatea, se repetă până la K.",
             size=11.5, color=NAVY, spacing=1.2)
    add_text(s, M, 4.65, 6.0, 0.35, "α = 1,0, ales pe validare.", size=12, color=ORANGE, bold=True)
    add_text(s, M, 5.1, 6.0, 0.8,
             "Fără penalizare: 66,5% captură.\nCu α=1,0: 85,2% pe validare.",
             size=11.5, color=MUTED, spacing=1.2)
    add_text(s, M, 6.15, 6.0, 0.35,
             "K=8 benchmark; interfața permite K=1–12.", size=9.5, color=MUTED)
    # ablation bars
    add_text(s, 7.0, 1.95, 5.6, 0.3, "ABLAȚIE PE VALIDARE", size=8.5, color=MUTED, bold=True)
    for i, (label, value, color) in enumerate([
        ("fără penalizare", 66.5, MUTED),
        ("α=0,5", 82.9, BLUE),
        ("α=1,0", 85.2, ORANGE),
        ("α=2,0", 84.9, TEAL),
    ]):
        y = 2.45 + i * 0.78
        add_text(s, 7.0, y, 1.65, 0.25, label, size=10, color=NAVY)
        add_rect(s, 8.75, y + 0.02, 2.9, 0.17, RGBColor(0xEC, 0xF2, 0xF9), None, radius=True)
        add_rect(s, 8.75, y + 0.02, max(0.08, 2.9 * value / 100), 0.17, color, None, radius=True)
        add_text(s, 11.8, y - 0.02, 0.7, 0.26, f"{value:.1f}%", size=10, color=color, bold=True,
                 align=PP_ALIGN.RIGHT)
    add_text(s, 7.0, 5.85, 5.4, 0.55,
             "Greedy este transparent și respectă bugetul, dar nu este optim global.",
             size=9.5, color=MUTED)
    add_footer(s, 5)
    add_notes(s, "[2:15–2:55] Pentru selecție folosim un greedy cu penalizare de canibalizare. Fiecare candidat are un scor egal cu creșterea estimată împărțită la un factor care crește când situl este aproape de stațiile deja alese. Alpha a fost ales pe validare; fără penalizare captura este 66,5%, cu alpha 1,0 este 85,2%. Greedy este ușor de explicat și respectă bugetul, dar nu este optim global. K=8 este benchmark-ul; interfața permite 1–12, iar peste 8 este extensie demo.")
    return s


def slide_results(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 6, "Rezultate", "Captură de 85,5% pe 40 de orașe de test.", size=30)
    add_text(s, M, 1.95, 5.5, 0.3, "K=8  ·  ORAȘE NEVĂZUTE", size=8.5, color=MUTED, bold=True)
    add_text(s, M, 2.3, 3.5, 0.9, "85,5%", size=52, color=ORANGE, bold=True)
    add_text(s, M, 3.2, 5.4, 0.4, "din beneficiul incremental al referinței perfecte", size=12, color=NAVY, bold=True)
    add_text(s, M, 3.75, 5.4, 0.4, "Regret 14,5%  ·  overlap 41,3%", size=10, color=MUTED)
    add_text(s, M, 4.2, 5.4, 0.4, "OOD 88,4%  ·  14 review  ·  320 acțiuni", size=10, color=MUTED)
    # metric table
    rows = [
        ("R² utilizare", "0,871", "Spearman", "0,931"),
        ("R² creștere", "0,735", "Spearman", "0,801"),
        ("MAE utilizare", "2,12", "MAE creștere", "1,35"),
    ]
    for i, (l1, v1, l2, v2) in enumerate(rows):
        y = 5.0 + i * 0.45
        add_text(s, M, y, 1.3, 0.3, l1, size=8.5, color=MUTED)
        add_text(s, M + 1.35, y - 0.02, 0.65, 0.3, v1, size=11, color=NAVY, bold=True)
        add_text(s, M + 2.15, y, 1.2, 0.3, l2, size=8.5, color=MUTED)
        add_text(s, M + 3.4, y - 0.02, 0.6, 0.3, v2, size=11, color=NAVY, bold=True)
    # baseline bars
    add_text(s, 6.8, 1.95, 5.7, 0.3, "CAPTURĂ DIN REFERINȚĂ", size=8.5, color=MUTED, bold=True)
    bars = [
        ("Model + greedy", 85.5, "85,5%", ORANGE),
        ("Populație", 11.3, "11,3%", BLUE),
        ("Aleator", 8.7, "8,7%", TEAL),
        ("Index manual", 7.5, "7,5%", NAVY),
        ("Activitate", 5.2, "5,2%", MUTED),
    ]
    for i, (label, value, text, color) in enumerate(bars):
        y = 2.45 + i * 0.72
        add_text(s, 6.8, y, 1.55, 0.25, label, size=9.5, color=NAVY, bold=(i == 0))
        add_rect(s, 8.5, y + 0.02, 3.2, 0.17, RGBColor(0xEC, 0xF2, 0xF9), None, radius=True)
        add_rect(s, 8.5, y + 0.02, max(0.08, 3.2 * value / 100), 0.17, color, None, radius=True)
        add_text(s, 11.9, y - 0.02, 0.75, 0.26, text, size=9.5, color=color, bold=True,
                 align=PP_ALIGN.RIGHT)
    add_text(s, 6.8, 6.15, 5.7, 0.5,
             "Cel mai slab oraș: 60,8%. Cel mai bun: 98,8%. Media ascunde variația.",
             size=9.5, color=MUTED)
    add_footer(s, 6)
    add_notes(s, "[2:55–3:35] Pe 40 de orașe de test, modelul capturează 85,5% din beneficiul incremental al referinței perfecte. Regretul este 14,5%, iar suprapunerea exactă cu referința este 41,3%; situri diferite pot avea valori apropiate. Baseline-ul cu populația ia 11,3%, aleatorul 8,7%. Pe orașele OOD captura este 88,4%. Cel mai slab oraș are 60,8%, cel mai bun 98,8%; media ascunde variația, de aceea analizăm erorile pe orașe.")
    return s


def slide_product(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 7, "Produs", "Fiecare recomandare are o explicație și un rând CSV.", size=27)
    add_image(s, ASSETS / "why.png", 6.75, 1.8, 5.1, 4.95)
    add_text(s, M, 1.95, 5.6, 0.35, "Harta arată unde. Panoul arată de ce.", size=16, color=NAVY, bold=True)
    add_text(s, M, 2.45, 5.55, 2.5,
             "•  rang, creștere estimată, utilizare și încredere\n"
             "•  factori locali cu valoare și mediană\n"
             "•  contextul sitului și motivul de review\n"
             "•  rândul CSV care a produs recomandarea",
             size=10.5, color=NAVY, spacing=1.35)
    add_text(s, M, 4.95, 5.4, 0.8,
             "K se schimbă din interfață: 1–12. Peste K=8, recomandarea este extensie demo și nu are rând CSV.",
             size=9.5, color=ORANGE, bold=True, spacing=1.2)
    add_text(s, M, 5.9, 5.4, 0.7,
             "Ieșiri: priority_sites.csv, review_queue.csv, dashboard.json.",
             size=8.5, color=MUTED)
    add_footer(s, 7)
    add_notes(s, "[3:35–4:15] Interfața arată harta cu noduri, stații existente și situri recomandate. La click, panoul afișează rangul, creșterea estimată, utilizarea, încrederea, factorii locali cu valoare și mediană, contextul și motivul de review. Fiecare explicație se termină cu rândul CSV exact. K se schimbă din interfață; peste 8 este extensie demo și nu are rând CSV. Ieșirile sunt CSV-ul de acțiuni, coada de review și bundle-ul dashboardului.")
    return s


def slide_limits(prs, blank):
    s = prs.slides.add_slide(blank)
    add_top(s, 8, "Limite", "Ce am ales și ce rămâne de validat.", size=30)
    columns = [
        ("ALEGERI", [
            "Simulator Huff pentru contrafactuale.",
            "Două MLP-uri, cu ținte separate.",
            "Greedy cu α=1,0 și K configurabil.",
            "Explicație până la rândul CSV.",
        ], SOFT_TEAL, TEAL),
        ("LIMITE", [
            "Date sintetice, nu București real.",
            "Greedy nu este optim global.",
            "Fără imputer pentru date lipsă.",
            "Fără costuri, permisare sau rețea reală.",
        ], SOFT_ORANGE, ORANGE),
        ("URMEAZĂ", [
            "Calibrare pe date reale.",
            "Costuri, capacitate de rețea, permisare.",
            "Pilot cu review uman.",
            "Validarea pragurilor de încredere.",
        ], SOFT_BLUE, BLUE),
    ]
    for i, (head, items, fill, line) in enumerate(columns):
        x = M + i * 4.05
        add_rect(s, x, 2.0, 3.72, 3.0, fill, line, radius=True)
        add_text(s, x + 0.2, 2.15, 3.3, 0.3, head, size=8.5, color=line, bold=True)
        add_text(s, x + 0.2, 2.5, 3.3, 2.2, "\n".join("•  " + item for item in items),
                 size=9.5, color=NAVY, spacing=1.45)
    add_text(s, M, 5.45, 11.8, 0.5,
             "Rezultatele sunt reproductibile din README; modelul rulează local, fără API extern.",
             size=11, color=MUTED)
    add_text(s, M, 6.0, 12.0, 0.45,
             "Repository: github.com/Mach3tryhard/Smiling-F-Smarthack-2026  ·  PPT: docs/PPC_EV_Siting_Lab_5min.pptx",
             size=9.5, color=NAVY, bold=True)
    add_text(s, SW - 2.8, 6.55, 2.0, 0.35, "Întrebări?", size=14, color=ORANGE, bold=True,
             align=PP_ALIGN.RIGHT)
    add_footer(s, 8)
    add_notes(s, "[4:15–5:00] Alegerile principale sunt simulatorul Huff, cele două MLP-uri, greedy cu alpha 1,0 și explicația până la rândul CSV. Limitele sunt datele sintetice, faptul că greedy nu este optim global, lipsa unui imputer și lipsa costurilor, permisării și rețelei reale. Următorii pași sunt calibrarea pe date reale, costurile, pilotul cu review uman și validarea pragurilor. Rezultatele sunt reproductibile, modelul rulează local și repository-ul conține PPT-ul.")
    return s


def main():
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)
    blank = prs.slide_layouts[6]

    slide_title(prs, blank)
    slide_problem(prs, blank)
    slide_huff(prs, blank)
    slide_mlp(prs, blank)
    slide_greedy(prs, blank)
    slide_results(prs, blank)
    slide_product(prs, blank)
    slide_limits(prs, blank)

    prs.save(OUT)
    print(f"wrote {OUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
