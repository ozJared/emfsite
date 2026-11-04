import random
from decimal import Decimal
import uuid

from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify

from .presets import KINDS, SECTION_IDS, default_dict, default_labels, default_sections, default_socials

SITE_TYPES = [("artist", "Artist / Musician"), ("portfolio", "Portfolio"), ("company", "Company"), ("store", "Online store")]
THEMES = [("noir", "Noir"), ("neon", "Neon"), ("blush", "Blush"), ("sky", "Sky")]
HERO_MODES = [("photo", "Photo (fills the stage, keeps its background)"), ("cutout", "Cutout (transparent image floats)")]


class SiteSettings(models.Model):
    """One row that holds everything about how the site looks and what it says."""
    site_type = models.CharField(max_length=12, choices=SITE_TYPES, default="artist")
    theme = models.CharField(max_length=8, choices=THEMES, default="noir")
    name = models.CharField("Site name", max_length=120, default="Premium EMF")
    ghost = models.CharField("Big background word", max_length=8, default="EMF")
    tagline = models.CharField(max_length=120, default="Artist · Musician")
    blurb = models.CharField(max_length=240, default="New music, shows and stories.")
    cta = models.CharField("Main button text", max_length=40, default="Listen now")
    whatsapp_number = models.CharField(
        "Owner WhatsApp number", max_length=20, blank=True,
        help_text="With country code, e.g. 2348012345678.")
    whatsapp_checkout = models.BooleanField(
        "Use WhatsApp enquiry instead of checkout", default=False,
        help_text="When enabled, submitted orders open WhatsApp. Otherwise buyers see the order confirmation.")
    notification_email = models.EmailField("Order and contact notification email", blank=True)
    business_address = models.CharField(max_length=300, blank=True)
    show_map = models.BooleanField("Display location map", default=True)
    currency = models.CharField(max_length=4, default="₦")
    hero_image = models.ImageField(upload_to="site/", blank=True)
    about_image = models.ImageField(upload_to="site/", blank=True)
    contact_image = models.ImageField(upload_to="site/", blank=True)
    hero_mode = models.CharField(max_length=8, choices=HERO_MODES, default="photo")
    fx = models.PositiveSmallIntegerField("Focus left to right", default=50)
    fy = models.PositiveSmallIntegerField("Focus up and down", default=18)
    meta_description = models.CharField(max_length=300, blank=True)
    labels = models.JSONField(default=default_labels)
    sections = models.JSONField(default=default_sections)
    texts = models.JSONField(default=default_dict)
    vis = models.JSONField(default=default_dict)
    socials = models.JSONField(default=default_socials)
    spotify_profile = models.JSONField(default=default_dict)

    class Meta:
        verbose_name = verbose_name_plural = "Site settings"

    def __str__(self):
        return self.name

    def save(self, *a, **k):
        self.pk = 1
        super().save(*a, **k)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def wa_digits(self):
        from .utils import normalize_whatsapp
        return normalize_whatsapp(self.whatsapp_number)

    def label(self, kind):
        return self.labels.get(kind) or default_labels()[kind]

    def section_list(self):
        have = {s["id"]: s for s in self.sections if s.get("id") in SECTION_IDS}
        out = [have[s["id"]] for s in self.sections if s.get("id") in have]
        out += [{"id": i, "on": False} for i in SECTION_IDS if i not in have]
        return out

    def is_on(self, sid):
        return any(s["id"] == sid and s["on"] for s in self.section_list())


class Item(models.Model):
    KIND_CHOICES = [("catalog", "Catalog"), ("blog", "Blog"), ("news", "News")]
    kind = models.CharField(max_length=8, choices=KIND_CHOICES, db_index=True)
    title = models.CharField(max_length=160)
    slug = models.SlugField(max_length=180, unique=True, blank=True)
    date = models.DateField(default=timezone.localdate)
    summary = models.CharField("Short summary", max_length=220, blank=True)
    body = models.TextField(blank=True, help_text="Separate paragraphs with a blank line.")
    price = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal("0"),
                                validators=[MinValueValidator(0)],
                                help_text="0 means no price (a release or a service). Above 0 makes it a product with an Order button.")
    sort_order = models.PositiveIntegerField(default=0, db_index=True)
    is_ticket = models.BooleanField(
        "Sell event tickets", default=False,
        help_text="For event items, create a unique ticket for each quantity after its order is marked paid.")
    link = models.URLField("Listen / external link", blank=True)
    spotify_id = models.CharField(max_length=32, blank=True, db_index=True)
    spotify_image_url = models.URLField(max_length=1000, blank=True)
    image = models.ImageField(upload_to="items/", blank=True)
    thumb = models.ImageField(upload_to="items/", blank=True, editable=False)
    crop = models.CharField(
        "Card crop (advanced)", max_length=30, blank=True,
        validators=[RegexValidator(r"^\d{1,3}% \d{1,3}%(\|\d(\.\d+)?)?$", "Use the form: 50% 20%|1.6")],
        help_text="Optional. Position and zoom, e.g. 50% 20%|1.6")
    hue = models.PositiveSmallIntegerField(default=0, editable=False)
    is_published = models.BooleanField("Visible to visitors", default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.kind}: {self.title}"

    def save(self, *a, **k):
        if not self.pk and not self.hue:
            self.hue = random.randint(0, 359)
        if not self.slug:
            base = slugify(self.title)[:150] or "item"
            slug, n = base, 2
            while Item.objects.filter(slug=slug).exclude(pk=self.pk).exists():
                slug, n = f"{base}-{n}", n + 1
            self.slug = slug
        super().save(*a, **k)

    def delete(self, *a, **k):
        for f in (self.image, self.thumb):
            if f:
                f.delete(save=False)
        for g in self.gallery.all():
            g.image.delete(save=False)
        return super().delete(*a, **k)

    def get_absolute_url(self):
        return reverse("detail", args=[self.kind, self.slug])

    @property
    def is_product(self):
        return self.kind == "catalog" and self.price > 0

    @property
    def card_image(self):
        return self.thumb or self.image

    @property
    def card_image_url(self):
        if self.thumb:
            return self.thumb.url
        if self.image:
            return self.image.url
        return self.spotify_image_url

    @property
    def paragraphs(self):
        return [p.strip() for p in self.body.replace("\r", "").split("\n\n") if p.strip()]


class ItemImage(models.Model):
    item = models.ForeignKey(Item, on_delete=models.CASCADE, related_name="gallery")
    image = models.ImageField(upload_to="gallery/")
    position = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["position", "id"]


class Order(models.Model):
    STATUS = [("new", "New"), ("confirmed", "Confirmed"), ("paid", "Paid"), ("shipped", "Shipped"),
              ("done", "Completed"), ("cancelled", "Cancelled")]
    name = models.CharField(max_length=120)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=30)
    address = models.TextField(blank=True)
    note = models.CharField(max_length=300, blank=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=4, default="₦")
    public_token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    status = models.CharField(max_length=10, choices=STATUS, default="new", db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"Order #{self.pk} · {self.name}"


class PaymentAttempt(models.Model):
    STATUS = [("pending", "Pending"), ("paid", "Paid"), ("failed", "Failed")]
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="payment_attempts")
    reference = models.CharField(max_length=100, unique=True)
    authorization_url = models.URLField(blank=True)
    status = models.CharField(max_length=10, choices=STATUS, default="pending", db_index=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name="lines")
    item = models.ForeignKey(Item, on_delete=models.SET_NULL, null=True, blank=True)
    title = models.CharField(max_length=160)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    qty = models.PositiveSmallIntegerField(default=1)
    is_ticket = models.BooleanField(default=False)

    @property
    def subtotal(self):
        return self.price * self.qty


class Ticket(models.Model):
    order_item = models.ForeignKey(OrderItem, on_delete=models.CASCADE, related_name="tickets")
    number = models.PositiveSmallIntegerField()
    code = models.CharField(max_length=16, unique=True)
    token = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    issued_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["order_item_id", "number"]
        constraints = [
            models.UniqueConstraint(fields=["order_item", "number"], name="unique_ticket_per_order_item_number"),
        ]

    @property
    def is_valid(self):
        return self.order_item.order.status in {"paid", "shipped", "done"}


class Message(models.Model):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    body = models.TextField(max_length=3000)
    created = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.name} ({self.created:%Y-%m-%d})"
