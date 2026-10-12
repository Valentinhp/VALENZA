"""Shared letter-size page furniture for Valenza documents."""
from pathlib import Path

PAGE_WIDTH, PAGE_HEIGHT = 612, 792
LEFT, RIGHT, BOTTOM = 42, 570, 730
INK = (0.161, 0.153, 0.141)
MUTED = (0.42, 0.40, 0.37)
TERRACOTTA = (0.78, 0.42, 0.27)
CREAM = (0.97, 0.95, 0.92)
RULE = (0.88, 0.84, 0.79)


def page_header(page, title, period, issued):
    import pymupdf
    logo = Path(__file__).parent / 'assets/logo_horizontal.png'
    page.insert_image(pymupdf.Rect(LEFT, 25, LEFT+156, 64), filename=str(logo))
    page.insert_text((RIGHT-145, 34), title, fontsize=8, fontname='hebo', color=MUTED)
    page.insert_text((RIGHT-145, 47), period, fontsize=8, color=MUTED)
    page.insert_text((RIGHT-145, 60), 'Emitido: '+issued, fontsize=8, color=MUTED)
    page.draw_line((LEFT, 73), (RIGHT, 73), color=TERRACOTTA, width=1)


def page_footer(page, number, total):
    page.draw_line((LEFT, 752), (RIGHT, 752), color=RULE, width=.5)
    page.insert_text((LEFT, 770), 'Valenza | Finanzas compartidas', fontsize=8, color=MUTED)
    value = f'{number} / {total}'
    import pymupdf
    page.insert_text((RIGHT-pymupdf.get_text_length(value, fontsize=8), 770), value, fontsize=8, color=MUTED)
