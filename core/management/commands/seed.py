from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand

from core.dash import apply_preset_to
from core.models import Item, SiteSettings
from core.presets import PRESETS
from core.utils import process_image

BODY = ("This is placeholder text. Replace it from the dashboard with your own words, images and details.\n\n"
        "Keep paragraphs short and clear. Use the show and hide switches to remove anything you don’t need.\n\n"
        "Every page here can become a blog post, a news update or a product page, just by choosing the content type.")
PHOTO = settings.BASE_DIR / "core" / "static" / "core" / "img" / "premium-emf.webp"

DEMO = {
    "artist": {"catalog": [("Midnight Frequency", 0), ("Gold Hour", 0), ("Velvet", 0), ("Night Sessions", 0)]},
    "portfolio": {"catalog": [("Brand Identity", 0), ("Mobile App", 0), ("Editorial Site", 0), ("Packaging", 0)]},
    "company": {"catalog": []},
    "store": {"catalog": [("Aero Runner", 48000), ("Cloud Hoodie", 65000), ("Studio Headset", 89000),
                          ("Carry Tote", 34000), ("Glass Bottle", 22000), ("Daily Cap", 29000)]},
}
CROPS = ["50% 20%|1", "50% 20%|2.1", "50% 75%|1.9", "50% 24%|3", "15% 60%|1.7", "50% 100%|1"]


class Command(BaseCommand):
    help = "Create starter content. Safe to run again: it never overwrites or duplicates what you already have."

    def add_arguments(self, parser):
        parser.add_argument("--type", default="artist", choices=list(PRESETS))

    def handle(self, *args, **o):
        kind_type = o["type"]
        s = SiteSettings.load()
        first_run = not Item.objects.exists() and not s.hero_image
        if first_run:
            apply_preset_to(s, kind_type)
            if kind_type == "artist":
                s.name, s.ghost = "Premium EMF", "EMF"
            else:
                s.name = "Your Name" if kind_type in ("portfolio", "company") else "Your Store"
            if kind_type == "artist" and PHOTO.exists():
                with open(PHOTO, "rb") as fh:
                    main, _ = process_image(File(fh), want_thumb=False)
                s.hero_image.save(main.name, main, save=False)
            s.save()
        if Item.objects.exists():
            self.stdout.write("Content already exists; nothing added.")
            return
        for n, (title, price) in enumerate(DEMO[kind_type]["catalog"]):
            it = Item(kind="catalog", title=title, price=price, summary="A short summary that appears on the card.",
                      body=BODY, link="")
            if kind_type == "artist" and PHOTO.exists():
                with open(PHOTO, "rb") as fh:
                    main, thumb = process_image(File(fh))
                it.image.save(main.name, main, save=False)
                it.thumb.save(thumb.name, thumb, save=False)
                it.crop = CROPS[n % len(CROPS)]
            it.save()
        for kind, titles in (("blog", ["Behind the scenes", "What I learned this year", "How the work gets made"]),
                             ("news", ["Big announcement coming soon", "We’re growing the team", "Now open for bookings"])):
            for t in titles:
                Item.objects.create(kind=kind, title=t, summary="A short summary that appears on the card.", body=BODY)
        self.stdout.write(self.style.SUCCESS(f"Starter content created for the “{kind_type}” site."))
