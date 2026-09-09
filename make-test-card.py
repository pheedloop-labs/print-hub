"""Generate a caliper-measurable test card for the print hub spike.

Page is exactly 140.0 x 88.0 mm - the ZC10L large-format card.
Print it with noscale. Then measure the targets with digital calipers.
Any renderer that scales the page shows up as a wrong reading.
"""

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

W, H = 140.0, 88.0
OUT = "test-card-140x88.pdf"

c = canvas.Canvas(OUT, pagesize=(W * mm, H * mm))
c.setTitle("PheedLoop Print Hub test card 140x88mm")


def line(x1, y1, x2, y2, width=0.25):
    c.setLineWidth(width)
    c.line(x1 * mm, y1 * mm, x2 * mm, y2 * mm)


def text(x, y, s, size=6, font="Helvetica"):
    c.setFont(font, size)
    c.drawString(x * mm, y * mm, s)


def ctext(x, y, s, size=6, font="Helvetica"):
    c.setFont(font, size)
    c.drawCentredString(x * mm, y * mm, s)


# --- corner registration crosses, centres exactly 5 mm in from each edge ---
c.setStrokeColorRGB(0, 0, 0)
for cx, cy in ((5, 5), (W - 5, 5), (5, H - 5), (W - 5, H - 5)):
    line(cx - 2, cy, cx + 2, cy, 0.25)
    line(cx, cy - 2, cx, cy + 2, 0.25)

# --- top ruler: 0 to 130 mm, origin at x = 5 mm ---
RULER_Y = H - 10.0
RULER_X0 = 5.0
RULER_LEN = 120
line(RULER_X0, RULER_Y, RULER_X0 + RULER_LEN, RULER_Y, 0.25)
for i in range(0, RULER_LEN + 1):
    if i % 10 == 0:
        h = 3.0
    elif i % 5 == 0:
        h = 2.0
    else:
        h = 1.0
    line(RULER_X0 + i, RULER_Y, RULER_X0 + i, RULER_Y + h, 0.15)
for i in range(0, RULER_LEN + 1, 20):
    ctext(RULER_X0 + i, RULER_Y + 4.6, str(i), 4.5)
text(RULER_X0, RULER_Y - 4.0,
     "ruler: 1 mm ticks, origin = corner cross, 5.0 mm from left edge", 4.5)

# --- 100.00 mm horizontal target ---
TY = 50.0
TX0, TX1 = 20.0, 120.0
line(TX0, TY, TX1, TY, 0.35)
line(TX0, TY - 3, TX0, TY + 3, 0.35)
line(TX1, TY - 3, TX1, TY + 3, 0.35)
ctext((TX0 + TX1) / 2, TY + 1.5, "100.00 mm  (tick centre to tick centre)", 5.5)

# --- 50.00 mm vertical target ---
VX = 130.0
VY0, VY1 = 15.0, 65.0
line(VX, VY0, VX, VY1, 0.35)
line(VX - 3, VY0, VX + 3, VY0, 0.35)
line(VX - 3, VY1, VX + 3, VY1, 0.35)
c.saveState()
c.translate(VX * mm, ((VY0 + VY1) / 2) * mm)
c.rotate(90)
c.setFont("Helvetica", 5.5)
c.drawCentredString(0, 1.5 * mm, "50.00 mm")
c.restoreState()

# --- line width ladder: does the renderer keep hairlines? ---
LX, LY = 20.0, 40.0
text(LX, LY + 3.0, "line width", 4.5)
for i, w in enumerate((0.1, 0.25, 0.5, 1.0, 2.0)):
    y = LY - i * 2.2
    line(LX, y, LX + 20, y, w)
    text(LX + 21, y - 0.6, f"{w} pt", 4)

# --- text size ladder: badge text is small, so prove it renders ---
TX, TY2 = 55.0, 40.0
text(TX, TY2 + 3.0, "text size", 4.5)
for i, s in enumerate((4, 5, 6, 8, 10)):
    text(TX, TY2 - i * 3.6, f"{s}pt Helvetica 0O1lI8B", s)

# --- colour patches: for the ZC10L colour check ---
# Keep these 3-tuples. setFillColorRGB reads a 4th value as alpha, and an
# alpha of 0 makes every later object invisible.
PX, PY, PS = 20.0, 12.0, 7.0
patches = [
    ("C", (0, 1, 1)), ("M", (1, 0, 1)), ("Y", (1, 1, 0)),
    ("K", (0, 0, 0)), ("R", (1, 0, 0)), ("G", (0, 1, 0)),
    ("B", (0, 0, 1)),
]
for i, (label, rgb) in enumerate(patches):
    x = PX + i * (PS + 1.5)
    c.setFillColorRGB(*rgb)
    c.rect(x * mm, PY * mm, PS * mm, PS * mm, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    ctext(x + PS / 2, PY - 3.0, label, 4.5)

# grey ramp
for i, g in enumerate((0.0, 0.25, 0.5, 0.75)):
    x = PX + 7 * (PS + 1.5) + i * (PS + 1.5)
    c.setFillColorRGB(g, g, g)
    c.rect(x * mm, PY * mm, PS * mm, PS * mm, stroke=0, fill=1)
c.setFillColorRGB(0, 0, 0)
ctext(PX + 7 * (PS + 1.5) + 1.5 * (PS + 1.5), PY - 3.0, "grey ramp", 4.5)

# --- identity block ---
c.setFillColorRGB(0, 0, 0)
c.setStrokeColorRGB(0, 0, 0)
text(20.0, H - 18.0, "PheedLoop Print Hub - spike test card", 7.5, "Helvetica-Bold")
text(20.0, H - 22.0,
     "Page 140.0 x 88.0 mm. Print with noscale. Measure both targets.", 5)
text(20.0, H - 25.5,
     "renderer: ____________   queue: ____________   date: __________", 5)

c.showPage()
c.save()
print(f"wrote {OUT}")