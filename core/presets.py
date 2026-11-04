"""Site-type presets. Switching a preset changes look, labels and which sections are on.
It never deletes items, orders, messages or images."""

SECTION_IDS = ["hero", "catalog", "blog", "news", "features", "contact"]
KINDS = ["catalog", "blog", "news"]
SOCIAL_NAMES = [
    "instagram", "tiktok", "linkedin", "facebook", "x", "youtube", "spotify",
    "whatsapp", "threads", "twitch", "soundcloud", "apple_music", "bandcamp",
    "pinterest", "snapchat", "telegram", "discord", "github", "behance",
    "dribbble", "medium", "vimeo", "reddit", "mastodon", "bluesky", "website",
]
SOCIAL_LABELS = {
    "instagram": "Instagram",
    "tiktok": "TikTok",
    "linkedin": "LinkedIn",
    "facebook": "Facebook",
    "x": "X",
    "youtube": "YouTube",
    "spotify": "Spotify",
    "whatsapp": "WhatsApp",
    "threads": "Threads",
    "twitch": "Twitch",
    "soundcloud": "SoundCloud",
    "apple_music": "Apple Music",
    "bandcamp": "Bandcamp",
    "pinterest": "Pinterest",
    "snapchat": "Snapchat",
    "telegram": "Telegram",
    "discord": "Discord",
    "github": "GitHub",
    "behance": "Behance",
    "dribbble": "Dribbble",
    "medium": "Medium",
    "vimeo": "Vimeo",
    "reddit": "Reddit",
    "mastodon": "Mastodon",
    "bluesky": "Bluesky",
    "website": "Website",
}

PRESETS = {
    "artist": dict(
        theme="noir", ghost="EMF", tagline="Artist · Musician", blurb="New music, shows and stories.",
        cta="Listen now", labels={"catalog": "Releases", "blog": "Stories", "news": "News"},
        on=["hero", "catalog", "news", "contact"]),
    "portfolio": dict(
        theme="blush", ghost="YOU", tagline="Designer · Developer", blurb="Selected work and thinking.",
        cta="View work", labels={"catalog": "Work", "blog": "Journal", "news": "News"},
        on=["hero", "catalog", "blog", "contact"]),
    "company": dict(
        theme="sky", ghost="CO", tagline="Built for what’s next", blurb="We help teams ship great things.",
        cta="Talk to us", labels={"catalog": "Services", "blog": "Insights", "news": "News"},
        on=["hero", "features", "news", "contact"]),
    "store": dict(
        theme="neon", ghost="SHOP", tagline="The new drop is live", blurb="Small batch, big attitude.",
        cta="Shop now", labels={"catalog": "Shop", "blog": "Journal", "news": "News"},
        on=["hero", "catalog", "blog", "contact"]),
}
PRESET_TEXT_KEYS = ["hero.s", "hero.p", "hero.c", "catalog.t", "blog.t", "news.t"]


def default_labels():
    return dict(PRESETS["artist"]["labels"])


def default_sections():
    return [{"id": i, "on": i in PRESETS["artist"]["on"]} for i in SECTION_IDS]


def default_socials():
    return [{"n": n, "u": ""} for n in SOCIAL_NAMES]


def default_dict():
    return {}
