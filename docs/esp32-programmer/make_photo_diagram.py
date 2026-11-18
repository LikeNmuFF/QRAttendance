"""Draw wiring annotations over an unchanged, credited reference photo."""
import base64
from pathlib import Path
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent
photo = base64.b64encode((root / 'real-boards.jpg').read_bytes()).decode()
svg = f'''<svg xmlns="http://www.w3.org/2000/svg" width="1800" height="1400" viewBox="0 0 1800 1400">
<style>text{{font-family:Arial,sans-serif;fill:#17283a}} .title{{font-size:46px;font-weight:bold}} .label{{font-size:29px;font-weight:bold}} .small{{font-size:24px}} .wire{{fill:none;stroke-width:9;stroke-linecap:round;stroke-linejoin:round}} .halo{{fill:none;stroke:white;stroke-width:17;stroke-linecap:round;stroke-linejoin:round}}</style>
<rect width="1800" height="1400" fill="white"/>
<text x="70" y="70" class="title">ESP32-CAM-MB → ESP32-CAM, using jumper wires</text>
<text x="70" y="118" class="small">Real board photograph with drawn connections — not a photo of an assembled circuit.</text>
<text x="250" y="175" class="label">USB programmer base</text>
<text x="1130" y="175" class="label">Camera board</text>
<image href="data:image/jpeg;base64,{photo}" x="150" y="200" width="1500" height="844"/>
<g><path class="halo" d="M320 372 L240 372 L240 230 L1040 230 L1040 372 L1006 372"/><path class="wire" stroke="#d32932" d="M320 372 L240 372 L240 230 L1040 230 L1040 372 L1006 372"/>
<path class="halo" d="M322 406 L205 406 L205 260 L1080 260 L1080 406 L1018 406"/><path class="wire" stroke="#151515" d="M322 406 L205 406 L205 260 L1080 260 L1080 406 L1018 406"/>
<path class="halo" d="M738 490 L815 545 L815 1070 L1540 1070 L1540 480 L1422 480"/><path class="wire" stroke="#086acd" d="M738 490 L815 545 L815 1070 L1540 1070 L1540 480 L1422 480"/>
<path class="halo" d="M746 526 L780 570 L780 1100 L1580 1100 L1580 514 L1434 514"/><path class="wire" stroke="#168044" d="M746 526 L780 570 L780 1100 L1580 1100 L1580 514 L1434 514"/>
<path class="halo" d="M1388 372 L1480 350 L1480 420 L1398 406"/><path class="wire" stroke="#e3b000" d="M1388 372 L1480 350 L1480 420 L1398 406"/></g>
'''
for color, points in [('#d32932',[(320,372),(1006,372)]),('#151515',[(322,406),(1018,406)]),('#086acd',[(738,490),(1422,480)]),('#168044',[(746,526),(1434,514)]),('#e3b000',[(1388,372),(1398,406)])]:
    for x,y in points:
        svg += f'<circle cx="{x}" cy="{y}" r="10" fill="{color}" stroke="white" stroke-width="3"/>'
svg += '''
<rect x="465" y="206" width="380" height="42" fill="white"/><text x="490" y="237" class="label">RED: 5V ↔ 5V</text>
<rect x="420" y="249" width="460" height="42" fill="white"/><text x="445" y="280" class="label">BLACK: GND ↔ GND</text>
<rect x="1080" y="310" width="300" height="44" fill="white"/><text x="1100" y="341" class="small">GPIO0 ↔ GND</text>
<rect x="1100" y="354" width="260" height="40" fill="white"/><text x="1115" y="383" class="small">Upload jumper only</text>
<rect x="845" y="645" width="305" height="105" fill="white"/><text x="865" y="683" class="small">MB right socket row:</text><text x="865" y="716" class="small">6th = U0R; 7th = U0T</text>
<rect x="160" y="460" width="345" height="115" fill="white"/><text x="180" y="498" class="small">MB left socket row:</text><text x="180" y="535" class="small">1st = 5V; 2nd = GND</text>
<text x="860" y="1028" class="small" fill="#086acd">BLUE: U0R ↔ U0R (GPIO3)</text>
<text x="880" y="1140" class="small" fill="#168044">GREEN: U0T ↔ U0T (GPIO1)</text>
<text x="70" y="1205" class="label">1. Unplug USB. Connect the four wires and the yellow GPIO0 jumper.</text>
<text x="70" y="1253" class="label">2. Connect USB to MB. Press RESET on the camera board, then upload.</text>
<text x="70" y="1301" class="label">3. Remove the yellow jumper. Press camera RESET to run.</text>
<text x="70" y="1349" class="small">Socket counts are from the TOP of this photo. Match your board variant; use only MB USB power.</text>
<text x="70" y="1384" class="small">Photo: Rui Santos / Sara Santos, Random Nerd Tutorials — upload-code-esp32-cam-mb-usb</text>
</svg>'''
(root / 'real-photo-wiring.svg').write_text(svg, encoding='utf-8')
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True)
    page = browser.new_page(viewport={'width':1800,'height':1400}, device_scale_factor=1)
    page.set_content('<body style="margin:0">'+svg+'</body>')
    page.locator('svg').screenshot(path=str(root / 'real-photo-wiring.png'))
    browser.close()
print(root / 'real-photo-wiring.png')
