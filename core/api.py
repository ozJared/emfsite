"""Edit-mode endpoints. Every one requires a logged-in owner, a POST and a CSRF token."""
import json
import re
from functools import wraps

from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import JsonResponse
from django.views.decorators.http import require_POST

from .dash import apply_preset_to
from .models import THEMES, Item
from .presets import PRESETS, SECTION_IDS
from .utils import process_image

KEY = re.compile(r"^[a-z0-9._-]{1,60}$")


def owner_api(fn):
    @wraps(fn)
    @require_POST
    def inner(request, *a, **k):
        if not request.is_owner:
            return JsonResponse({"ok": False, "error": "Log in as the owner."}, status=403)
        try:
            data = json.loads(request.body) if request.content_type == "application/json" and request.body else {}
        except ValueError:
            return JsonResponse({"ok": False, "error": "Bad request."}, status=400)
        return fn(request, data, *a, **k)
    return inner


def platform_admin_api(fn):
    @wraps(fn)
    @require_POST
    def inner(request, *args, **kwargs):
        if not request.is_platform_admin:
            return JsonResponse({"ok": False, "error": "Only the platform superuser can change site design."}, status=403)
        return fn(request, *args, **kwargs)
    return inner


@platform_admin_api
@owner_api
def text(request, d):
    key, val = d.get("key", ""), str(d.get("value", ""))[:2000].strip()
    if not KEY.match(key):
        return JsonResponse({"ok": False, "error": "Bad key."}, status=400)
    s = request.site
    s.texts[key] = val
    s.save(update_fields=["texts"])
    return JsonResponse({"ok": True})


@platform_admin_api
@owner_api
def vis(request, d):
    key = d.get("key", "")
    if not KEY.match(key):
        return JsonResponse({"ok": False, "error": "Bad key."}, status=400)
    s = request.site
    s.vis[key] = bool(d.get("visible"))
    s.save(update_fields=["vis"])
    return JsonResponse({"ok": True, "visible": s.vis[key]})


@platform_admin_api
@owner_api
def section(request, d):
    s, sid, act = request.site, d.get("id"), d.get("action")
    secs = s.section_list()
    idx = next((i for i, x in enumerate(secs) if x["id"] == sid), None)
    if idx is None or act not in ("up", "down", "toggle"):
        return JsonResponse({"ok": False, "error": "Bad request."}, status=400)
    if act == "toggle":
        secs[idx]["on"] = not secs[idx]["on"]
    else:
        j = idx + (-1 if act == "up" else 1)
        if 0 <= j < len(secs):
            secs[idx], secs[j] = secs[j], secs[idx]
    s.sections = secs
    s.save(update_fields=["sections"])
    return JsonResponse({"ok": True})


@platform_admin_api
@owner_api
def image(request, d):
    slot = request.POST.get("slot")
    f = request.FILES.get("file")
    if slot not in ("hero", "about", "contact") or not f:
        return JsonResponse({"ok": False, "error": "Choose an image."}, status=400)
    try:
        main, _ = process_image(f, want_thumb=False)
    except ValidationError as e:
        return JsonResponse({"ok": False, "error": e.messages[0]}, status=400)
    s = request.site
    old = getattr(s, slot + "_image")
    if old:
        old.delete(save=False)
    setattr(s, slot + "_image", main)
    s.save()
    return JsonResponse({"ok": True})


@owner_api
def item_publish(request, d):
    it = Item.objects.filter(pk=d.get("id")).first()
    if not it:
        return JsonResponse({"ok": False, "error": "Not found."}, status=404)
    it.is_published = not it.is_published
    it.save(update_fields=["is_published"])
    return JsonResponse({"ok": True, "published": it.is_published})


@owner_api
def item_order(request, d):
    ids = d.get("ids")
    if (
        d.get("kind") != "catalog"
        or not isinstance(ids, list)
        or not ids
        or len(ids) > 100
        or any(type(item_id) is not int or item_id < 1 for item_id in ids)
        or len(set(ids)) != len(ids)
    ):
        return JsonResponse({"ok": False, "error": "Choose a valid release order."}, status=400)

    with transaction.atomic():
        items = list(
            Item.objects.select_for_update()
            .filter(kind="catalog")
            .order_by("sort_order", "-date", "-id")
        )
        current_ids = [item.pk for item in items]
        if not set(ids).issubset(current_ids):
            return JsonResponse({"ok": False, "error": "Some releases could not be found."}, status=400)

        ordered_ids = ids + [item_id for item_id in current_ids if item_id not in set(ids)]
        by_id = {item.pk: item for item in items}
        for index, item_id in enumerate(ordered_ids, start=1):
            by_id[item_id].sort_order = index * 10
        Item.objects.bulk_update(items, ["sort_order"])
    return JsonResponse({"ok": True})


@platform_admin_api
@owner_api
def preset(request, d):
    name = d.get("type")
    if name not in PRESETS:
        return JsonResponse({"ok": False, "error": "Unknown type."}, status=400)
    apply_preset_to(request.site, name)
    return JsonResponse({"ok": True})


@platform_admin_api
@owner_api
def theme(request, d):
    if d.get("theme") not in dict(THEMES):
        return JsonResponse({"ok": False, "error": "Unknown theme."}, status=400)
    s = request.site
    s.theme = d["theme"]
    s.save(update_fields=["theme"])
    return JsonResponse({"ok": True})
