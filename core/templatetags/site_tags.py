import re
from decimal import Decimal

from django import template
from django.utils.html import format_html
from django.utils.safestring import mark_safe

register = template.Library()


def _ic(d, size=20):
    return mark_safe(
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{d}</svg>')


ICONS = {
    "bag": '<path d="M6 8h12l-1 12H7zM9 8a3 3 0 0 1 6 0"/>',
    "edit": '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L8 18l-4 1 1-4Z"/>',
    "user": '<circle cx="12" cy="8" r="4"/><path d="M4 21c1-4 4-6 8-6s7 2 8 6"/>',
    "menu": '<path d="M4 8h16M4 16h16"/>',
    "link": '<circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><path d="m8.7 10.5 6.6-4m-6.6 7.9 6.6 4"/>',
    "eye": '<path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    "close": '<path d="M6 6l12 12M18 6L6 18"/>',
    "instagram": '<rect x="3" y="3" width="18" height="18" rx="5"/><circle cx="12" cy="12" r="4"/><circle cx="17.2" cy="6.8" r=".6"/>',
    "x": '<path d="M4 4l16 16M20 4L4 20"/>',
    "youtube": '<rect x="2.5" y="5.5" width="19" height="13" rx="4"/><path d="M10 9.5v5l4.5-2.5z"/>',
    "spotify": '<circle cx="12" cy="12" r="9"/><path d="M7 9.5c3.5-1 7-.7 10 1M7.8 12.6c2.8-.8 5.6-.5 8 .8M8.6 15.4c2.1-.5 4.2-.3 6 .6"/>',
    "whatsapp": '<path d="M4 20l1.2-4A8 8 0 1 1 8 18.8z"/><path d="M9 9.5c.5 2.5 2.5 4.5 5.5 5.5"/>',
    "dribbble": '<circle cx="12" cy="12" r="9"/><path d="M7 4.5c4.5 4.3 7.7 9.6 9.4 15M3.5 10c5.4.2 10.9-1.4 14.8-4.5M4.6 17c3.5-3.8 9.1-5.8 15.7-4.4"/>',
    "website": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a15 15 0 0 1 0 18M12 3a15 15 0 0 0 0 18"/>',
}

SOCIAL_ICONS = {
    "tiktok": '<path d="M19.6 8.7a8.1 8.1 0 0 1-4.8-1.6v7.1a5.3 5.3 0 1 1-4.6-5.2v3.2a2.1 2.1 0 1 0 1.4 2V3h3.2c.2 2 1.7 3.8 4.8 4.1z"/>',
    "linkedin": '<path d="M5.2 8.8H2.4V21h2.8zM3.8 3a1.7 1.7 0 1 0 0 3.4 1.7 1.7 0 0 0 0-3.4M21.6 13.9c0-3.7-2-5.4-4.7-5.4a4 4 0 0 0-3.6 2v-1.7h-2.8V21h2.8v-6.1c0-1.6.3-3.2 2.4-3.2s2.2 1.9 2.2 3.3V21h2.8z"/>',
    "facebook": '<path d="M13.5 21v-8h2.7l.4-3h-3.1V8.1c0-.9.3-1.5 1.6-1.5h1.7V3.9c-.3 0-1.3-.1-2.5-.1-2.5 0-4.2 1.5-4.2 4.3V10H7.3v3h2.8v8z"/>',
    "threads": '<path d="M12 3.2c5 0 8.2 3.3 8.2 8.7 0 5.3-2.8 9-7.5 9-3.5 0-5.8-1.9-5.8-4.8 0-2.6 2-4.4 5-4.4 1.5 0 2.8.4 4 1.1-.3-2-1.4-3-3.4-3-1.4 0-2.5.5-3.3 1.5l-2-1.8c1.3-1.7 3.2-2.6 5.5-2.6 2 0 3.8.8 4.8 2.3-.8-3.2-2.7-4.8-5.7-4.8-2.3 0-4.1 1-5.4 2.9L4 5.7c1.8-1.7 4.3-2.5 8-2.5zm-.1 11.1c-1.4 0-2.3.6-2.3 1.7 0 1.1 1 1.8 2.7 1.8 1.2 0 2.2-.4 3-1.1-.8-1.6-2-2.4-3.4-2.4z"/>',
    "twitch": '<path d="M4 3h18v12l-5 5h-4l-3 3v-3H5V6zm3 3v11h5v2l2-2h3l3-3V6zm4 2h2v6h-2zm5 0h2v6h-2z"/>',
    "soundcloud": '<path d="M3 14.5c0-1 .4-1.8 1.1-2.4l.2-1.6c.1-.5.8-.5.9 0l.2 1.2c.3-.1.6-.2.9-.2l.3-2.2c.1-.5.8-.5.9 0l.3 2.3c.4.2.7.5.9.9.5-3.2 3.2-5.5 6.4-5.5 3.5 0 6.3 2.8 6.3 6.3s-2.8 6.3-6.3 6.3H6.1A3.1 3.1 0 0 1 3 16.5z"/>',
    "apple_music": '<path d="M17 3.2v13.2a3.1 3.1 0 1 1-2-2.9V7.2l-7 1.5v9a3.1 3.1 0 1 1-2-2.9V6.9z"/>',
    "bandcamp": '<path d="M7.5 5h7.8c3.4 0 5.7 2.1 5.7 5s-2.3 5-5.7 5H7.5zm0 7h7.8c3.4 0 5.7 2.1 5.7 5s-2.3 5-5.7 5H7.5z"/>',
    "pinterest": '<path d="M12 2a10 10 0 0 0-3.6 19.3c0-.8 0-1.8.2-2.7l1.3-5.6s-.3-.6-.3-1.5c0-1.4.8-2.4 1.8-2.4.8 0 1.2.6 1.2 1.4 0 .9-.6 2.3-.9 3.6-.3 1.1.5 2 1.6 2 1.9 0 3.2-2.5 3.2-5.4 0-2.2-1.5-3.9-4.2-3.9-3.1 0-5 2.3-5 4.9 0 .9.3 1.6.7 2.1.2.2.2.3.1.6l-.2.8c-.1.3-.3.4-.6.3-1.3-.5-1.9-2-1.9-3.6 0-2.7 2.3-5.9 6.9-5.9 3.7 0 6.1 2.7 6.1 5.6 0 3.8-2.1 6.6-5.2 6.6-1 0-2-.6-2.3-1.2l-.7 2.8c-.2 1-.7 1.9-1.1 2.6A10 10 0 1 0 12 2z"/>',
    "snapchat": '<path d="M12 2.5c-2.4 0-4 1.8-4 4.5 0 .8.1 1.5.2 2.1-1-.2-1.8-.8-2.2-1.2-.4-.4-1-.4-1.4 0-.4.4-.4 1 0 1.4.8.9 2 1.5 3.2 1.7-.5 1.7-1.6 3.1-3.2 4.1l-1.8 1c-.6.3-.7 1.1-.2 1.6.8.7 2 1 3.2 1.1.7.1 1.2.4 1.6.9.8 1 2.1 1.5 4.6 1.5s3.8-.5 4.6-1.5c.4-.5.9-.8 1.6-.9 1.2-.1 2.4-.4 3.2-1.1.5-.5.4-1.3-.2-1.6l-1.8-1c-1.6-1-2.7-2.4-3.2-4.1 1.2-.2 2.4-.8 3.2-1.7.4-.4.4-1 0-1.4-.4-.4-1-.4-1.4 0-.4.4-1.2 1-2.2 1.2.1-.6.2-1.3.2-2.1 0-2.7-1.6-4.5-4-4.5z"/>',
    "telegram": '<path d="m21.8 4.5-3.2 15.1c-.2 1.1-.8 1.4-1.7.9l-4.7-3.5-2.3 2.2c-.3.3-.5.5-1 .5l.4-4.8 8.8-8c.4-.4-.1-.6-.6-.2L6.6 13.7 2 12.3c-1-.3-1-1 .2-1.5l18-6.9c.8-.3 1.5.2 1.3.6z"/>',
    "discord": '<path d="M19.7 5.2A18 18 0 0 0 15.4 4l-.5 1a16 16 0 0 0-5.8 0l-.5-1a18 18 0 0 0-4.3 1.2C1.6 9.2.8 13.1 1.2 17c1.8 1.4 3.6 2.2 5.4 2.7l1.2-2a11 11 0 0 1-1.9-.9l.5-.4c3.7 1.7 7.7 1.7 11.3 0l.6.4c-.6.4-1.2.7-1.9.9l1.2 2c1.8-.5 3.6-1.3 5.4-2.7.5-4.5-.8-8.3-3.3-11.8zM8.8 14.6c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2zm6.4 0c-1 0-1.8-.9-1.8-2s.8-2 1.8-2 1.8.9 1.8 2-.8 2-1.8 2z"/>',
    "github": '<path d="M12 2a10 10 0 0 0-3.2 19.5c.5.1.7-.2.7-.5v-1.8c-2.8.6-3.4-1.2-3.4-1.2-.5-1.1-1.1-1.4-1.1-1.4-.9-.6.1-.6.1-.6 1 .1 1.5 1 1.5 1 .9 1.5 2.3 1.1 2.9.8.1-.6.4-1.1.6-1.3-2.2-.3-4.6-1.1-4.6-5a3.9 3.9 0 0 1 1-2.7c-.1-.3-.4-1.3.1-2.7 0 0 .8-.3 2.8 1a9.7 9.7 0 0 1 5.1 0c2-1.3 2.8-1 2.8-1 .5 1.4.2 2.4.1 2.7a3.9 3.9 0 0 1 1 2.7c0 3.9-2.4 4.7-4.6 5 .4.3.7.9.7 1.8V21c0 .3.2.6.7.5A10 10 0 0 0 12 2z"/>',
    "behance": '<path d="M3 4h8c3 0 4.7 1.5 4.7 4 0 1.5-.7 2.5-1.8 3.1 1.7.5 2.6 1.8 2.6 3.7 0 3-2.1 5.2-5.7 5.2H3zm4 3v3h3.4c1 0 1.5-.5 1.5-1.5S11.4 7 10.4 7zm0 6v4h3.8c1.2 0 1.8-.7 1.8-2s-.6-2-1.8-2zM17 5h5v2h-5zm5.2 10h-6.5c.1 1.5.8 2.3 2.1 2.3.8 0 1.5-.4 1.7-1h2.5c-.6 2.4-2.2 3.6-4.4 3.6-3 0-4.8-2-4.8-5s1.9-5 4.8-5c3.2 0 4.8 2.1 4.6 5.1zm-6.4-1.8h3.8c-.1-1.1-.7-1.7-1.8-1.7-1.2 0-1.8.6-2 1.7z"/>',
    "medium": '<path d="M3 6.2c0-.3-.1-.5-.3-.7L1 3.4V3h6.2l4.8 10.5L16.2 3H22v.4l-1.5 1.4c-.1.1-.2.3-.2.5v13.4c0 .2.1.4.2.5l1.5 1.4v.4h-7.5v-.4l1.6-1.4c.2-.2.2-.2.2-.5V7.9l-4.5 13h-.6L6 7.9v8.7c-.1.4.1.8.4 1.1l2.1 2.5v.4H2.4v-.4l2.1-2.5c.3-.3.4-.7.3-1.1z"/>',
    "vimeo": '<path d="M22 7.2c-.1 3-2.2 7.1-6.2 12.3-2.1 2.8-4 4.2-5.5 4.2-.9 0-1.7-.8-2.4-2.5L5.5 14c-.9-3.3-1.8-4.9-2.8-4.9-.2 0-.8.4-1.8 1.2L0 8.8l3.5-3.1C5 4.4 6.1 3.7 6.8 3.6c1.8-.2 2.9 1 3.3 3.5.5 2.7.8 4.4 1 5.1.5 2.2 1 3.3 1.6 3.3.4 0 1.1-.7 2-2.1s1.4-2.4 1.5-3.1c.1-1.2-.4-1.8-1.5-1.8-.5 0-1 .1-1.5.4 1-3.2 2.9-4.8 5.7-4.7 2.1 0 3.1 1.4 3.1 4.1z"/>',
    "reddit": '<path d="M12 2a2 2 0 0 0-1.9 2.7 12 12 0 0 0-5.4 2.1 1.8 1.8 0 1 0-1.2 3.2 5 5 0 0 0-.5 2.2c0 3.7 4 6.7 9 6.7s9-3 9-6.7a5 5 0 0 0-.5-2.2 1.8 1.8 0 1 0-1.2-3.2 12 12 0 0 0-5.4-2.1l.8-3.1 2.6.6a1.5 1.5 0 1 0 .3-1.3l-3.2-.7a.7.7 0 0 0-.8.5l-.9 3.8a12 12 0 0 0-.8 0 12 12 0 0 0-.8 0A2 2 0 0 0 12 2zm-3.2 9a1.3 1.3 0 1 1 0 2.6 1.3 1.3 0 0 1 0-2.6zm6.4 0a1.3 1.3 0 1 1 0 2.6 1.3 1.3 0 0 1 0-2.6zm-6.5 4.1c1.7 1.3 4.9 1.3 6.6 0l.8.9c-2.2 1.9-6 1.9-8.2 0z"/>',
    "mastodon": '<path d="M20.5 5.4c-1.3-1-3.4-1.4-5.8-1.4h-5.4c-2.4 0-4.5.4-5.8 1.4C2 6.6 1.7 8.5 1.7 11v4.2c0 4.8 3.1 6.1 6.7 6.5 1.7.2 3.3.1 4.6-.1l-.1-2.7c-1.3.4-2.7.4-4 .2-1.4-.2-2.1-1-2.2-2.1 2.4.6 4.6.8 6.8.8 4.1 0 7.1-1 7.8-5.4.2-1.4.3-3 .3-4.2 0-2.5-.4-4.4-1.1-5.8zm-3.5 9.3h-3v-5c0-1.1-.5-1.7-1.4-1.7-1 0-1.6.7-1.6 2.1v2.7H8v-2.7c0-1.4-.5-2.1-1.6-2.1-.9 0-1.4.6-1.4 1.7v5H2V9.5c0-1.1.3-2 .9-2.6.6-.6 1.4-.9 2.4-.9 1.2 0 2.2.5 2.8 1.5l.6 1 .6-1c.6-1 1.6-1.5 2.8-1.5 1 0 1.8.3 2.4.9.6.6.9 1.5.9 2.6z"/>',
    "bluesky": '<path d="M12 11.1c-1.1-2.1-4.2-6.1-7-8C3.1 1.8 2.4 2 1.9 2.2.9 2.6.7 4.2.7 5.1c0 .9.5 7.2.8 8.3.9 3.5 4.1 4.7 7.1 4.2-5.2.9-9.8 3.2-3.7 8.7 6.8 5.9 6.8-1.3 7.1-3.2.1-.3.1-.5.2-.7.1.2.1.4.2.7.3 1.9.3 9.1 7.1 3.2 6.1-5.5 1.5-7.8-3.7-8.7 3 .5 6.2-.7 7.1-4.2.3-1.1.8-7.4.8-8.3 0-.9-.2-2.5-1.2-2.9-.5-.2-1.2-.4-3.1.9-2.8 1.9-5.9 5.9-7 8z" transform="translate(0 -1) scale(1 .82)"/>',
}


@register.simple_tag
def icon(name, size=20):
    if name in SOCIAL_ICONS:
        return mark_safe(
            f'<svg class="brand-icon brand-icon-{name}" width="{size}" height="{size}" '
            f'viewBox="0 0 24 24" fill="currentColor" aria-hidden="true">{SOCIAL_ICONS[name]}</svg>')
    return _ic(ICONS.get(name, ""), size)


@register.simple_tag(takes_context=True)
def t(context, key, default="", tag="span", cls=""):
    """Editable text. Shows the owner's saved text, or the default."""
    saved = context["site"].texts.get(key)
    text = default if saved is None else saved
    return format_html('<{} class="{}" data-key="{}">{}</{}>', tag, cls, key, text, tag)


@register.simple_tag(takes_context=True)
def visible(context, key):
    return context["site"].vis.get(key, True)


@register.simple_tag(takes_context=True)
def offcls(context, key):
    return "" if context["site"].vis.get(key, True) else " off"


class VisNode(template.Node):
    def __init__(self, nodelist, key, cls):
        self.nodelist, self.key, self.cls = nodelist, key, cls

    def render(self, context):
        key = self.key.resolve(context)
        cls = self.cls.resolve(context) if self.cls else ""
        on = context["site"].vis.get(key, True)
        if not on and not context.get("edit"):
            return ""
        inner = self.nodelist.render(context)
        return format_html('<div class="{}{}" data-vis="{}">{}</div>', cls, "" if on else " off", key, mark_safe(inner))


@register.tag("vis")
def do_vis(parser, token):
    """{% vis 'key' 'optional-class' %} ... {% endvis %}: element with an on/off switch."""
    bits = token.split_contents()[1:]
    nodelist = parser.parse(("endvis",))
    parser.delete_first_token()
    return VisNode(nodelist, parser.compile_filter(bits[0]), parser.compile_filter(bits[1]) if len(bits) > 1 else None)


@register.simple_tag
def art(h):
    h = int(h or 0)
    return mark_safe(
        f"background:radial-gradient(70% 90% at 12% 8%,hsl({h} 95% 68%),transparent 62%),"
        f"radial-gradient(60% 70% at 92% 18%,hsl({(h + 70) % 360} 90% 60%),transparent 62%),"
        f"radial-gradient(90% 80% at 50% 115%,hsl({(h + 300) % 360} 85% 48%),transparent 62%),hsl({h} 45% 14%)")


@register.simple_tag
def crop(item):
    fp = (item.crop or "").strip()
    pos, _, z = fp.partition("|")
    if not re.fullmatch(r"\d{1,3}% \d{1,3}%", pos):
        return ""
    if not re.fullmatch(r"\d(\.\d+)?", z or "1"):
        z = "1"
    return format_html(' style="object-position:{};transform-origin:{};--z:{}"', pos, pos, z or "1")


@register.filter
def money(value, currency="₦"):
    try:
        v = Decimal(value)
    except Exception:
        return ""
    s = f"{int(v):,}" if v == v.to_integral_value() else f"{v:,.2f}"
    return f"{currency}{s}"


@register.filter
def get(d, key):
    try:
        return d.get(key, "")
    except AttributeError:
        return ""
