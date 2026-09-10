"""Generate a caliper-measurable test card for the print hub spike.

    make-test-card.py                     -> 140.0 x 88.0, the ZC10L card
    make-test-card.py 83.98 58.92 65 40   -> W H [h-target v-target]

Print it with noscale, then measure the two targets with digital calipers.
Any renderer that scales the page shows up as a wrong reading.

Author the page at the *imageable* size the driver reports, not the form
size. pdfium_print.py blits 1:1 centred inside HORZRES x VERTRES, so a page
authored larger than the imageable area is clipped or rescaled, and both
failures are invisible by eye on a badge. Read the imageable size from
GetDeviceCaps HORZRES/VERTRES divided by LOGPIXELSX, because a driver with
unprintable margins reports a physical page bigger than it can image: the
Brother QL-800 is 1062 x 732 px physical against 992 x 696 imageable.

Two layout rules, both learned on the 84 mm label, where the first version
of this file produced an unmeasurable card.

The caliper targets get exclusive space. A right-hand column belongs to the
vertical target alone and the ruler stops short of it, because deriving
positions from W independently once put the horizontal target's right tick
0.5 mm from the vertical target's line.

Bands stack bottom-up from measured heights, never from guessed fractions of
H. Guessing put a red bar on top of two ladder rows. If the stack does not
fit, the ladders lose rows in a fixed order rather than overlapping, and the
script says what it dropped.
"""

import sys

from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

args = sys.argv[1:]
W, H = (float(args[0]), float(args[1])) if len(args) >= 2 else (140.0, 88.0)
HT = float(args[2]) if len(args) >= 3 else 100.0
VT = float(args[3]) if len(args) >= 4 else 50.0

M = 5.0            # margin to the registration crosses
RIGHT = 14.0       # right-hand column, the vertical target's alone
ARM = 3.0          # caliper tick arm half-length
CONTENT = W - M - RIGHT                     # right edge of the content column

# Ordered hardest-first on purpose. Trimming drops from the end, so a short
# page keeps the hairlines and the small type, which are the entries that
# actually diagnose a renderer. A 2 pt rule and 8 pt text always survive.
LINE_WIDTHS = (0.1, 0.25, 0.5, 1.0, 2.0)
TEXT_SIZES = (4, 5, 6, 8)

# Clamp the targets so they cannot collide, and report the value actually used.
HT_MAX, VT_MAX = CONTENT - M, H - 2 * M - 8.0
if HT > HT_MAX:
    HT = round(HT_MAX - HT_MAX % 5)
    print(f"h-target does not fit in {HT_MAX:.2f} mm, using {HT:g}")
if VT > VT_MAX:
    VT = round(VT_MAX - VT_MAX % 5)
    print(f"v-target does not fit in {VT_MAX:.2f} mm, using {VT:g}")

GAP = 1.2
PS = min(7.0, (CONTENT - M - (len(patches := [
    ("C", (0, 1, 1)), ("M", (1, 0, 1)), ("Y", (1, 1, 0)), ("K", (0, 0, 0)),
    ("R", (1, 0, 0)), ("G", (0, 1, 0)), ("B", (0, 0, 1)),
    ("25", (.75, .75, .75)), ("50", (.5, .5, .5)), ("75", (.25, .25, .25)),
]) - 1) * GAP) / len(patches))


def stack(n_line, n_text):
    """Position every band bottom-up. Returns the layout and the height used."""
    y = {}
    y["patch_label"] = M - 3.4
    y["patch"] = M - 1.0
    y["red"] = y["patch"] + PS + 2.2                    # red bar bottom
    ladder_bottom = y["red"] + 3.4 + 2.8
    y["lines"] = [ladder_bottom + i * 2.0 for i in range(n_line)]
    y["texts"] = [ladder_bottom + 0.4 + i * 3.0 for i in range(n_text)]
    y["ladder_label"] = max(y["lines"][-1], y["texts"][-1] + 2.4) + 2.4
    y["target"] = y["ladder_label"] + 2.6 + ARM         # target centreline
    y["target_label"] = y["target"] + ARM + 1.2
    y["ruler_caption"] = y["target_label"] + 3.4
    y["ruler"] = y["ruler_caption"] + 3.2
    y["subtitle"] = y["ruler"] + 2.6 + 3.6 + 2.4        # clear of tick labels
    y["title"] = y["subtitle"] + 3.6
    return y, y["title"] + 2.6


for n_line, n_text in ((5, 4), (4, 4), (4, 3), (3, 3), (3, 2), (2, 2)):
    Y, used = stack(n_line, n_text)
    if used <= H:
        break

# Centre the band block when the page is much taller than the content needs.
# A 302 mm badge would otherwise carry everything in its bottom 57 mm with a
# quarter of a metre of white space above it. The vertical target is placed
# from H directly, so it is unaffected.
if used < H:
    shift = (H - used) / 2.0
    Y = {k: [e + shift for e in v] if isinstance(v, list) else v + shift
         for k, v in Y.items()}
if n_line < len(LINE_WIDTHS) or n_text < len(TEXT_SIZES):
    print(f"page is {H:g} mm, needs {used:.1f}: ladders trimmed to "
          f"{n_line} line widths and {n_text} text sizes")

OUT = f"test-card-{W:g}x{H:g}.pdf"
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

# --- identity ---
text(M, Y["title"], "PheedLoop Print Hub - spike test card", 6.5, "Helvetica-Bold")
text(M, Y["subtitle"], f"{W:g} x {H:g} mm  noscale   renderer ____  queue ____", 4.2)

# --- ruler, 1 mm ticks, origin at the top-left cross ---
# Stops short of the right-hand column so it never crosses the vertical target.
RULER_LEN = int(CONTENT - M)
line(M, Y["ruler"], M + RULER_LEN, Y["ruler"], 0.25)
for i in range(RULER_LEN + 1):
    h = 2.6 if i % 10 == 0 else 1.8 if i % 5 == 0 else 0.9
    line(M + i, Y["ruler"], M + i, Y["ruler"] + h, 0.15)
for i in range(0, RULER_LEN + 1, 20):
    ctext(M + i, Y["ruler"] + 3.6, str(i), 4.0)
text(M, Y["ruler_caption"], f"ruler 1 mm ticks, origin {M:g} mm from left edge", 4.0)

# --- horizontal caliper target. Nothing else enters this band. ---
TY = Y["target"]
TX0 = M + (CONTENT - M - HT) / 2.0
line(TX0, TY, TX0 + HT, TY, 0.35)
for x in (TX0, TX0 + HT):
    line(x, TY - ARM, x, TY + ARM, 0.45)
ctext(TX0 + HT / 2.0, Y["target_label"], f"{HT:.2f} mm  tick centre to tick centre", 4.6)

# --- right-hand column: vertical caliper target, its space alone ---
VX = W - RIGHT / 2.0 - 1.5
VY0 = (H - VT) / 2.0
line(VX, VY0, VX, VY0 + VT, 0.35)
for y in (VY0, VY0 + VT):
    line(VX - ARM, y, VX + ARM, y, 0.45)
c.saveState()
c.translate(VX * mm, (VY0 + VT / 2.0) * mm)
c.rotate(90)
c.setFont("Helvetica", 4.6)
c.drawCentredString(0, (ARM + 1.0) * mm, f"{VT:.2f} mm")
c.restoreState()

# --- line width and text size ladders, side by side ---
text(M, Y["ladder_label"], "line width", 4.0)
for w, y in zip(LINE_WIDTHS, reversed(Y["lines"])):
    line(M, y, M + 12, y, w)
    text(M + 13, y - 0.6, f"{w}pt", 3.5)

TX2 = M + 22.0
text(TX2, Y["ladder_label"], "text size", 4.0)
for s, y in zip(TEXT_SIZES, reversed(Y["texts"])):
    text(TX2, y, f"{s}pt Helvetica 0O1lI8B", s)

# --- red channel test, for two-colour media such as Brother DK-2251 ---
# The QL-800 reports colordevice 0 and dmColor 1, monochrome, even with
# black/red stock loaded, so whether red survives is an empirical question.
c.setFillColorRGB(1, 0, 0)
c.rect(M * mm, Y["red"] * mm, 16 * mm, 3.4 * mm, stroke=0, fill=1)
text(M + 17, Y["red"] + 1.0, "RED CHANNEL: bar and text are pure 255,0,0", 4.0)
c.setFillColorRGB(0, 0, 0)

# --- colour patches ---
# Keep these 3-tuples. setFillColorRGB reads a 4th value as alpha, and an
# alpha of 0 makes every later object invisible.
for i, (label, rgb) in enumerate(patches):
    x = M + i * (PS + GAP)
    c.setFillColorRGB(*rgb)
    c.rect(x * mm, Y["patch"] * mm, PS * mm, PS * mm, stroke=0, fill=1)
    c.setFillColorRGB(0, 0, 0)
    ctext(x + PS / 2, Y["patch_label"], label, 3.5)

c.showPage()
c.save()
print(f"wrote {OUT}  ({W:g} x {H:g} mm, targets {HT:g} / {VT:g})")
