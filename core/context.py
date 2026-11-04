from urllib.parse import urlencode

from django.urls import reverse

from .models import SITE_TYPES, THEMES, Item
from .presets import KINDS, SOCIAL_LABELS, SOCIAL_NAMES

def site(request):
    s = request.site
    path = request.path
    nav = [(reverse("home"), "Home", path == "/", "nav.home")]
    for k in KINDS:
        if s.is_on(k):
            url = reverse("list", args=[k])
            nav.append((url, s.label(k), path.startswith(url) or path.startswith(url.rstrip("/") + "/"), f"nav.{k}"))
    for sid, label, name in (("features", "Services", "features"), ("contact", "Contact", "contact")):
        if s.is_on(sid):
            url = reverse(name)
            nav.append((url, label, path == url, f"nav.{sid}"))
    configured = {x["n"]: x.get("u", "") for x in s.socials}
    if s.wa_digits:
        configured["whatsapp"] = f"https://wa.me/{s.wa_digits}"
    active_socials = [(index, name, configured[name]) for index, name in enumerate(SOCIAL_NAMES) if configured.get(name)]
    footer_configured = {x["n"]: x.get("u", "") for x in s.socials}
    footer_socials = [
        {"label": SOCIAL_LABELS[name], "url": footer_configured[name]}
        for name in SOCIAL_NAMES if footer_configured.get(name)
    ][:3]
    socs = []
    for index, name, url in active_socials:
        socs.append({
            "n": name,
            "label": SOCIAL_LABELS[name],
            "u": url,
            "key": f"social.{name}",
            "i": index,
        })
    cart = request.session.get("cart", {})
    og = ""
    if s.hero_image:
        og = request.build_absolute_uri(s.hero_image.url)
    map_link = map_embed_url = ""
    if s.business_address:
        map_link = "https://www.google.com/maps/search/?" + urlencode({"api": "1", "query": s.business_address})
        map_embed_url = "https://maps.google.com/maps?" + urlencode({
            "q": s.business_address, "z": 15, "output": "embed",
        })
    return {
        "site": s, "edit": request.edit, "is_owner": request.is_owner,
        "is_platform_admin": request.is_platform_admin, "nav": nav, "socs": socs,
        "cart_count": sum(cart.values()) if cart else 0,
        "has_shop": Item.objects.filter(kind="catalog", price__gt=0, is_published=True).exists(),
        "labels": {k: s.label(k) for k in KINDS}, "og_image": og, "kinds": KINDS,
        "marquee": s.texts.get("marq.text") or f"{s.name} • {s.tagline} • {s.name} • {s.tagline}",
        "map_link": map_link, "map_embed_url": map_embed_url, "footer_socials": footer_socials,
        "spotify_profile": s.spotify_profile,
        "on": {x["id"]: x["on"] for x in s.section_list()}, "section_list": s.section_list(),
        "site_types": SITE_TYPES, "themes": THEMES,
    }
