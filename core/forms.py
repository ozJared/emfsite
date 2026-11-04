from django import forms
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import UploadedFile

from .models import HERO_MODES, THEMES, Item, Order
from .presets import SOCIAL_LABELS, SOCIAL_NAMES
from .spotify_embed import fetch_track_metadata
from .utils import digits, normalize_whatsapp, process_image


class ItemForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = ["title", "date", "summary", "body", "price", "link", "is_ticket", "image", "crop", "is_published"]
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d"),
            "body": forms.Textarea(attrs={"rows": 10}),
            "price": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }

    def __init__(self, *a, kind="catalog", **k):
        super().__init__(*a, **k)
        self.kind = kind
        self._thumb = None
        if kind != "catalog":
            for f in ("price", "link", "is_ticket", "crop"):
                del self.fields[f]
        else:
            self.fields["title"].required = False
            self.fields["price"].label = "Price (leave 0 for a release or service)"
            self.fields["date"].help_text = "For event tickets, this date is shown on the ticket."
            self.fields["spotify_embed"] = forms.CharField(
                label="Spotify track or embed code",
                required=False,
                initial=self.instance.link if self.instance and self.instance.spotify_id else "",
                widget=forms.Textarea(attrs={
                    "rows": 3,
                    "placeholder": "Paste a Spotify track URL or its <iframe> embed code",
                }),
                help_text="Fetches the track title and cover art from Spotify without API credentials.",
            )
            self.order = [
                "title",
                "spotify_embed",
                *(field for field in self.fields if field not in {"title", "spotify_embed"}),
            ]

    def clean_image(self):
        img = self.cleaned_data.get("image")
        if isinstance(img, UploadedFile):
            main, thumb = process_image(img)
            self._thumb = thumb
            return main
        return img

    def clean(self):
        cleaned = super().clean()
        if self.kind == "catalog":
            embed_input = cleaned.get("spotify_embed", "").strip()
            if embed_input:
                try:
                    track = fetch_track_metadata(embed_input)
                except ValidationError as exc:
                    self.add_error("spotify_embed", exc)
                else:
                    cleaned["link"] = track["url"]
                    cleaned["spotify_id"] = track["id"]
                    cleaned["spotify_image_url"] = track["image_url"]
                    if not cleaned.get("title"):
                        cleaned["title"] = track["title"]
            else:
                cleaned["spotify_id"] = ""
                cleaned["spotify_image_url"] = ""
            if not cleaned.get("title"):
                self.add_error("title", "Enter a title or provide a Spotify track link.")
        if cleaned.get("is_ticket") and cleaned.get("price", 0) <= 0:
            self.add_error("price", "Set a price to sell event tickets.")
        return cleaned

    def save(self, commit=True):
        inst = super().save(commit=False)
        if self.kind == "catalog":
            inst.spotify_id = self.cleaned_data.get("spotify_id", "")
            inst.spotify_image_url = self.cleaned_data.get("spotify_image_url", "")
        if self._thumb:
            inst.thumb = self._thumb
        if not inst.image:
            inst.thumb = ""
        if commit:
            inst.save()
        return inst


class SettingsForm(forms.Form):
    name = forms.CharField(label="Site name", max_length=120)
    ghost = forms.CharField(label="Big background word", max_length=8)
    tagline = forms.CharField(max_length=120)
    blurb = forms.CharField(max_length=240)
    cta = forms.CharField(label="Main button text", max_length=40)
    whatsapp_number = forms.CharField(
        label="Owner WhatsApp number", max_length=20, required=False,
        help_text="With country code, e.g. 2348012345678. A Nigerian number like 08012345678 also works.")
    whatsapp_checkout = forms.BooleanField(
        label="Use WhatsApp enquiry instead of checkout", required=False,
        help_text="Off by default: buyers submit an order and see its confirmation page.")
    notification_email = forms.EmailField(
        label="Order and contact notification email", required=False,
        help_text="New orders and contact messages are emailed here. SMTP must be configured in .env.")
    business_address = forms.CharField(
        label="Business address", max_length=300, required=False,
        help_text="Shown on Contact with an embedded Google Maps location.")
    show_map = forms.BooleanField(
        label="Display location map", required=False,
        help_text="Show or hide the map on your Contact page.")
    currency = forms.CharField(max_length=4)
    theme = forms.ChoiceField(choices=THEMES)
    hero_mode = forms.ChoiceField(label="Hero image style", choices=HERO_MODES)
    fx = forms.IntegerField(label="Focus left to right", min_value=0, max_value=100, widget=forms.NumberInput(attrs={"type": "range"}))
    fy = forms.IntegerField(label="Focus up and down", min_value=0, max_value=100, widget=forms.NumberInput(attrs={"type": "range"}))
    meta_description = forms.CharField(label="Search engine description", max_length=300, required=False)
    hero_image = forms.ImageField(required=False)
    about_image = forms.ImageField(required=False)
    contact_image = forms.ImageField(required=False)
    lab_catalog = forms.CharField(label="Name for the catalog section", max_length=30)
    lab_blog = forms.CharField(label="Name for the blog section", max_length=30)
    lab_news = forms.CharField(label="Name for the news section", max_length=30)

    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        for n in SOCIAL_NAMES:
            if n != "whatsapp":
                self.fields["soc_" + n] = forms.URLField(label=f"{SOCIAL_LABELS[n]} link", required=False)

    @classmethod
    def initial_for(cls, s):
        d = {f: getattr(s, f) for f in ("name", "ghost", "tagline", "blurb", "cta", "whatsapp_number",
                                       "whatsapp_checkout", "currency",
                                       "theme", "hero_mode", "fx", "fy", "meta_description",
                                       "notification_email", "business_address", "show_map",
                                       "contact_image")}
        d.update(lab_catalog=s.label("catalog"), lab_blog=s.label("blog"), lab_news=s.label("news"))
        for x in s.socials:
            d["soc_" + x["n"]] = x.get("u", "")
        return d

    def clean_whatsapp_number(self):
        raw = self.cleaned_data.get("whatsapp_number", "")
        if not raw:
            return ""
        d = normalize_whatsapp(raw)
        if not 8 <= len(d) <= 15:
            raise ValidationError("Enter a full number with country code, for example 2348012345678.")
        return d

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("whatsapp_checkout") and not cleaned.get("whatsapp_number"):
            self.add_error("whatsapp_number", "Enter an owner WhatsApp number to use WhatsApp enquiries.")
        return cleaned

    def clean_hero_image(self):
        return self._img("hero_image")

    def clean_about_image(self):
        return self._img("about_image")

    def clean_contact_image(self):
        return self._img("contact_image")

    def _img(self, name):
        f = self.cleaned_data.get(name)
        return process_image(f, want_thumb=False)[0] if isinstance(f, UploadedFile) else None

    def apply(self, s):
        c = self.cleaned_data
        for f in ("name", "ghost", "tagline", "blurb", "cta", "whatsapp_number", "whatsapp_checkout",
                  "currency", "theme", "hero_mode", "fx", "fy", "meta_description", "show_map",
                  "notification_email", "business_address"):
            setattr(s, f, c[f])
        if c.get("hero_image"):
            s.hero_image = c["hero_image"]
        if c.get("about_image"):
            s.about_image = c["about_image"]
        if c.get("contact_image"):
            s.contact_image = c["contact_image"]
        s.labels = {"catalog": c["lab_catalog"], "blog": c["lab_blog"], "news": c["lab_news"]}
        socials = {x["n"]: x for x in s.socials}
        for n in SOCIAL_NAMES:
            if n != "whatsapp":
                socials.setdefault(n, {"n": n, "u": ""})["u"] = c.get("soc_" + n, "")
        s.socials = [socials.get(n, {"n": n, "u": ""}) for n in SOCIAL_NAMES]
        s.save()


class OwnerProfileForm(forms.Form):
    whatsapp_number = forms.CharField(
        label="Owner WhatsApp number", max_length=20, required=False,
        help_text="With country code, e.g. 2348012345678.")
    notification_email = forms.EmailField(
        label="Order and contact notification email", required=False)
    business_address = forms.CharField(
        label="Business address", max_length=300, required=False)
    show_map = forms.BooleanField(
        label="Display location map", required=False,
        help_text="Show or hide the map on your Contact page.")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in SOCIAL_NAMES:
            if name != "whatsapp":
                self.fields["soc_" + name] = forms.URLField(
                    label=f"{SOCIAL_LABELS[name]} link", required=False)

    @classmethod
    def initial_for(cls, site):
        data = {
            name: getattr(site, name)
            for name in ("whatsapp_number", "notification_email", "business_address", "show_map")
        }
        data.update({f"soc_{social['n']}": social.get("u", "") for social in site.socials})
        return data

    def clean_whatsapp_number(self):
        raw = self.cleaned_data.get("whatsapp_number", "")
        if not raw:
            return ""
        number = normalize_whatsapp(raw)
        if not 8 <= len(number) <= 15:
            raise ValidationError("Enter a full number with country code, for example 2348012345678.")
        return number

    def apply(self, site):
        for field in ("whatsapp_number", "notification_email", "business_address", "show_map"):
            setattr(site, field, self.cleaned_data[field])
        socials = {social["n"]: social for social in site.socials}
        for name in SOCIAL_NAMES:
            if name != "whatsapp":
                socials.setdefault(name, {"n": name, "u": ""})["u"] = self.cleaned_data.get(f"soc_{name}", "")
        site.socials = [socials.get(name, {"n": name, "u": ""}) for name in SOCIAL_NAMES]
        site.save()


class CheckoutForm(forms.Form):
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"placeholder": "Full name", "autocomplete": "name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "Email for payment receipt", "autocomplete": "email"}))
    phone = forms.CharField(max_length=30, widget=forms.TextInput(attrs={"placeholder": "Phone or WhatsApp", "autocomplete": "tel"}))
    address = forms.CharField(required=False, max_length=500, widget=forms.Textarea(attrs={"rows": 3, "placeholder": "Delivery address (if needed)"}))
    note = forms.CharField(required=False, max_length=300, widget=forms.TextInput(attrs={"placeholder": "Note (size, colour, anything else)"}))

    def clean_phone(self):
        p = self.cleaned_data["phone"]
        if len(digits(p)) < 7:
            raise ValidationError("Enter a valid phone number.")
        return p


class ContactForm(forms.Form):
    name = forms.CharField(max_length=120, widget=forms.TextInput(attrs={"placeholder": "Your name"}))
    email = forms.EmailField(widget=forms.EmailInput(attrs={"placeholder": "Email"}))
    body = forms.CharField(max_length=3000, widget=forms.Textarea(attrs={"rows": 4, "placeholder": "Message"}))
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))  # honeypot


class OrderStatusForm(forms.ModelForm):
    class Meta:
        model = Order
        fields = ["status"]
