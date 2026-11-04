import base64
import uuid
from io import BytesIO

import qrcode
from qrcode.image.svg import SvgPathImage

from .models import Ticket


def issue_order_tickets(order):
    """Create one idempotent ticket per purchased quantity for ticketed items."""
    tickets = []
    for line in order.lines.select_related("item"):
        if not line.is_ticket:
            continue
        for number in range(1, line.qty + 1):
            ticket, _ = Ticket.objects.get_or_create(
                order_item=line,
                number=number,
                defaults={"code": f"CB-{uuid.uuid4().hex[:12].upper()}"},
            )
            tickets.append(ticket)
    return tickets


def qr_svg_bytes(value):
    code = qrcode.QRCode(version=None, error_correction=qrcode.constants.ERROR_CORRECT_M, box_size=5, border=2)
    code.add_data(value)
    code.make(fit=True)
    image = code.make_image(image_factory=SvgPathImage)
    output = BytesIO()
    image.save(output)
    return output.getvalue()


def qr_data_uri(value):
    return "data:image/svg+xml;base64," + base64.b64encode(qr_svg_bytes(value)).decode("ascii")
