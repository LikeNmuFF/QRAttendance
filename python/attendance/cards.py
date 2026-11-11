"""A4 sheets of six printable student cards, using current QR credentials."""
import io
import math
from pathlib import Path

import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas

from .db import qr_payload

FONT = "AttendanceSans"
pdfmetrics.registerFont(TTFont(FONT, str(Path(__file__).parent / "static/fonts/dm-sans.ttf")))
DEFAULT_MESSAGE = "Present this code at the attendance scanner."


def wrapped_lines(text, width, size):
    """Wrap long names, including a name with no spaces, without clipping."""
    lines = []
    line = ""
    for word in text.split():
        candidate = (line + " " + word).strip()
        if pdfmetrics.stringWidth(candidate, FONT, size) <= width:
            line = candidate
            continue
        if line:
            lines.append(line)
        line = ""
        for character in word:
            if line and pdfmetrics.stringWidth(line + character, FONT, size) > width:
                lines.append(line)
                line = ""
            line += character
    if line:
        lines.append(line)
    return lines


def card_pdf(students, message=DEFAULT_MESSAGE):
    stream = io.BytesIO()
    pdf = canvas.Canvas(stream, pagesize=A4)
    pdf.setTitle("Student QR cards")
    width, height = A4
    margin, gap, card_height = 28, 12, 244
    card_width = (width - 2 * margin - gap) / 2
    pages = math.ceil(len(students) / 6)
    for page_index in range(pages):
        pdf.setFillColorRGB(0, 0, 0)
        pdf.setFont(FONT, 15)
        pdf.drawString(margin, height - 28, "Student QR cards")
        pdf.setFont(FONT, 8)
        pdf.drawRightString(width - margin, height - 28, f"Page {page_index + 1} of {pages}")
        for position, (sid, name) in enumerate(students[page_index * 6:(page_index + 1) * 6]):
            x = margin + (position % 2) * (card_width + gap)
            top = height - 52 - (position // 2) * (card_height + gap)
            center = x + card_width / 2
            pdf.setStrokeColorRGB(.65, .65, .65)
            pdf.setLineWidth(.4)
            pdf.rect(x, top - card_height, card_width, card_height)
            pdf.setFont(FONT, 10)
            pdf.drawCentredString(center, top - 20, "QR ATTENDANCE")
            # Vector modules remain sharp at any printer resolution; four-module quiet zone.
            qr = qrcode.QRCode(border=4)
            qr.add_data(qr_payload(sid))
            qr.make(fit=True)
            matrix = qr.get_matrix()
            module = 104 / len(matrix)
            left, bottom = center - 52, top - 136
            path = pdf.beginPath()
            for row, cells in enumerate(matrix):
                for column, black in enumerate(cells):
                    if black:
                        path.rect(left + column * module,
                                  bottom + (len(matrix) - row - 1) * module, module, module)
            pdf.drawPath(path, stroke=0, fill=1)
            size = 11
            while size > 8 and len(wrapped_lines(name, card_width - 24, size)) > 3:
                size -= .5
            pdf.setFont(FONT, size)
            for line_index, line in enumerate(wrapped_lines(name, card_width - 24, size)):
                pdf.drawCentredString(center, top - 151 - line_index * 12, line)
            id_size = 9
            while id_size > 6 and len(wrapped_lines("ID: " + sid, card_width - 24, id_size)) > 2:
                id_size -= .5
            pdf.setFont(FONT, id_size)
            for line_index, line in enumerate(wrapped_lines("ID: " + sid, card_width - 24, id_size)):
                pdf.drawCentredString(center, top - 194 - line_index * 10, line)
            message_size = 8
            while message_size > 6 and len(wrapped_lines(message, card_width - 24, message_size)) > 2:
                message_size -= .5
            pdf.setFont(FONT, message_size)
            for line_index, line in enumerate(wrapped_lines(message, card_width - 24, message_size)):
                pdf.drawCentredString(center, top - 222 - line_index * 10, line)
        pdf.setFont(FONT, 8)
        pdf.drawCentredString(width / 2, 15, "Print on A4 at 100% / Actual size. Cut along the light outlines.")
        pdf.showPage()
    pdf.save()
    stream.seek(0)
    return stream
