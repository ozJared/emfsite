import json
import hashlib
import hmac
import tempfile
from decimal import Decimal
from io import BytesIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core import mail
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image

from .forms import ItemForm, OwnerProfileForm, SettingsForm
from .models import Item, Order, OrderItem, PaymentAttempt, SiteSettings, Ticket
from .payments import PaystackError, _request_json, initialize_transaction, is_configured
from .presets import SOCIAL_NAMES

U = get_user_model()
LOCMEM = {"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}


def png():
    b = BytesIO()
    Image.new("RGB", (40, 30), (200, 30, 30)).save(b, "PNG")
    return SimpleUploadedFile("x.png", b.getvalue(), content_type="image/png")


@override_settings(CACHES=LOCMEM, MEDIA_ROOT=tempfile.mkdtemp())
class SiteTests(TestCase):
    def setUp(self):
        cache.clear()
        self.owner = U.objects.create_user("owner", password="correct-horse-battery", is_staff=True)
        self.fan = U.objects.create_user("fan", password="correct-horse-battery")
        self.platform_admin = U.objects.create_superuser("platform-admin", "admin@example.test", "correct-horse-battery")
        s = SiteSettings.load()
        s.whatsapp_number = "08012345678"
        s.save()
        self.product = Item.objects.create(kind="catalog", title="Aero Runner", price=Decimal("15000"))
        self.post = Item.objects.create(kind="blog", title="Hello world", body="One.\n\nTwo.")

    def login(self):
        self.client.login(username="owner", password="correct-horse-battery")

    def login_platform_admin(self):
        self.client.login(username="platform-admin", password="correct-horse-battery")

    def jpost(self, name, data):
        return self.client.post(reverse(name), json.dumps(data), content_type="application/json")

    # --- visitors never get edit tools
    def test_visitor_sees_no_edit_ui(self):
        r = self.client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, "edit.js")
        self.assertNotContains(r, "Edit mode")

    def test_visitor_cannot_use_api(self):
        self.assertEqual(self.jpost("api_text", {"key": "hero.h", "value": "x"}).status_code, 403)
        self.assertEqual(self.jpost("api_vis", {"key": "hero.p", "visible": False}).status_code, 403)

    def test_non_owner_cannot_log_in(self):
        r = self.client.post(reverse("login"), {"username": "fan", "password": "correct-horse-battery"})
        self.assertEqual(r.status_code, 200)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertContains(r, "Enable Staff status for an owner account")

    def test_staff_owner_and_platform_superuser_can_both_sign_in(self):
        self.owner.set_password("owner-test-password")
        self.owner.save(update_fields=["password"])

        owner_response = self.client.post(reverse("login"), {
            "username": "owner",
            "password": "owner-test-password",
        })
        self.assertRedirects(owner_response, reverse("home"))
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.owner.pk))
        self.assertEqual(self.client.get(reverse("dash")).status_code, 200)
        self.assertNotContains(self.client.get(reverse("dash")), "Manage logins")

        self.client.logout()
        admin_response = self.client.post(reverse("login"), {
            "username": "platform-admin",
            "password": "correct-horse-battery",
        })
        self.assertRedirects(admin_response, reverse("home"))
        self.assertEqual(self.client.session.get("_auth_user_id"), str(self.platform_admin.pk))
        self.assertContains(self.client.get(reverse("dash")), "Manage logins")

    def test_login_rate_limit(self):
        for _ in range(5):
            self.client.post(reverse("login"), {"username": "owner", "password": "wrong"})
        r = self.client.post(reverse("login"), {"username": "owner", "password": "correct-horse-battery"})
        self.assertEqual(r.status_code, 429)

    # --- owner edit mode
    def test_edit_mode_and_saved_text_shows_for_everyone(self):
        self.login_platform_admin()
        self.client.post(reverse("edit_toggle"), {"next": "/"})
        response = self.client.get("/")
        self.assertContains(response, "edit.js")
        self.assertContains(response, "Editing · tap to save")
        self.assertEqual(self.jpost("api_text", {"key": "hero.h", "value": "Hello EMF"}).status_code, 200)
        self.client.logout()
        self.assertContains(self.client.get("/"), "Hello EMF")

    def test_edit_mode_exposes_social_controls_and_marquee(self):
        self.login_platform_admin()
        self.client.post(reverse("edit_toggle"), {"next": "/"})
        s = SiteSettings.load()
        s.socials = [
            {"n": "instagram", "u": "https://instagram.com/example"},
            {"n": "tiktok", "u": ""},
            {"n": "linkedin", "u": "https://linkedin.com/in/example"},
        ]
        s.save(update_fields=["socials"])
        response = self.client.get("/")
        self.assertContains(response, 'data-vis="marq"')
        self.assertContains(response, 'data-key="marq.text"')
        self.assertContains(response, f'data-vis="item-{self.product.pk}"')
        self.assertContains(response, f'data-vis="item-{self.post.pk}"')
        for key in ("header.menu", "header.cart", "nav.home"):
            self.assertContains(response, f'data-vis="{key}"')
        self.assertContains(response, 'data-vis="social.instagram"')
        self.assertContains(response, 'data-vis="social.linkedin"')
        self.assertContains(response, 'data-vis="social.whatsapp"')
        self.assertNotContains(response, 'data-vis="social.tiktok"')
        self.assertNotContains(response, "data-social-empty")
        social_names = [social["n"] for social in response.context["socs"]]
        self.assertEqual(social_names, ["instagram", "linkedin", "whatsapp"])
        self.assertContains(response, '<nav class="social-menu" aria-label="Social profiles">')
        self.assertContains(response, '<rect x="3" y="3" width="18" height="18" rx="5"/>')
        self.assertContains(response, 'class="brand-icon brand-icon-linkedin"')
        social_markup = response.content.decode().split('<nav class="social-menu"', 1)[1].split("</nav>", 1)[0]
        self.assertNotIn("<text", social_markup)

    def test_platform_admin_can_hide_header_cart_for_visitors(self):
        self.login_platform_admin()
        self.assertEqual(self.jpost("api_vis", {"key": "header.cart", "visible": False}).status_code, 200)
        self.client.logout()
        self.assertNotContains(self.client.get("/"), 'data-vis="header.cart"')

    def test_visitor_login_is_hidden_until_header_click_sequence(self):
        response = self.client.get("/")
        self.assertContains(response, 'id="secret-login"')
        self.assertContains(response, 'id="secret-login" class="head-toggle secret-login" href="/login/" aria-label="Owner login" title="Owner login" hidden')
        self.assertContains(response, "public.js?v=10")
        self.assertNotContains(response, 'data-vis="header.login"')

    def test_superuser_can_manage_logins_but_regular_owner_cannot(self):
        self.login_platform_admin()
        response = self.client.get(reverse("dash"))
        self.assertContains(response, "Manage logins")
        self.assertContains(response, reverse("admin:auth_user_changelist"))
        self.client.logout()
        self.login()
        self.assertNotContains(self.client.get(reverse("dash")), "Manage logins")

    def test_spotify_import_controls_and_endpoint_are_removed(self):
        from django.urls import Resolver404, resolve

        self.login_platform_admin()
        response = self.client.get(reverse("dash_settings"))
        self.assertNotContains(response, "Spotify artist import")
        self.assertNotContains(response, "Import from Spotify")
        with self.assertRaises(Resolver404):
            resolve("/dashboard/spotify/import/")

    def test_existing_spotify_hero_embed_is_preserved(self):
        site = SiteSettings.load()
        site.spotify_profile = {
            "name": "Sample Artist",
            "popular_track": {
                "id": "4uLU6hMCjMI75M1A2tKUQC",
                "name": "Popular Song",
                "url": "https://open.spotify.com/track/4uLU6hMCjMI75M1A2tKUQC",
            },
        }
        site.save(update_fields=["spotify_profile"])
        response = self.client.get(reverse("home"))
        self.assertContains(response, "https://open.spotify.com/embed/track/4uLU6hMCjMI75M1A2tKUQC")
        self.assertContains(response, "Popular Song")

    def test_spotify_embed_code_fills_release_title_art_and_player(self):
        track_id = "0HbbNYD4lMSUgZSV9mEasy"
        embed_code = (
            '<iframe src="https://open.spotify.com/embed/track/'
            f'{track_id}?utm_source=generator"></iframe>'
        )
        response_data = (
            '{"title":"Chairman","thumbnail_url":'
            '"https://image-cdn-ak.spotifycdn.com/image/cover"}'
        ).encode()
        response = MagicMock()
        response.__enter__.return_value.read.return_value = response_data
        with patch("core.spotify_embed.urlopen", return_value=response) as urlopen:
            form = ItemForm({
                "title": "",
                "date": "2026-11-03",
                "summary": "",
                "body": "",
                "price": "0",
                "link": "",
                "is_ticket": "",
                "crop": "",
                "is_published": "on",
                "spotify_embed": embed_code,
            }, kind="catalog")
            self.assertTrue(form.is_valid(), form.errors)
            item = form.save(commit=False)
            item.kind = "catalog"
            item.save()

        request = urlopen.call_args.args[0]
        self.assertIn("oembed?url=", request.full_url)
        self.assertEqual(item.title, "Chairman")
        self.assertEqual(item.link, f"https://open.spotify.com/track/{track_id}")
        self.assertEqual(item.spotify_id, track_id)
        self.assertEqual(item.card_image_url, "https://image-cdn-ak.spotifycdn.com/image/cover")
        detail = self.client.get(item.get_absolute_url())
        self.assertContains(detail, f"https://open.spotify.com/embed/track/{track_id}")
        self.assertContains(detail, "spotify-track-embed")

    def test_spotify_embed_parser_rejects_non_spotify_iframe(self):
        form = ItemForm({
            "title": "",
            "date": "2026-11-03",
            "summary": "",
            "body": "",
            "price": "0",
            "link": "",
            "is_ticket": "",
            "crop": "",
            "is_published": "on",
            "spotify_embed": '<iframe src="https://evil.example/track/123"></iframe>',
        }, kind="catalog")
        self.assertFalse(form.is_valid())
        self.assertIn("spotify_embed", form.errors)

    def test_platform_admin_can_hide_a_carousel_item(self):
        self.login_platform_admin()
        response = self.jpost("api_vis", {"key": f"item-{self.product.pk}", "visible": False})
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        self.assertNotContains(self.client.get("/"), f'data-vis="item-{self.product.pk}"')

    def test_superuser_can_reorder_releases_and_visitors_see_saved_order(self):
        second = Item.objects.create(kind="catalog", title="Second release")
        third = Item.objects.create(kind="catalog", title="Third release")
        self.login_platform_admin()
        self.client.post(reverse("edit_toggle"), {"next": "/"})
        edit_home = self.client.get(reverse("home"))
        self.assertContains(edit_home, 'data-reorder-list="catalog"')
        self.assertContains(edit_home, "Move earlier")
        self.assertContains(edit_home, "Move later")

        response = self.jpost("api_item_order", {
            "kind": "catalog",
            "ids": [third.pk, self.product.pk, second.pk],
        })
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            list(Item.objects.filter(kind="catalog").order_by("sort_order").values_list("pk", flat=True)),
            [third.pk, self.product.pk, second.pk],
        )

        self.client.logout()
        listing = self.client.get(reverse("list", args=["catalog"])).content.decode()
        self.assertLess(listing.index("Third release"), listing.index("Aero Runner"))
        self.assertLess(listing.index("Aero Runner"), listing.index("Second release"))

    def test_release_order_rejects_duplicates_and_visitors(self):
        second = Item.objects.create(kind="catalog", title="Second release")
        self.assertEqual(
            self.jpost("api_item_order", {"kind": "catalog", "ids": [self.product.pk, second.pk]}).status_code,
            403,
        )
        self.login()
        response = self.jpost("api_item_order", {
            "kind": "catalog",
            "ids": [self.product.pk, self.product.pk],
        })
        self.assertEqual(response.status_code, 400)
        self.product.refresh_from_db()
        self.assertEqual(self.product.sort_order, 0)

    def test_settings_form_has_fields_for_supported_socials(self):
        form = SettingsForm()
        profile_form = OwnerProfileForm()
        for name in SOCIAL_NAMES:
            if name != "whatsapp":
                self.assertIn(f"soc_{name}", form.fields)
                self.assertIn(f"soc_{name}", profile_form.fields)
        self.assertIn("whatsapp_checkout", form.fields)
        self.assertNotIn("theme", profile_form.fields)
        self.assertNotIn("site_type", profile_form.fields)

    def test_dashboard_social_links_are_collapsed(self):
        self.login()
        response = self.client.get(reverse("dash_settings"))
        self.assertContains(response, '<details class="social-fields">')
        self.assertContains(response, "Owner profile")
        self.assertNotContains(response, "Site type")

    def test_whatsapp_checkout_requires_an_owner_number(self):
        data = SettingsForm.initial_for(SiteSettings.load())
        data["whatsapp_number"] = ""
        data["whatsapp_checkout"] = True
        form = SettingsForm(data)
        self.assertFalse(form.is_valid())
        self.assertIn("whatsapp_number", form.errors)

    def test_hide_element_hides_for_visitors_only(self):
        self.login_platform_admin()
        self.jpost("api_vis", {"key": "hero.p", "visible": False})
        self.client.logout()
        self.assertNotContains(self.client.get("/"), 'data-key="hero.p"')

    def test_sections_toggle_and_preset_keep_content(self):
        self.login_platform_admin()
        self.jpost("api_preset", {"type": "store"})
        s = SiteSettings.load()
        self.assertEqual(s.site_type, "store")
        self.assertTrue(s.is_on("catalog"))
        self.assertEqual(Item.objects.count(), 2)

    def test_regular_owner_cannot_change_site_design(self):
        self.login()
        self.assertEqual(self.client.post(reverse("edit_toggle"), {"next": "/"}).status_code, 404)
        self.assertEqual(self.jpost("api_text", {"key": "hero.h", "value": "Changed"}).status_code, 403)
        self.assertEqual(self.jpost("api_vis", {"key": "header.login", "visible": False}).status_code, 403)
        self.assertEqual(self.jpost("api_section", {"id": "contact", "action": "toggle"}).status_code, 403)
        self.assertEqual(self.jpost("api_theme", {"theme": "neon"}).status_code, 403)
        self.assertEqual(self.jpost("api_preset", {"type": "store"}).status_code, 403)
        self.assertEqual(self.client.post(reverse("dash_preset"), {"type": "store"}).status_code, 302)
        self.assertEqual(SiteSettings.load().site_type, "artist")
        self.assertNotContains(self.client.get("/"), "Edit mode")

    def test_regular_owner_cannot_change_site_settings_in_django_admin(self):
        self.login()
        response = self.client.get("/django-admin/core/sitesettings/1/change/")
        self.assertEqual(response.status_code, 403)

    # --- CRUD
    def test_item_crud(self):
        self.login()
        r = self.client.post(reverse("dash_item_new", args=["news"]), {"title": "Big news", "date": "2026-10-30", "body": "Text", "is_published": "on"})
        self.assertEqual(r.status_code, 302)
        it = Item.objects.get(title="Big news")
        self.assertEqual(it.kind, "news")
        self.assertContains(self.client.get(it.get_absolute_url()), "Big news")
        self.client.post(reverse("dash_item_edit", args=[it.pk]), {"title": "Bigger news", "date": "2026-10-30", "body": "Text", "is_published": "on"})
        it.refresh_from_db()
        self.assertEqual(it.title, "Bigger news")
        self.client.post(reverse("dash_item_delete", args=[it.pk]))
        self.assertFalse(Item.objects.filter(pk=it.pk).exists())

    def test_image_upload_is_converted(self):
        self.login()
        self.client.post(reverse("dash_item_new", args=["catalog"]),
                         {"title": "Pic", "date": "2026-10-30", "price": "5000", "is_published": "on", "image": png()})
        it = Item.objects.get(title="Pic")
        self.assertTrue(it.image.name.endswith(".webp"))
        self.assertTrue(it.thumb)

    def test_draft_hidden_from_visitors(self):
        Item.objects.filter(pk=self.post.pk).update(is_published=False)
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 404)
        self.login()
        self.assertEqual(self.client.get(self.post.get_absolute_url()).status_code, 200)

    # --- the two detail pages
    def test_detail_pages(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "Add to order")
        self.assertContains(response, 'class="art big product-art"')
        self.assertContains(response, 'class="product-price-badge"')
        self.assertNotContains(response, 'class="price"')
        self.assertContains(response, 'aria-label="Ask about Aero Runner on WhatsApp"')
        self.assertNotContains(response, "Continue to checkout")
        self.assertLess(response.content.index(b'class="product-actions"'),
                        response.content.index(b'class="mut lede"'))
        self.login_platform_admin()
        self.client.post(reverse("edit_toggle"), {"next": self.product.get_absolute_url()})
        self.assertContains(self.client.get(self.product.get_absolute_url()), 'aria-label="Edit Aero Runner"')
        r = self.client.get(self.post.get_absolute_url())
        self.assertContains(r, "Hello world")
        self.assertNotContains(r, "Order now")

    def test_product_detail_and_checkout_flow(self):
        response = self.client.get(self.product.get_absolute_url())
        self.assertContains(response, "Add to order")
        self.assertContains(response, 'name="qty"')
        self.client.post(reverse("cart_add", args=[self.product.pk]), {"qty": "2"})
        response = self.client.get(reverse("checkout"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Order summary")
        site = SiteSettings.load()
        site.whatsapp_number = ""
        site.save(update_fields=["whatsapp_number"])
        response = self.client.post(reverse("checkout"), {
            "name": "Ada", "email": "ada@example.test", "phone": "08099998888",
        })
        order = Order.objects.get()
        self.assertRedirects(response, reverse("order_done_token", args=[order.public_token]))
        status_page = self.client.get(reverse("order_done_token", args=[order.public_token]))
        self.assertContains(status_page, "Order placed — payment pending")
        self.assertContains(status_page, "No payment was taken")
        self.assertNotContains(status_page, "Your event tickets")
        self.assertEqual(order.total, Decimal("30000"))

    def test_paid_order_issues_unique_printable_qr_tickets_once(self):
        event = Item.objects.create(kind="catalog", title="Live Show", price=Decimal("8000"), is_ticket=True)
        order = Order.objects.create(name="Ada", phone="08099998888", total=Decimal("16000"))
        line = OrderItem.objects.create(order=order, item=event, title=event.title, price=event.price, qty=2, is_ticket=True)
        self.login()
        response = self.client.post(reverse("dash_order", args=[order.pk]), {"status": "paid"})
        self.assertRedirects(response, reverse("dash_order", args=[order.pk]))
        tickets = list(Ticket.objects.filter(order_item=line))
        self.assertEqual(len(tickets), 2)
        self.assertEqual(len({t.code for t in tickets}), 2)
        self.client.post(reverse("dash_order", args=[order.pk]), {"status": "paid"})
        self.assertEqual(Ticket.objects.filter(order_item=line).count(), 2)
        self.client.logout()
        ticket_page = self.client.get(reverse("ticket_detail", args=[tickets[0].token]))
        self.assertContains(ticket_page, tickets[0].code)
        self.assertContains(ticket_page, "data:image/svg+xml;base64,")
        self.assertContains(ticket_page, "Download QR code")
        qr_download = self.client.get(reverse("ticket_qr_download", args=[tickets[0].token]))
        self.assertEqual(qr_download["Content-Type"], "image/svg+xml")
        self.assertIn("attachment;", qr_download["Content-Disposition"])
        self.assertIn(tickets[0].code, qr_download["Content-Disposition"])
        self.assertContains(self.client.get(reverse("ticket_verify", args=[tickets[0].token])), "Valid ticket")
        order.status = "cancelled"
        order.save(update_fields=["status"])
        self.assertContains(self.client.get(reverse("ticket_verify", args=[tickets[0].token])), "Invalid ticket")
        self.assertEqual(self.client.get(reverse("ticket_qr_download", args=[tickets[0].token])).status_code, 404)

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.test",
        EMAIL_HOST_USER="owner@example.test",
        EMAIL_HOST_PASSWORD="configured-for-test",
    )
    def test_contact_message_email_notification_uses_configured_recipient(self):
        site = SiteSettings.load()
        site.notification_email = "alerts@example.test"
        site.save(update_fields=["notification_email"])
        response = self.client.post(reverse("contact"), {
            "name": "Ada", "email": "ada@example.test", "body": "Hello", "website": "",
        })
        self.assertRedirects(response, reverse("contact"))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alerts@example.test"])
        self.assertEqual(mail.outbox[0].reply_to, ["ada@example.test"])

    def test_about_and_contact_show_google_map_from_address_only(self):
        site = SiteSettings.load()
        site.business_address = "Lagos, Nigeria"
        site.save()
        about = self.client.get(reverse("contact"))
        self.assertContains(about, "maps.google.com/maps?")
        self.assertContains(about, "output=embed")
        self.assertContains(about, "<iframe")
        self.assertContains(about, "Open in Google Maps")
        self.assertContains(about, "About Premium EMF")
        self.assertContains(about, 'class="contact-layout"')
        self.assertContains(about, 'class="contact-story-card"')
        self.assertContains(about, 'class="contact-message-card"')
        self.assertContains(self.client.get(reverse("contact")), "Lagos, Nigeria")
        self.login()
        profile_data = OwnerProfileForm.initial_for(site)
        profile_data["show_map"] = False
        response = self.client.post(reverse("dash_settings"), profile_data)
        self.assertRedirects(response, reverse("dash_settings"))
        site.refresh_from_db()
        self.assertFalse(site.show_map)
        self.assertNotContains(self.client.get(reverse("contact")), "<iframe")
        profile_data["show_map"] = True
        self.client.post(reverse("dash_settings"), profile_data)
        site.refresh_from_db()
        self.assertTrue(site.show_map)
        self.assertContains(self.client.get(reverse("contact")), "<iframe")
        self.assertRedirects(self.client.get(reverse("about")), reverse("contact"), status_code=301)
        self.assertNotContains(self.client.get("/"), 'href="/about/"')
        settings = self.client.get(reverse("dash_settings"))
        self.assertNotContains(settings, "latitude")
        self.assertNotContains(settings, "longitude")

    @override_settings(
        EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
        EMAIL_HOST="smtp.test",
        EMAIL_HOST_USER="owner@example.test",
        EMAIL_HOST_PASSWORD="configured-for-test",
    )
    def test_checkout_emails_owner_and_does_not_redirect_to_whatsapp_by_default(self):
        site = SiteSettings.load()
        site.notification_email = "alerts@example.test"
        site.save(update_fields=["notification_email"])
        self.client.post(reverse("cart_add", args=[self.product.pk]))
        r = self.client.post(reverse("checkout"), {
            "name": "Ada", "email": "ada@example.test", "phone": "08099998888", "address": "PH",
        })
        order = Order.objects.get()
        self.assertRedirects(r, reverse("order_done_token", args=[order.public_token]))
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["alerts@example.test"])
        self.assertIn(f"New order #{order.pk}", mail.outbox[0].subject)
        self.assertIn("Aero Runner", mail.outbox[0].body)

    def test_order_redirects_to_whatsapp_only_when_owner_enables_it(self):
        site = SiteSettings.load()
        site.whatsapp_checkout = True
        site.save(update_fields=["whatsapp_checkout"])
        self.client.post(reverse("cart_add", args=[self.product.pk]))
        r = self.client.post(reverse("checkout"), {
            "name": "Ada", "email": "ada@example.test", "phone": "08099998888", "address": "PH",
        })
        self.assertEqual(r.status_code, 302)
        self.assertTrue(r["Location"].startswith("https://wa.me/2348012345678?text="))
        o = Order.objects.get()
        self.assertEqual(o.total, Decimal("15000"))
        self.assertEqual(o.lines.count(), 1)

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_example", PAYSTACK_MODE="test", PAYSTACK_CURRENCY="NGN")
    @patch("core.views.initialize_transaction", return_value="https://checkout.paystack.com/test")
    @patch("core.views.verify_transaction")
    def test_paystack_checkout_verifies_payment_and_issues_tickets_once(self, verify, initialize):
        event = Item.objects.create(kind="catalog", title="Live Show", price=Decimal("8000"), is_ticket=True)
        self.client.post(reverse("cart_add", args=[event.pk]), {"qty": "2"})
        response = self.client.post(reverse("checkout"), {
            "name": "Ada", "email": "ada@example.test", "phone": "08099998888",
        })
        order = Order.objects.get()
        attempt = PaymentAttempt.objects.get(order=order)
        self.assertRedirects(response, "https://checkout.paystack.com/test", fetch_redirect_response=False)
        initialize.assert_called_once()
        self.assertEqual(initialize.call_args.args[0], attempt.reference)
        self.assertEqual(initialize.call_args.args[1], "ada@example.test")
        self.assertEqual(initialize.call_args.args[2], Decimal("16000"))
        self.assertEqual(order.status, "new")
        self.assertEqual(Ticket.objects.count(), 0)
        response = self.client.post(reverse("retry_order_payment", args=[order.public_token]))
        self.assertRedirects(response, "https://checkout.paystack.com/test", fetch_redirect_response=False)
        self.assertEqual(initialize.call_count, 1)
        self.assertEqual(PaymentAttempt.objects.filter(order=order).count(), 1)

        verify.return_value = {
            "status": "success", "reference": attempt.reference,
            "currency": "NGN", "amount": 1_600_000,
        }
        response = self.client.get(reverse("paystack_return"), {"reference": attempt.reference})
        self.assertRedirects(response, reverse("order_done_token", args=[order.public_token]))
        order.refresh_from_db()
        attempt.refresh_from_db()
        self.assertEqual(order.status, "paid")
        self.assertEqual(attempt.status, "paid")
        self.assertEqual(Ticket.objects.count(), 2)

        payload = json.dumps({
            "event": "charge.success",
            "data": {"reference": attempt.reference},
        }).encode()
        signature = hmac.new(b"sk_test_example", payload, hashlib.sha512).hexdigest()
        response = self.client.post(
            reverse("paystack_webhook"), payload, content_type="application/json",
            HTTP_X_PAYSTACK_SIGNATURE=signature,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(Ticket.objects.count(), 2)

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_example", PAYSTACK_MODE="test", PAYSTACK_CURRENCY="NGN")
    @patch("core.views.verify_transaction")
    def test_paystack_does_not_confirm_amount_mismatch_or_invalid_webhook(self, verify):
        order = Order.objects.create(name="Ada", email="ada@example.test", phone="08099998888",
                                     total=Decimal("15000"), currency="₦")
        attempt = PaymentAttempt.objects.create(order=order, reference="test-reference")
        verify.return_value = {
            "status": "success", "reference": attempt.reference,
            "currency": "NGN", "amount": 1,
        }
        response = self.client.get(reverse("paystack_return"), {"reference": attempt.reference})
        self.assertRedirects(response, reverse("order_done_token", args=[order.public_token]))
        order.refresh_from_db()
        self.assertEqual(order.status, "new")

        response = self.client.post(
            reverse("paystack_webhook"), b'{"event":"charge.success"}',
            content_type="application/json", HTTP_X_PAYSTACK_SIGNATURE="invalid",
        )
        self.assertEqual(response.status_code, 400)

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_example", PAYSTACK_MODE="live", PAYSTACK_CURRENCY="NGN")
    def test_paystack_mode_must_match_secret_key_prefix(self):
        self.assertFalse(is_configured())
        with self.assertRaises(PaystackError):
            initialize_transaction("reference", "ada@example.test", Decimal("10"), "https://example.test/return/")

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_example", PAYSTACK_MODE="test", PAYSTACK_CURRENCY="NGN")
    @patch("core.payments._request_json")
    def test_paystack_initialization_uses_minor_units_and_trusted_checkout_host(self, request_json):
        request_json.return_value = {
            "authorization_url": "https://checkout.paystack.com/example",
            "reference": "reference",
        }
        url = initialize_transaction(
            "reference", "ada@example.test", Decimal("123.45"), "https://example.test/return/",
        )
        self.assertEqual(url, "https://checkout.paystack.com/example")
        self.assertEqual(request_json.call_args.args[0:2], ("POST", "/transaction/initialize"))
        self.assertEqual(request_json.call_args.args[2]["amount"], 12_345)
        self.assertEqual(request_json.call_args.args[2]["currency"], "NGN")
        self.assertEqual(request_json.call_args.args[2]["channels"], ["card", "bank_transfer"])

        request_json.return_value = {
            "authorization_url": "https://attacker.example/pay",
            "reference": "reference",
        }
        with self.assertRaises(PaystackError):
            initialize_transaction(
                "reference", "ada@example.test", Decimal("123.45"), "https://example.test/return/",
            )

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_header_example", PAYSTACK_MODE="test")
    @patch("core.payments.urlopen")
    def test_paystack_request_uses_bearer_secret_authorization(self, urlopen):
        response = urlopen.return_value.__enter__.return_value
        response.read.return_value = b'{"status":true,"data":{}}'

        _request_json("POST", "/transaction/initialize", {})

        request = urlopen.call_args.args[0]
        self.assertEqual(request.get_header("Authorization"), "Bearer sk_test_header_example")
        self.assertEqual(request.get_header("User-agent"), "EMFStore-Django/1.0")

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_sensitive_example", PAYSTACK_MODE="test", PAYSTACK_CURRENCY="NGN")
    @patch("core.payments.urlopen")
    def test_paystack_http_error_reports_provider_message_without_leaking_secret(self, urlopen):
        from urllib.error import HTTPError

        urlopen.side_effect = HTTPError(
            "https://api.paystack.co/transaction/initialize",
            403,
            "Forbidden",
            {},
            BytesIO(b'{"status":false,"message":"Access denied for sk_test_sensitive_example"}'),
        )
        with self.assertRaises(PaystackError) as raised:
            _request_json("POST", "/transaction/initialize", {})
        self.assertIn("HTTP 403", str(raised.exception))
        self.assertIn("[redacted]", str(raised.exception))
        self.assertNotIn("sk_test_sensitive_example", str(raised.exception))

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_sensitive_example", PAYSTACK_MODE="test")
    @patch("core.payments.urlopen")
    def test_paystack_http_error_finds_nested_reason_and_redacts_request_data(self, urlopen):
        from urllib.error import HTTPError

        urlopen.side_effect = HTTPError(
            "https://api.paystack.co/transaction/initialize",
            403,
            "Forbidden",
            {},
            BytesIO(
                b'{"status":false,"error":{"detail":"Denied for ada@example.test '
                b'with reference abc123 and sk_test_sensitive_example"}}'
            ),
        )
        with self.assertRaises(PaystackError) as raised:
            _request_json(
                "POST",
                "/transaction/initialize",
                {"email": "ada@example.test", "reference": "abc123"},
            )
        message = str(raised.exception)
        self.assertIn("Denied for [redacted] with reference [redacted]", message)
        self.assertNotIn("ada@example.test", message)
        self.assertNotIn("abc123", message)
        self.assertNotIn("sk_test_sensitive_example", message)

    @override_settings(PAYSTACK_SECRET_KEY="sk_test_sensitive_example", PAYSTACK_MODE="test")
    @patch("core.payments.urlopen")
    def test_paystack_http_error_reports_safe_metadata_when_provider_message_is_missing(self, urlopen):
        from email.message import Message
        from urllib.error import HTTPError

        headers = Message()
        headers["Content-Type"] = "text/html"
        headers["X-Request-Id"] = "req-123"
        urlopen.side_effect = HTTPError(
            "https://api.paystack.co/transaction/initialize",
            403,
            "Forbidden",
            headers,
            BytesIO(b"<html>blocked</html>"),
        )
        with self.assertRaises(PaystackError) as raised:
            _request_json("POST", "/transaction/initialize", {})
        self.assertIn("HTTP 403", str(raised.exception))
        self.assertIn("content type text/html", str(raised.exception))
        self.assertIn("body 20 bytes", str(raised.exception))
        self.assertIn("request ID req-123", str(raised.exception))
        self.assertNotIn("blocked", str(raised.exception))
        self.assertNotIn("sk_test_sensitive_example", str(raised.exception))

    def test_pages_render(self):
        for name in ("home", "contact", "cart", "login"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
        self.assertRedirects(self.client.get(reverse("about")), reverse("contact"), status_code=301)
        self.assertEqual(self.client.get("/catalog/").status_code, 200)
        self.assertEqual(self.client.get("/nope/").status_code, 404)

    def test_footer_shows_only_first_three_configured_social_links(self):
        site = SiteSettings.load()
        site.socials = [
            {"n": "instagram", "u": "https://instagram.com/example"},
            {"n": "tiktok", "u": "https://tiktok.com/@example"},
            {"n": "linkedin", "u": "https://linkedin.com/in/example"},
            {"n": "website", "u": "https://example.com"},
        ]
        site.save(update_fields=["socials"])
        response = self.client.get("/")
        self.assertContains(response, "https://instagram.com/example")
        self.assertContains(response, "https://tiktok.com/@example")
        self.assertContains(response, "https://linkedin.com/in/example")
        footer = response.content.split(b"<footer", 1)[1].split(b"</footer>", 1)[0]
        self.assertNotIn(b"https://example.com", footer)
        self.assertEqual(len(response.context["footer_socials"]), 3)

    def test_footer_hides_when_no_social_profiles_are_configured(self):
        site = SiteSettings.load()
        site.socials = [{"n": name, "u": ""} for name in SOCIAL_NAMES]
        site.save(update_fields=["socials"])
        response = self.client.get("/")
        self.assertNotContains(response, 'class="footer-socials"')

    def test_about_section_shows_configured_social_icons(self):
        site = SiteSettings.load()
        site.socials = [
            {"n": "instagram", "u": "https://instagram.com/example"},
            {"n": "linkedin", "u": "https://linkedin.com/in/example"},
            {"n": "tiktok", "u": ""},
        ]
        site.save(update_fields=["socials"])
        response = self.client.get(reverse("contact"))
        self.assertContains(response, '<nav class="about-socials" aria-label="Social profiles">')
        self.assertContains(response, 'href="https://instagram.com/example"')
        self.assertContains(response, 'aria-label="Instagram"')
        self.assertContains(response, 'href="https://linkedin.com/in/example"')
        self.assertNotContains(response, 'aria-label="TikTok"')

    def test_dashboard_requires_owner(self):
        self.assertEqual(self.client.get(reverse("dash")).status_code, 302)
        self.login()
        for name in ("dash", "dash_orders", "dash_messages", "dash_settings"):
            self.assertEqual(self.client.get(reverse(name)).status_code, 200)
