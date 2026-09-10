"""Generate a caliper-measurable test card for the print hub spike.

    make-test-card.py                      -> 140.0 x 88.0, the ZC10L card
    make-test-card.py 83.99 58.93 70 40    -> W H [h-target v-target]

Print it with noscale, then measure the two targets with digital calipers.
Any renderer that scales the page shows up as a wrong reading.

Author the page at the *imageable* size the driver reports, not the form
size. pdfium_print.py blits 1:1 centred inside HORZRES x VERTRES, so a page
authored larger than the imageable area is clipped or rescaled, and both
failures are invisible by eye on a badge. Read the imageable size from
GetDeviceCaps HORZRES/VERTRES divided by LOGPIXELSX, because a driver with
unprintable margins reports a physical page bigger than it can image: the
Brother QL-800 is 1062 x 732 px physical against 992 x 696 imageable.
"""

import sys

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

args = sys.argv[1:]
W, H = (float(args[0]), float(args[1])) if len(args) >= 2 else (140.0, 88.0)
HT = float(args[2]) if len(args) >= 3 else 100.0
VT = float(args[3]) if len(args) >= 4 else 50.0
OUT = f"test-card-{W:g}x{H:g}.pdf"

M = 5.0                                   # margin to the registration crosses
c = canvas.Canvas(OUT, pagesize=(W * mm, H * mm))
c.setTitle(f"PheedLoop Print Hub test card {W:g}x{H:g}mm")


def line(x1, y1, x2, y2, width=0.25):
    c.setLineWidth(width)
    c.line(x1 * mm, y1 * mm, x2 * mm, y2 * mm)


def text(x, y, s, size=6, font="Helvetica"):
    c.setFont(font, size)
    c.drawString(x * mm, y * mm, s)


def ctext(x, y, s, size=6, font="Helvetica"):
    c.setFont(font, size)
    c.drawCentredString(x * mm, y * mm, s)


c.setStrokeColorRGB(0, 0, 0)
c.setFillColorRGB(0, 0, 0)

# --- corner registration crosses, centres exactly M mm in from each edge ---
for cx, cy in ((M, M), (W - M, M), (M, H - M), (W - M, H - M)):
    line(cx - 2, cy, cx + 2, cy, 0.25)
    line(cx, cy - 2, cx, cy + 2, 0.25)

# --- identity block ---
text(M, H - 4.0, "PheedLoop Print Hub - spike test card", 6.5, "Helvetica-Bold")
text(M, H - 7.4, f"Page {W:g} x {H:g} mm. noscale. Measure both targets.", 4.5)
text(M, H - 10.6, "renderer: ______  queue: ______  date: ______", 4.5)

# --- ruler, 1 mm ticks, origin at the top-left cross ---
RULER_Y = H - 18.0
RULER_LEN = int(W - 2 * M)
line(M, RULER_Y, M + RULER_LEN, RULER_Y, 0.25)
for i in range(RULER_LEN + 1):
    h = 3.0 if i % 10 == 0 else 2.0 if i % 5 == 0 else 1.0
    line(M + i, RULER_Y, M + i, RULER_Y + h, 0.15)
for i in range(0, RULER_LEN + 1, 20):
    ctext(M + i, RULER_Y + 4.2, str(i), 4.0)
text(M, RULER_Y - 3.4, f"ruler 1 mm ticks, origin = cross, {M:g} mm from left", 4.0)

# --- horizontal caliper target, centred ---
TY = H * 0.50
TX0 = (W - HT) / 2.0
line(TX0, TY, TX0 + HT, TY, 0.35)
line(TX0, TY - 2.5, TX0, TY + 2.5, 0.35)
line(TX0 + HT, TY - 2.5, TX0 + HT, TY + 2.5, 0.35)
ctext(W / 2.0, TY + 1.2, f"{HT:.2f} mm  (tick centre to tick centre)", 5.0)

# --- vertical caliper target, centred, clear of the corner crosses ---
VX = W - M - 2.5
VY0 = (H - VT) / 2.0
line(VX, VY0, VX, VY0 + VT, 0.35)
line(VX - 2.5, VY0, VX + 2.5, VY0, 0.35)
line(VX - 2.5, VY0 + VT, VX + 2.5, VY0 + VT, 0.35)
c.saveState()
c.translate(VX * mm, (VY0 + VT / 2.0) * mm)
c.rotate(90)
c.setFont("Helvetica", 5.0)
c.drawCentredString(0, 1.2 * mm, f"{VT:.2f} mm")
c.restoreState()

# --- line width and text size ladders, side by side under the target ---
LY = TY - 5.0
text(M, LY, "line width", 4.0)
for i, w in enumerate((0.1, 0.25, 0.5, 1.0, 2.0)):
    y = LY - 2.4 - i * 2.0
    line(M, y, M + 14, y, w)
    text(M + 15, y - 0.6, f"{w}pt", 3.5)

TX2 = W * 0.42
text(TX2, LY, "text size", 4.0)
for i, s in enumerate((4, 5, 6, 8)):
    text(TX2, LY - 3.0 - i * 3.0, f"{s}pt Helvetica 0O1lI8B", s)

# --- red channel test, for two-colour media such as Brother DK-2251 ---
# The QL-800 reports colordevice 0 and dmColor 1, monochrome, even with
# black/red stock loaded, so whether red survives is an empirical question.
RY = 13.5
c.setFillColorRGB(1, 0, 0)
c.rect(M * mm, RY * mm, 18 * mm, 4 * mm, stroke=0, fill=1)
text(M + 19, RY + 1.2, "RED CHANNEL: bar and this text are pure red 255,0,0", 4.0)
c.setFillColorRGB(0, 0, 0)

# --- colour patches, sized to whatever width is available ---
# Keep these 3-tuples. setFillColorRGB reads a 4th value as alpha, and an
# alpha of 0 makes every later object invisible.
patches = [("C", (0, 1, 1)), ("M", (1, 0, 1)), ("Y", (1, 1, 0)),
           ("K", (0, 0, 0)), ("R", (1, 0, 0)), ("G", (0, 1, 0)),
           ("B", (0, 0, 1)), ("25", (.75, .75, .75)), ("50", (.5, .5, .5)),
           ("75", (.25, .25, .25))]
GAP = 1.2
PS = min(7.0, (W - 2 * M - (len(patches) - 1) * GAP) / len(patches))
PY = 4.5
for i, (label, rgb) in enumerate(patches):
    x = M + i * (PS + GAP)
    c.setFillColorRGB(*rgb)
    c.rect(x * mm, PY * mm, PS * mm, PS * mm, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    ctext(x + PS / 2, PY - 2.6, label, 3.5)

c.showPage()
c.save()
print(f"wrote {OUT}  ({W:g} x {H:g} mm, targets {HT:g} / {VT:g})")
