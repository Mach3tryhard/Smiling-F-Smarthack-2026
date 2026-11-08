"""Build the concise PPC EV Siting Lab presentation.

Eight slides, large type, one subject per slide, no captions and no decorative
labels. Technical choices are explained directly: Huff, MLP, greedy.

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
MIST = RGBColor(0xF4, 0xF7, 0xFB)
MUTED = RGBColor(0x5E, 0x76, 0x8E)
LINE = RGBColor(0xD5, 0xE3, 0xF2)
WHITE = RGBColor(0xFF, 0xFF, 0xFF)
SOFT_ORANGE = RGBColor(0xFF, 0xF1, 0xE2)
SOFT_BLUE = RGBColor(0xE8, 0xF1, 0xFF)
SOFT_TEAL = RGBColor(0xE5, 0xF7, 0xF5)

FONT = "Arial"
SW, SH = 13.333, 7.5
M = 0.8


def add_text(slide, x, y, w, h, text, *, size=20, color=NAVY, bold=False,
             align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP, spacing=1.1):
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
            shape.adjustments[0] = 0.06
        except Exception:
            pass
    return shape


def add_title(slide, text, *, size=36):
    add_text(slide, M, 0.62, 11.8, 1.0, text, size=size, color=NAVY, bold=True, spacing=0.98)


def add_page(slide, number):
    add_text(slide, SW - 1.05, 7.12, 0.35, 0.25, f"{number:02d}", size=9, color=MUTED,
             bold=True, align=PP_ALIGN.RIGHT)


def add_image(slide, path, x, y, w, h):
    image = Image.open(path)
    iw, ih = image.size
    scale = min(w / iw, h / ih)
    dw, dh = iw * scale, ih * scale
    dx, dy = x + (w - dw) / 2, y + (h - dh) / 2
    add_rect(slide, dx - 0.035, dy - 0.035, dw + 0.07, dh + 0.07, WHITE, LINE, radius=True)
    slide.shapes.add_picture(str(path), Inches(dx), Inches(dy), Inches(dw), Inches(dh))


def add_formula(slide, x, y, w, h, lines, *, size=15):
    add_rect(slide, x, y, w, h, NAVY, radius=True)
    add_text(slide, x + 0.25, y + 0.2, w - 0.5, h - 0.3, lines, size=size, color=WHITE,
             spacing=1.5)


def add_notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def slide_title(prs, blank):
    s = prs.slides.add_slide(blank)
    add_rect(s, 0, 0, SW, SH, WHITE)
    add_text(s, M, 0.75, 6.2, 0.35, "PPC EV Siting Lab", size=20, color=BLUE, bold=True)
    add_text(s, M, 1.45, 6.5, 2.4,
             "Amplasarea stațiilor\nde încărcare EV",
             size=44, color=NAVY, bold=True, spacing=0.98)
    add_text(s, M, 4.15, 6.2, 0.5, "Smarthack XI 2026", size=19, color=MUTED)
    add_text(s, M, 4.75, 6.2, 0.4, "24h to Power PPC", size=15, color=MUTED)
    add_image(s, ASSETS / "map-canvas.png", 7.0, 0.85, 5.5, 5.6)
    add_notes(s, "[0:00–0:15] Proiectul optimizează amplasarea stațiilor de încărcare EV sub un buget K. Prezentarea acoperă datele, modelele, optimizatorul, rezultatele și limitele.")


def slide_objective(prs, blank):
    s = prs.slides.add_slide(blank)
    add_title(s, "Maximizarea utilizării rețelei")
    add_text(s, M, 1.95, 11.4, 0.6,
             "K stații noi. Se maximizează diferența dintre rețeaua cu și fără ele.",
             size=22, color=MUTED, spacing=1.2)
    add_formula(s, M, 2.9, 11.75, 1.35,
                "max  U(S ∪ A) − U(S),   |A| = K", size=25)
    add_text(s, M, 4.6, 5.8, 0.5, "U = utilizarea totală a tuturor stațiilor.", size=16, color=MUTED)
    add_text(s, 7.0, 4.45, 5.5, 1.3,
             "Top-K după cerere grupează stațiile.\nCanibalizarea reduce beneficiul incremental.",
             size=18, color=ORANGE, bold=True, spacing=1.25)
    add_page(s, 2)
    add_notes(s, "[0:15–0:50] Obiectivul este utilizarea totală a rețelei, nu utilizarea fiecărei stații. Formula scade utilizarea de bază din utilizarea după cele K stații. O selecție top-K după cerere grupează stațiile, iar canibalizarea reduce beneficiul incremental. De aceea modelul prezice creșterea incrementală, iar optimizatorul penalizează vecinătatea.")


def slide_huff(prs, blank):
    s = prs.slides.add_slide(blank)
    add_title(s, "Simulatorul Huff")
    add_formula(
        s, M, 2.0, 7.35, 2.55,
        "competition_i = Σ_{j≠i} capacity_j · exp(−d_ij / λ)\n"
        "share_i = capacity_i / (capacity_i + competition_i)\n"
        "usage_i = demand_i · share_i",
        size=14,
    )
    add_text(s, 8.55, 2.0, 4.0, 0.4, "400 de orașe", size=24, color=NAVY, bold=True)
    add_text(s, 8.55, 2.5, 4.0, 0.4, "501.812 noduri", size=20, color=BLUE, bold=True)
    add_text(s, 8.55, 2.95, 4.0, 0.4, "36.809 stații existente", size=20, color=BLUE, bold=True)
    add_text(s, 8.55, 3.75, 4.0, 1.0,
             "Contrafactual:\nU(S ∪ {i}) − U(S)",
             size=18, color=NAVY, bold=True, spacing=1.25)
    add_text(s, M, 5.1, 11.5, 0.8,
             "Modelul nu vede cererea latentă, utilizarea observată sau flagul de stație.",
             size=17, color=NAVY, bold=True)
    add_text(s, M, 5.95, 11.5, 0.8,
             "Datele reale nu conțin contrafactualul și sunt afectate de selecția operatorilor.",
             size=16, color=MUTED)
    add_page(s, 3)
    add_notes(s, "[0:50–1:35] Utilizarea este generată cu un model Huff: fiecare stație are o capacitate, iar competiția scade exponențial cu distanța. Cererea latentă este împărțită între stații proporțional cu capacitatea și competiția. Astfel simulatorul poate calcula U(S ∪ {i}) − U(S) pentru orice candidat. Datele reale nu au acest contrafactual, iar stațiile existente sunt alese de operatori. Modelul vede doar 24 de features observabile.")


def slide_mlp(prs, blank):
    s = prs.slides.add_slide(blank)
    add_title(s, "Două MLP-uri")
    add_text(s, M, 1.95, 6.0, 0.35, "24 → 256 → 128 → 64 → 1", size=20, color=BLUE, bold=True)
    add_text(s, M, 2.4, 6.0, 0.35, "3 seed-uri; media predicțiilor", size=15, color=MUTED)
    add_text(s, M, 3.0, 5.9, 0.7,
             "Utilizare: 27.324 stații\nCreștere: 350.187 candidați",
             size=18, color=NAVY, bold=True, spacing=1.35)
    add_text(s, M, 4.2, 5.9, 0.8,
             "Date tabelare, interacțiuni neliniare,\ninferență locală pe CPU.",
             size=15, color=MUTED, spacing=1.2)
    add_text(s, M, 5.35, 5.9, 0.9,
             "Split pe orașe:\n300 train · 40 validation · 40 test · 20 OOD",
             size=14, color=NAVY, spacing=1.25)
    # target cards
    add_rect(s, 7.1, 2.0, 2.55, 1.5, SOFT_BLUE, BLUE, radius=True)
    add_text(s, 7.3, 2.15, 2.15, 0.3, "UTILIZARE", size=9, color=BLUE, bold=True)
    add_text(s, 7.3, 2.5, 2.15, 0.75, "stații\nexistente", size=17, color=NAVY, bold=True)
    add_rect(s, 9.9, 2.0, 2.55, 1.5, SOFT_ORANGE, ORANGE, radius=True)
    add_text(s, 10.1, 2.15, 2.15, 0.3, "CREȘTERE", size=9, color=RGBColor(0x93, 0x44, 0x00), bold=True)
    add_text(s, 10.1, 2.5, 2.15, 0.75, "candidați\nnoi", size=17, color=NAVY, bold=True)
    add_text(s, 7.1, 3.95, 5.35, 0.55,
             "A doua țintă este cea folosită la selecție.",
             size=15, color=ORANGE, bold=True)
    add_text(s, 7.1, 4.8, 5.35, 0.75,
             "Fără cererea latentă, utilizarea observată\nsau flagul de stație în datele de intrare.",
             size=13, color=MUTED, spacing=1.2)
    add_text(s, 7.1, 5.85, 5.35, 0.5,
             "R² utilizare 0,871  ·  R² creștere 0,735",
             size=13, color=NAVY, bold=True)
    add_page(s, 4)
    add_notes(s, "[1:35–2:20] Antrenăm două MLP-uri cu aceeași arhitectură: 24 de inputuri, straturi 256, 128, 64 și o ieșire. Primul model prezice utilizarea stațiilor existente. Al doilea prezice creșterea incrementală pentru candidați; aceasta este ținta folosită la selecție. Folosim trei seed-uri, iar media este predicția. MLP-ul se potrivește datelor tabelare, cu interacțiuni neliniare, și rulează local. Splitul este pe orașe: 300 train, 40 validation, 40 test, 20 OOD. Modelul nu primește cererea latentă, utilizarea observată sau flagul de stație.")


def slide_greedy(prs, blank):
    s = prs.slides.add_slide(blank)
    add_title(s, "Greedy cu penalizare")
    add_formula(s, M, 1.95, 11.75, 1.25,
                "score_i = creștere_i / (1 + α · Σ_{j∈selected} exp(−d_ij / λ))", size=15)
    add_text(s, M, 3.5, 5.8, 0.45, "α = 1,0, ales pe validare.", size=22, color=ORANGE, bold=True)
    add_text(s, M, 4.1, 5.8, 0.7,
             "Penalizarea evită gruparea stațiilor\nîn același cartier.",
             size=16, color=NAVY, spacing=1.2)
    add_text(s, M, 5.2, 5.8, 0.35, "K=8 benchmark; interfața 1–12.", size=13, color=MUTED)
    add_text(s, M, 5.75, 5.8, 0.35, "Greedy nu este optim global.", size=13, color=MUTED)
    # ablation bars
    add_text(s, 7.0, 3.35, 2.4, 0.4, "fără penalizare", size=15, color=MUTED)
    add_rect(s, 7.0, 3.8, 3.8, 0.35, RGBColor(0xEC, 0xF2, 0xF9), None, radius=True)
    add_rect(s, 7.0, 3.8, 3.8 * 0.665, 0.35, MUTED, None, radius=True)
    add_text(s, 11.0, 3.8, 1.4, 0.35, "66,5%", size=20, color=MUTED, bold=True)
    add_text(s, 7.0, 4.65, 2.4, 0.4, "α = 1,0", size=15, color=ORANGE, bold=True)
    add_rect(s, 7.0, 5.1, 3.8, 0.35, RGBColor(0xEC, 0xF2, 0xF9), None, radius=True)
    add_rect(s, 7.0, 5.1, 3.8 * 0.852, 0.35, ORANGE, None, radius=True)
    add_text(s, 11.0, 5.1, 1.4, 0.35, "85,2%", size=20, color=ORANGE, bold=True)
    add_page(s, 5)
    add_notes(s, "[2:20–3:00] Selecția folosește un greedy cu penalizare de canibalizare. Scorul unui candidat este creșterea estimată împărțită la un factor care crește când candidatul este aproape de stațiile deja alese. Alpha a fost ales pe validare: fără penalizare captura este 66,5%, cu alpha 1,0 este 85,2%. Greedy respectă bugetul și este ușor de explicat, dar nu este optim global. K=8 este benchmark-ul; interfața permite 1–12.")


def slide_results(prs, blank):
    s = prs.slides.add_slide(blank)
    add_title(s, "Rezultate la K=8", size=38)
    add_text(s, M, 1.95, 3.8, 0.35, "40 de orașe de test", size=16, color=MUTED)
    add_text(s, M, 2.3, 3.6, 1.2, "85,5%", size=64, color=ORANGE, bold=True)
    add_text(s, M, 3.55, 4.2, 0.7,
             "din beneficiul incremental\nal referinței perfecte",
             size=17, color=NAVY, bold=True, spacing=1.15)
    add_text(s, M, 4.55, 4.2, 0.5, "Regret 14,5%  ·  OOD 88,4%", size=15, color=MUTED)
    bars = [
        ("Model + greedy", 85.5, "85,5%", ORANGE),
        ("Populație", 11.3, "11,3%", BLUE),
        ("Aleator", 8.7, "8,7%", TEAL),
        ("Index manual", 7.5, "7,5%", NAVY),
    ]
    for i, (label, value, text, color) in enumerate(bars):
        y = 2.15 + i * 0.85
        add_text(s, 5.9, y, 1.8, 0.3, label, size=14, color=NAVY, bold=(i == 0))
        add_rect(s, 7.65, y + 0.02, 3.8, 0.2, RGBColor(0xEC, 0xF2, 0xF9), None, radius=True)
        add_rect(s, 7.65, y + 0.02, max(0.06, 3.8 * value / 100), 0.2, color, None, radius=True)
        add_text(s, 11.55, y - 0.03, 0.75, 0.3, text, size=14, color=color, bold=True,
                 align=PP_ALIGN.RIGHT)
    add_text(s, 5.9, 5.9, 6.4, 0.6,
             "Cel mai slab oraș 60,8%. Cel mai bun 98,8%.",
             size=13, color=MUTED)
    add_page(s, 6)
    add_notes(s, "[3:00–3:40] Pe 40 de orașe de test, modelul capturează 85,5% din beneficiul incremental al referinței perfecte. Regretul este 14,5%, iar pe orașele OOD captura este 88,4%. Baseline-ul cu populația ia 11,3%, aleatorul 8,7%, indexul manual 7,5%. Rezultatele variază între 60,8% și 98,8% pe orașe; media singură nu este suficientă.")


def slide_ui(prs, blank):
    s = prs.slides.add_slide(blank)
    add_title(s, "Explicația din interfață", size=36)
    add_text(s, M, 2.0, 5.2, 0.5, "Rang și încredere", size=24, color=NAVY, bold=True)
    add_text(s, M, 2.65, 5.2, 0.5, "Factori locali", size=24, color=NAVY, bold=True)
    add_text(s, M, 3.3, 5.2, 0.5, "Rând CSV", size=24, color=NAVY, bold=True)
    add_text(s, M, 4.35, 5.2, 0.8,
             "Fiecare recomandare poate fi verificată\npână la intrarea care a produs-o.",
             size=14, color=MUTED, spacing=1.2)
    add_text(s, M, 5.5, 5.2, 0.4, "K selectabil 1–12.", size=14, color=ORANGE, bold=True)
    add_image(s, ASSETS / "why.png", 6.65, 1.65, 5.35, 5.2)
    add_page(s, 7)
    add_notes(s, "[3:40–4:20] Interfața arată harta cu noduri, stații existente și situri recomandate. La click, panoul afișează rangul, încrederea, factorii locali cu valoare și mediană, contextul și rândul CSV. K se poate schimba între 1 și 12; peste 8 este extensie demo și nu are rând CSV.")


def slide_limits(prs, blank):
    s = prs.slides.add_slide(blank)
    add_title(s, "Limite", size=38)
    bullets = [
        "Date sintetice.",
        "Greedy nu este optim global.",
        "Fără costuri, permisare sau rețea reală.",
        "Fără imputer pentru date lipsă.",
        "K=9–12 este extensie demo.",
    ]
    for i, bullet in enumerate(bullets):
        y = 1.95 + i * 0.62
        add_text(s, M, y, 11.4, 0.45, "•  " + bullet, size=22, color=NAVY, bold=True)
    add_page(s, 8)
    add_notes(s, "[4:20–5:00] Limitele sunt datele sintetice, faptul că greedy nu este optim global, lipsa costurilor, permisării și rețelei reale, lipsa unui imputer pentru date lipsă și faptul că K=9–12 este extensie demo. Următorii pași sunt calibrarea pe date reale, adăugarea costurilor și un pilot cu review uman.")


def main():
    prs = Presentation()
    prs.slide_width = Inches(SW)
    prs.slide_height = Inches(SH)
    blank = prs.slide_layouts[6]

    slide_title(prs, blank)
    slide_objective(prs, blank)
    slide_huff(prs, blank)
    slide_mlp(prs, blank)
    slide_greedy(prs, blank)
    slide_results(prs, blank)
    slide_ui(prs, blank)
    slide_limits(prs, blank)

    prs.save(OUT)
    print(f"wrote {OUT} ({len(prs.slides)} slides)")


if __name__ == "__main__":
    main()
