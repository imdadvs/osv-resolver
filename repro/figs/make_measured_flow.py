"""Render the audited advisory funnel for the Substack article."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


OUT = str(Path(__file__).with_name("measured-flow.png"))
W, H = 1600, 1180
BG = "#FFFFFF"
INK = "#17243A"
MUTED = "#526174"
CONNECTOR = "#B8C5D1"
BLUE = "#2958B7"
ORANGE = "#D95F20"
TEAL = "#087F72"

font_dir = "/System/Library/Fonts/Supplemental"
regular = font_dir + "/Arial.ttf"
bold = font_dir + "/Arial Bold.ttf"


def font(size, heavy=False):
    return ImageFont.truetype(bold if heavy else regular, size)


im = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(im)


def center_text(text, cx, top, face, color):
    box = d.textbbox((0, 0), text, font=face)
    d.text((cx - (box[2] - box[0]) / 2, top), text, font=face, fill=color)


def card(box, number, label, *, fill, color, note=None, outline=None):
    x0, y0, x1, y1 = box
    d.rounded_rectangle(box, radius=24, fill=fill, outline=outline, width=3 if outline else 1)
    cx = (x0 + x1) / 2
    if note:
        center_text(number, cx, y0 + 22, font(59, True), color)
        center_text(label, cx, y0 + 91, font(30, True), color)
        center_text(note, cx, y0 + 124, font(22), color)
    else:
        center_text(number, cx, y0 + 25, font(60, True), color)
        center_text(label, cx, y0 + 98, font(29, True), color)


def line(points):
    d.line(points, fill=CONNECTOR, width=7, joint="curve")


d.text((85, 47), "From Go advisories to test evidence", font=font(61, True), fill=INK)
d.text((88, 126), "The observed funnel, with pipeline flags kept distinct from archived run transitions", font=font(27), fill=MUTED)

# Draw connectors before the cards so lines meet their borders cleanly.
line([(800, 331), (800, 368), (330, 368), (330, 415)])
line([(800, 368), (880, 368), (880, 415)])
line([(800, 368), (1370, 368), (1370, 415)])
line([(330, 585), (330, 634), (475, 634), (475, 676)])
line([(330, 634), (1125, 634), (1125, 676)])
line([(475, 851), (475, 899), (400, 899), (400, 941)])
line([(475, 899), (1175, 899), (1175, 941)])

card((490, 185, 1110, 331), "1,525", "selected Go advisory groups", fill=INK, color="#FFFFFF")

card((70, 415, 590, 585), "871", "test path", fill=BLUE, color="#FFFFFF", note="807 retained extracted test names")
card((625, 415, 1135, 585), "630", "no detected changed Go test", fill="#EBF0F5", color=INK)
card((1205, 415, 1535, 585), "24", "other outcomes", fill="#F3F5F7", color=INK)

card((150, 676, 800, 851), "477", "pipeline flags · provisional", fill=ORANGE, color="#FFFFFF", note="364 direct  ·  108 reversal  ·  5 retry/search")
card((855, 676, 1395, 851), "394", "unresolved test-path cases", fill="#EBF0F5", color=INK)

card((110, 941, 690, 1100), "338", "archived raw-log transitions", fill=TEAL, color="#FFFFFF", note="aggregate old FAIL  →  fixed PASS")
card((875, 941, 1475, 1100), "139", "other provisional flags", fill="#FFF2EA", color=INK, outline="#F2B99C")

d.text((88, 1132), "All flags need advisory attribution; run transitions alone do not establish deployment reachability.", font=font(23), fill=MUTED)

im.save(OUT, "PNG", optimize=True)
print(OUT)
