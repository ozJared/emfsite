import logging
import re
import uuid
from io import BytesIO
from smtplib import SMTPException
from urllib.parse import quote

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.files.base import ContentFile
from django.core.mail import EmailMessage
from PIL import Image, ImageOps, UnidentifiedImageError

ALLOWED_FORMATS = {"JPEG", "PNG", "WEBP", "GIF"}
MAX_UPLOAD = 8 * 1024 * 1024
logger = logging.getLogger(__name__)


def _send_site_notification(site, subject, body, log_reference, reply_to=None):
    if not site.notification_email:
        logger.warning("%s saved without email notification: no recipient configured.", log_reference)
        return False
    if not settings.EMAIL_HOST or not settings.EMAIL_HOST_USER or not settings.EMAIL_HOST_PASSWORD:
        logger.error("%s saved without email notification: SMTP is not fully configured.", log_reference)
        return False
    email = EmailMessage(
        subject=subject,
        body=body,
        to=[site.notification_email],
        reply_to=reply_to or [],
    )
    try:
        sent = email.send(fail_silently=False)
    except (SMTPException, OSError):
        logger.exception("Could not send email notification for %s.", log_reference)
        return False
    if sent != 1:
        logger.error("Email notification for %s was not accepted by the configured mail backend.", log_reference)
        return False
    return True


def notify_contact_message(site, message):
    body = f"From: {message.name}\nEmail: {message.email}\n\n{message.body}"
    return _send_site_notification(
        site, f"New message for {site.name}", body, f"contact message {message.pk}", [message.email])


def notify_order(site, order, tracking_url):
    lines = "\n".join(
        f"{line.qty} x {line.title} - {order.currency} {line.price} each"
        for line in order.lines.all()
    )
    body = (
        f"New order #{order.pk}\n\n{lines}\n\n"
        f"Total: {order.currency} {order.total}\n"
        f"Name: {order.name}\nEmail: {order.email or 'Not provided'}\nPhone: {order.phone}\n"
        f"Address: {order.address or 'Not provided'}\n"
        f"Note: {order.note or 'None'}\n\n"
        f"Order status: {tracking_url}"
    )
    return _send_site_notification(site, f"New order #{order.pk} for {site.name}", body, f"order {order.pk}")


def process_image(f, max_px=1800, thumb_px=640, want_thumb=True):
    """Validate an uploaded image, strip metadata, resize and convert to WebP.
    Returns (main, thumb) as ContentFile objects."""
    if getattr(f, "size", 0) > MAX_UPLOAD:
        raise ValidationError("That image is larger than 8 MB. Choose a smaller one.")
    try:
        f.seek(0)
        probe = Image.open(f)
        probe.verify()
        f.seek(0)
        im = Image.open(f)
        fmt = im.format
        im.load()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError, Image.DecompressionBombError):
        raise ValidationError("That file is not a valid image. Use JPG, PNG, WebP or GIF.")
    if fmt not in ALLOWED_FORMATS:
        raise ValidationError("Use a JPG, PNG, WebP or GIF image.")
    im = ImageOps.exif_transpose(im)
    alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
    im = im.convert("RGBA" if alpha else "RGB")

    def enc(px, q):
        c = im.copy()
        c.thumbnail((px, px), Image.LANCZOS)
        buf = BytesIO()
        c.save(buf, "WEBP", quality=q, method=4)
        return ContentFile(buf.getvalue(), name=uuid.uuid4().hex + ".webp")

    return enc(max_px, 84), (enc(thumb_px, 78) if want_thumb else None)


def digits(s):
    return re.sub(r"\D", "", s or "")


def normalize_whatsapp(raw):
    """Return international digits for wa.me. A Nigerian local number (0801...) becomes 234801..."""
    d = digits(raw)
    if len(d) == 11 and d.startswith("0"):
        d = "234" + d[1:]
    return d


def wa_link(number, text=""):
    n = digits(number)
    return f"https://wa.me/{n}?text={quote(text)}" if text else f"https://wa.me/{n}"


def client_ip(request):
    from django.conf import settings
    if settings.TRUST_PROXY:
        fwd = request.META.get("HTTP_X_FORWARDED_FOR", "")
        if fwd:
            return fwd.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "0.0.0.0")
