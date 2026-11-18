"""Draw a deterministic DFPlayer pin reference in the user's photo orientation."""
import sys
from pathlib import Path

root = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(root / '.venv' / 'Lib' / 'site-packages'))
from PIL import Image, ImageDraw, ImageFont

output = root / 'docs' / 'dfplayer-pinout.png'
image = Image.new('RGB', (1600, 1380), '#f4f7fb')
draw = ImageDraw.Draw(image)
font_root = Path('C:/Windows/Fonts')


def font(size, bold=False):
    return ImageFont.truetype(str(font_root / ('arialbd.ttf' if bold else 'arial.ttf')), size)


def text(x, y, words, size=27, color='#17283b', bold=False, anchor=None):
    draw.text((x, y), words, font=font(size, bold), fill=color, anchor=anchor)


text(70, 48, 'DFPlayer Mini / MP3-TF-16P', 47, bold=True)
text(70, 112, 'Front view — same orientation as your photo', 28, color='#526479')
text(800, 190, 'TEXT + SMALL COMPONENTS AT TOP', 24, bold=True, anchor='mm')

board = (595, 245, 1005, 960)
draw.rounded_rectangle(board, radius=20, fill='#20313c', outline='#0e1c25', width=4)
for x in (660, 720, 880, 940):
    draw.rounded_rectangle((x-12, 270, x+12, 305), radius=3, fill='#c8b685')
text(800, 335, 'MP3-TF-16P', 29, color='white', bold=True, anchor='mm')
draw.rounded_rectangle((650, 390, 950, 890), radius=12, fill='#c9d2dc', outline='#8d9eae', width=4)
draw.rounded_rectangle((682, 420, 918, 848), radius=8, outline='#99a8b5', width=3)
text(800, 615, 'microSD', 39, color='#36495c', bold=True, anchor='mm')
text(800, 665, 'card holder', 25, color='#526479', anchor='mm')
draw.rounded_rectangle((690, 875, 910, 904), radius=6, fill='#14202b')
draw.line((800, 1012, 800, 933), fill='#526479', width=4)
draw.polygon([(800, 928), (790, 945), (810, 945)], fill='#526479')
text(800, 1040, 'SD CARD OPENING', 24, bold=True, anchor='mm')

left = [
    ('VCC', '+5V supply', '#b73339'),
    ('RX', 'ESP32 GPIO2 through 1kΩ', '#09699b'),
    ('TX', 'Leave unconnected', '#687789'),
    ('DAC_R', 'Unused audio output', '#687789'),
    ('DAC_L', 'Unused audio output', '#687789'),
    ('SPK1', 'Speaker terminal A', '#8445a2'),
    ('GND', 'Supply / ESP32 ground', '#177350'),
    ('SPK2', 'Speaker terminal B', '#8445a2'),
]
right = [('BUSY', 'Unused'), ('USB−', 'Unused'), ('USB+', 'Unused'),
         ('ADKEY2', 'Unused'), ('ADKEY1', 'Unused'), ('IO2', 'Unused'),
         ('GND', 'Same ground'), ('IO1', 'Unused')]

for index, (name, purpose, color) in enumerate(left):
    y = 300 + index * 83
    draw.ellipse((605, y-12, 629, y+12), fill='#d5bc7c', outline='#f5e4b6', width=2)
    draw.line((465, y, 604, y), fill=color, width=4)
    draw.ellipse((597, y-5, 607, y+5), fill=color)
    text(435, y-9, name, 34, color, True, 'rs')
    text(435, y+25, purpose, 24, color, anchor='rs')

for index, (name, purpose) in enumerate(right):
    y = 300 + index * 83
    color = '#177350' if name == 'GND' else '#687789'
    draw.ellipse((971, y-12, 995, y+12), fill='#d5bc7c', outline='#f5e4b6', width=2)
    draw.line((996, y, 1125, y), fill=color, width=3)
    text(1150, y-9, name, 32, color, True, 'ls')
    text(1150, y+25, purpose, 24, color, anchor='ls')

draw.rounded_rectangle((70, 1100, 1530, 1325), radius=18, fill='white', outline='#ccd6e1', width=2)
text(100, 1126, 'YOUR ATTENDANCE SYSTEM', 27, bold=True)
text(100, 1175, 'Speaker connects between SPK1 and SPK2 — neither speaker wire goes to GND.', 27)
text(100, 1220, 'Leave TX, DAC, USB and button-control pins unconnected.', 27)
text(100, 1265, 'Disconnect power before wiring. Confirm the orientation before connecting +5V.', 25, '#b73339', True)

output.parent.mkdir(parents=True, exist_ok=True)
image.save(output)
print(output)
