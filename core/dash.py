from django.contrib import messages
from django.contrib.auth.decorators import user_passes_test
from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Count
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from .forms import ItemForm, OwnerProfileForm, SettingsForm
from .models import Item, ItemImage, Message, Order
from .presets import KINDS, PRESETS, PRESET_TEXT_KEYS, SECTION_IDS
from .tickets import issue_order_tickets
from .utils import digits, process_image, wa_link

owner_only = user_passes_test(lambda u: u.is_active and (u.is_staff or u.is_superuser), login_url="/login/")
platform_admin_only = user_passes_test(
    lambda u: u.is_active and u.is_superuser, login_url="/login/")


def _ctx(request, tab, **extra):
    return dict(tab=tab, **extra)


@owner_only
def overview(request):
    return render(request, "core/dashboard/home.html", _ctx(
        request, "overview",
        new_orders=Order.objects.filter(status="new").count(),
        unread=Message.objects.filter(is_read=False).count(),
        counts={k: Item.objects.filter(kind=k).count() for k in KINDS},
        recent=Order.objects.prefetch_related("lines")[:5]))


# ------------------------------------------------------------------ items CRUD
@owner_only
def item_list(request, kind):
    if kind not in KINDS:
        raise Http404
    return render(request, "core/dashboard/items.html", _ctx(request, kind, kind=kind, rows=Item.objects.filter(kind=kind)))


@owner_only
def item_edit(request, kind=None, pk=None):
    item = get_object_or_404(Item, pk=pk) if pk else None
    kind = item.kind if item else kind
    if kind not in KINDS:
        raise Http404
    form = ItemForm(request.POST or None, request.FILES or None, instance=item, kind=kind)
    if request.method == "POST" and form.is_valid():
        obj = form.save(commit=False)
        obj.kind = kind
        obj.save()
        if kind == "catalog":
            for gid in request.POST.getlist("del_img"):
                g = ItemImage.objects.filter(pk=gid, item=obj).first()
                if g:
                    g.image.delete(save=False)
                    g.delete()
            for f in request.FILES.getlist("gallery")[:12]:
                try:
                    main, _ = process_image(f, want_thumb=False)
                    ItemImage.objects.create(item=obj, image=main)
                except ValidationError as e:
                    messages.warning(request, f"{f.name}: {e.messages[0]}")
        messages.success(request, "Saved")
        return redirect("dash_items", kind=kind)
    return render(request, "core/dashboard/item_form.html", _ctx(request, kind, kind=kind, item=item, form=form))


@owner_only
def item_delete(request, pk):
    item = get_object_or_404(Item, pk=pk)
    if request.method == "POST":
        kind = item.kind
        item.delete()
        messages.success(request, "Deleted")
        return redirect("dash_items", kind=kind)
    return render(request, "core/dashboard/item_delete.html", _ctx(request, item.kind, item=item))


@owner_only
@require_POST
def item_toggle(request, pk):
    item = get_object_or_404(Item, pk=pk)
    item.is_published = not item.is_published
    item.save(update_fields=["is_published"])
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("dash_items", kind=item.kind)


# ------------------------------------------------------------------ orders
@owner_only
def orders(request):
    st = request.GET.get("status", "")
    qs = Order.objects.prefetch_related("lines")
    if st:
        qs = qs.filter(status=st)
    return render(request, "core/dashboard/orders.html", _ctx(request, "orders", rows=qs, st=st, statuses=Order.STATUS))


@owner_only
def order_detail(request, pk):
    o = get_object_or_404(Order.objects.prefetch_related("lines__tickets", "payment_attempts"), pk=pk)
    if request.method == "POST":
        if request.POST.get("status") in dict(Order.STATUS):
            with transaction.atomic():
                o.status = request.POST["status"]
                o.save(update_fields=["status"])
                if o.status == "paid":
                    issue_order_tickets(o)
            messages.success(request, "Status updated; event tickets are now available." if o.status == "paid" else "Status updated")
        return redirect("dash_order", pk=o.pk)
    reply = wa_link(digits(o.phone), f"Hi {o.name}, about your order #{o.pk}: ")
    tickets = [ticket for line in o.lines.all() for ticket in line.tickets.all()]
    return render(request, "core/dashboard/order_detail.html", _ctx(
        request, "orders", o=o, statuses=Order.STATUS, reply=reply, tickets=tickets))


@owner_only
@require_POST
def order_delete(request, pk):
    get_object_or_404(Order, pk=pk).delete()
    messages.success(request, "Order deleted")
    return redirect("dash_orders")


# ------------------------------------------------------------------ messages
@owner_only
def inbox(request):
    return render(request, "core/dashboard/messages.html", _ctx(request, "messages", rows=Message.objects.all()))


@owner_only
@require_POST
def message_action(request, pk):
    m = get_object_or_404(Message, pk=pk)
    if request.POST.get("do") == "delete":
        m.delete()
    else:
        m.is_read = not m.is_read
        m.save(update_fields=["is_read"])
    return redirect("dash_messages")


# ------------------------------------------------------------------ settings
@owner_only
def settings_view(request):
    s = request.site
    form_class = SettingsForm if request.is_platform_admin else OwnerProfileForm
    form = form_class(request.POST or None, request.FILES or None, initial=form_class.initial_for(s))
    if request.method == "POST" and form.is_valid():
        form.apply(s)
        messages.success(request, "Settings saved")
        return redirect("dash_settings")
    return render(request, "core/dashboard/settings.html", _ctx(
        request, "settings", form=form, presets=list(PRESETS) if request.is_platform_admin else (),
        current=s.site_type, is_platform_admin=request.is_platform_admin,
        recipient_ready=bool(s.notification_email),
        smtp_ready=bool(settings.EMAIL_HOST and settings.EMAIL_HOST_USER and settings.EMAIL_HOST_PASSWORD)))


@platform_admin_only
@require_POST
def apply_preset(request):
    name = request.POST.get("type")
    if name not in PRESETS:
        raise Http404
    apply_preset_to(request.site, name)
    messages.success(request, f"Switched to {name}. Your content is untouched.")
    nxt = request.POST.get("next", "")
    if nxt and url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        return redirect(nxt)
    return redirect("dash_settings")


def apply_preset_to(s, name):
    p = PRESETS[name]
    known_ghosts = {x["ghost"] for x in PRESETS.values()} | {""}
    s.site_type, s.theme = name, p["theme"]
    if s.ghost in known_ghosts:
        s.ghost = p["ghost"]
    s.tagline, s.blurb, s.cta = p["tagline"], p["blurb"], p["cta"]
    s.labels = dict(p["labels"])
    s.sections = [{"id": i, "on": i in p["on"]} for i in SECTION_IDS]
    for k in PRESET_TEXT_KEYS:
        s.texts.pop(k, None)
    s.save()
