"""
Generación del comprobante (ticket) de entrega de uniforme en PDF.

Cada entrega tiene un folio estable (ver db.folio_entrega) y puede incluir
una firma digital capturada en pantalla; si no hay firma digital, el PDF
deja una línea en blanco para firma en papel, así que sirve igual con el
flujo actual (papel) o con el nuevo (firma en pantalla).
"""

from datetime import datetime
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.units import mm
from reportlab.lib.utils import ImageReader
from reportlab.pdfgen import canvas

import db

PAGE_W, PAGE_H = letter


def generar_ticket_pdf(entrega: dict) -> bytes:
    """Genera el PDF del comprobante de una entrega. `entrega` es el dict
    que regresa db.obtener_entrega(), más opcionalmente 'firma_png' (bytes)."""
    cedis = db.get_config("cedis", "CEDIS")
    folio = db.folio_entrega(entrega["id"])

    buffer = BytesIO()
    c = canvas.Canvas(buffer, pagesize=letter)

    margen = 20 * mm
    y = PAGE_H - margen

    # Encabezado
    c.setFont("Helvetica-Bold", 16)
    c.drawString(margen, y, "Comprobante de Entrega de Uniforme")
    c.setFont("Helvetica", 10)
    c.drawRightString(PAGE_W - margen, y, folio)
    y -= 8 * mm

    c.setFont("Helvetica", 10)
    c.drawString(margen, y, cedis)
    c.drawRightString(PAGE_W - margen, y, f"Fecha de entrega: {entrega['fecha']}")
    y -= 10 * mm

    c.setStrokeColor(colors.grey)
    c.line(margen, y, PAGE_W - margen, y)
    y -= 10 * mm

    def campo(etiqueta, valor):
        nonlocal y
        c.setFont("Helvetica-Bold", 10)
        c.drawString(margen, y, etiqueta)
        c.setFont("Helvetica", 10)
        c.drawString(margen + 45 * mm, y, str(valor) if valor not in (None, "") else "—")
        y -= 7 * mm

    campo("Empleado:", entrega.get("empleado"))
    campo("No. de empleado:", entrega.get("numero_empleado"))
    campo("Puesto:", entrega.get("puesto"))
    campo("Área / Ruta:", entrega.get("area"))
    y -= 3 * mm
    campo("Prenda:", entrega.get("prenda"))
    campo("Talla:", entrega.get("talla"))
    campo("Cantidad:", entrega.get("cantidad"))
    campo("Motivo de entrega:", entrega.get("motivo"))
    campo("Entregado por:", entrega.get("entregado_por"))
    if entrega.get("notas"):
        campo("Notas:", entrega.get("notas"))

    y -= 8 * mm
    c.setStrokeColor(colors.grey)
    c.line(margen, y, PAGE_W - margen, y)
    y -= 12 * mm

    firma_png = entrega.get("firma_png")
    c.setFont("Helvetica-Bold", 10)
    c.drawString(margen, y, "Firma del empleado (acuse de recibido):")
    y -= 4 * mm

    firma_box_h = 28 * mm
    firma_box_w = 90 * mm
    if firma_png:
        try:
            img = ImageReader(BytesIO(firma_png))
            c.drawImage(img, margen, y - firma_box_h, width=firma_box_w, height=firma_box_h,
                        preserveAspectRatio=True, anchor="sw", mask="auto")
            c.setFont("Helvetica-Oblique", 8)
            c.drawString(margen, y - firma_box_h - 5 * mm, "Firma capturada digitalmente en el sistema.")
        except Exception:
            firma_png = None  # cae al recuadro en blanco si la imagen no se puede leer

    if not firma_png:
        c.setStrokeColor(colors.black)
        c.rect(margen, y - firma_box_h, firma_box_w, firma_box_h)
        c.setFont("Helvetica-Oblique", 8)
        c.drawString(margen, y - firma_box_h - 5 * mm, "Espacio para firma en papel.")

    y -= firma_box_h + 15 * mm

    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawString(
        margen, y,
        "Este comprobante certifica la recepción del uniforme señalado arriba por parte del empleado.",
    )
    y -= 5 * mm
    c.drawString(margen, y, f"Generado el {datetime.now().strftime('%Y-%m-%d %H:%M')} — Folio {folio}")

    c.showPage()
    c.save()
    return buffer.getvalue()
