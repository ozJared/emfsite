import json
import re
from html.parser import HTMLParser
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from django.core.exceptions import ValidationError


TRACK_ID = re.compile(r"^[A-Za-z0-9]{22}$")
SPOTIFY_HOSTS = {"open.spotify.com", "www.open.spotify.com"}


class _IframeSourceParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.src = ""

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "iframe":
            self.src = dict(attrs).get("src", "")


def _track_url(value):
    value = value.strip()
    if "<" in value or ">" in value:
        parser = _IframeSourceParser()
        try:
            parser.feed(value)
        except ValueError as exc:
            raise ValidationError("Paste a Spotify track link or embed code.") from exc
        value = parser.src

    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.hostname not in SPOTIFY_HOSTS:
        raise ValidationError("Paste a Spotify track link or Spotify iframe embed code.")
    parts = [part for part in parsed.path.split("/") if part]
    if parts and re.fullmatch(r"intl-[a-z]{2}", parts[0], re.IGNORECASE):
        parts = parts[1:]
    if len(parts) == 3 and parts[0] == "embed":
        parts = parts[1:]
    if len(parts) != 2 or parts[0] != "track" or not TRACK_ID.fullmatch(parts[1]):
        raise ValidationError("That Spotify link must point to a track.")
    track_id = parts[1]
    return track_id, f"https://open.spotify.com/track/{track_id}"


def _valid_thumbnail(value):
    parsed = urlparse(value)
    host = parsed.hostname or ""
    return (
        parsed.scheme == "https"
        and (host.endswith(".scdn.co") or host.endswith(".spotifycdn.com"))
    )


def fetch_track_metadata(embed_input):
    track_id, track_url = _track_url(embed_input)
    request = Request(
        "https://open.spotify.com/oembed?url=" + quote(track_url, safe=""),
        headers={
            "Accept": "application/json",
            "User-Agent": "PremiumEMF/1.0 (Spotify track metadata lookup)",
        },
    )
    try:
        with urlopen(request, timeout=8) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        raise ValidationError(
            f"Spotify could not load track details (HTTP {exc.code}). "
            "You can retry or add the release details manually."
        ) from exc
    except (URLError, TimeoutError, OSError) as exc:
        raise ValidationError(
            "Could not reach Spotify for track details. You can retry or add the release details manually."
        ) from exc
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValidationError("Spotify returned invalid track details. Please try again.") from exc

    if not isinstance(payload, dict) or not isinstance(payload.get("title"), str) or not payload["title"].strip():
        raise ValidationError("Spotify did not provide a track title. Add the release details manually.")
    image_url = payload.get("thumbnail_url", "")
    if not isinstance(image_url, str) or not _valid_thumbnail(image_url):
        image_url = ""
    return {
        "id": track_id,
        "url": track_url,
        "title": payload["title"].strip()[:160],
        "image_url": image_url,
    }
