import json
import logging
import secrets

from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.contrib.auth.forms import AuthenticationForm
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.db import transaction
from django.http import Http404, HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods, require_POST

from .forms import CheckoutForm, ContactForm
from .models import Item, Message, Order, OrderItem, PaymentAttempt, Ticket
from .payments import (
    PaystackError,
    currency_is_supported,
    initialize_transaction,
    is_configured as paystack_is_configured,
    successful_payment_matches,
    verify_transaction,
    verify_webhook_signature,
)
from .presets import KINDS
from .tickets import issue_order_tickets, qr_data_uri, qr_svg_bytes
from .utils import client_ip, notify_contact_message, notify_order, wa_link

logger = logging.getLogger(__name__)


def not_found(request, exception=None):
    return render(request, "404.html", status=404)


def published(request, kind):
    qs = Item.objects.filter(kind=kind)
    if kind == "catalog":
        qs = qs.order_by("sort_order", "-date", "-id")
    return qs if request.is_owner else qs.filter(is_published=True)


def home(request):
    items = {k: list(published(request, k)[:12]) for k in KINDS}
    featured = next((i for i in items["catalog"] if i.is_published), None)
    sections = [s for s in request.site.section_list() if s["on"] or request.edit]
    return render(request, "core/home.html", {"items": items, "featured": featured, "sections": sections, "form": ContactForm()})


def listing(request, kind):
    if not request.site.is_on(kind) and not request.is_owner:
        raise Http404
    return render(request, "core/list.html", {"kind": kind, "list": published(request, kind)})


def detail(request, kind, slug):
    item = get_object_or_404(Item, kind=kind, slug=slug)
    if not item.is_published and not request.is_owner:
        raise Http404
    more = published(request, kind).exclude(pk=item.pk).filter(is_published=True)[:3]
    # Catalog items (products, releases, services) share the product-style page; blog and news use the article page.
    tpl = "core/detail_product.html" if kind == "catalog" else "core/detail_article.html"
    return render(request, tpl, {"item": item, "more": more, "kind": kind,
                                 "og_image": request.build_absolute_uri(item.image.url) if item.image else ""})


def page(request, name):
    if not request.site.is_on(name) and not request.is_owner:
        raise Http404
    form = None
    if name == "contact":
        form = ContactForm(request.POST or None)
        if request.method == "POST":
            if form.is_valid():
                d = form.cleaned_data
                if not d["website"]:  # honeypot empty = human
                    saved = Message.objects.create(name=d["name"], email=d["email"], body=d["body"])
                    if notify_contact_message(request.site, saved):
                        messages.success(request, "Message sent. We’ll reply soon.")
                    else:
                        messages.warning(request, "Your message was saved, but its email notification could not be delivered. The owner can still read it in the dashboard.")
                else:
                    messages.success(request, "Message sent. We’ll reply soon.")
                return redirect("contact")
    return render(request, "core/page.html", {"name": name, "form": form, "items": {}, "featured": None})


# ---------------------------------------------------------------- cart / orders
def _cart_lines(request):
    cart = request.session.get("cart", {})
    items = {str(i.pk): i for i in Item.objects.filter(pk__in=[int(k) for k in cart], kind="catalog",
                                                         is_published=True, price__gt=0)}
    lines, total = [], 0
    for k, qty in cart.items():
        it = items.get(k)
        if it:
            lines.append({"item": it, "qty": qty, "sub": it.price * qty})
            total += it.price * qty
    return lines, total


@require_POST
def cart_add(request, pk):
    item = get_object_or_404(Item, pk=pk, kind="catalog", is_published=True, price__gt=0)
    try:
        quantity = int(request.POST.get("qty", "1"))
    except ValueError:
        return HttpResponseBadRequest("Invalid quantity.")
    if not 1 <= quantity <= 20:
        return HttpResponseBadRequest("Quantity must be between 1 and 20.")
    cart = request.session.get("cart", {})
    cart[str(item.pk)] = min(cart.get(str(item.pk), 0) + quantity, 20)
    request.session["cart"] = cart
    messages.success(request, "Added to your order")
    return redirect("checkout" if request.POST.get("next") == "checkout" else "cart")


@require_POST
def cart_remove(request, pk):
    cart = request.session.get("cart", {})
    cart.pop(str(pk), None)
    request.session["cart"] = cart
    return redirect("cart")


def cart(request):
    lines, total = _cart_lines(request)
    return render(request, "core/cart.html", {"lines": lines, "total": total, "form": CheckoutForm()})


@require_http_methods(["GET", "POST"])
def checkout(request):
    lines, total = _cart_lines(request)
    if not lines:
        return redirect("cart")
    payment_enabled = paystack_is_configured() and currency_is_supported(request.site.currency)
    if request.method == "GET":
        return render(request, "core/checkout.html", {
            "lines": lines, "total": total, "form": CheckoutForm(),
            "payment_enabled": payment_enabled,
        })
    form = CheckoutForm(request.POST)
    if not form.is_valid():
        return render(request, "core/checkout.html", {
            "lines": lines, "total": total, "form": form,
            "payment_enabled": payment_enabled,
        })
    d = form.cleaned_data
    site = request.site
    with transaction.atomic():
        order = Order.objects.create(name=d["name"], email=d["email"], phone=d["phone"],
                                     address=d["address"], note=d["note"],
                                     total=total, currency=site.currency)
        OrderItem.objects.bulk_create([OrderItem(
            order=order, item=l["item"], title=l["item"].title, price=l["item"].price,
            qty=l["qty"], is_ticket=l["item"].is_ticket,
        ) for l in lines])
    request.session["cart"] = {}
    request.session["last_order"] = order.pk
    tracking_url = request.build_absolute_uri(reverse("order_done_token", args=[order.public_token]))
    email_sent = notify_order(site, order, tracking_url)
    if not email_sent:
        messages.warning(
            request,
            "Your order was saved, but the owner email notification could not be delivered. "
            "The owner can still see the order in the dashboard.",
        )
    if site.whatsapp_checkout and site.wa_digits:
        text = order_message(order, tracking_url)
        return HttpResponseRedirect(wa_link(site.wa_digits, text))
    if payment_enabled:
        return _start_order_payment(request, order)
    messages.warning(
        request,
        "Your order was saved, but online payment is not configured. "
        "Contact the store to arrange payment.",
    )
    return redirect("order_done_token", token=order.public_token)


def _start_order_payment(request, order):
    if order.status != "new":
        messages.info(request, "This order is no longer awaiting payment.")
        return redirect("order_done_token", token=order.public_token)
    if not paystack_is_configured() or not currency_is_supported(order.currency):
        messages.error(request, "Paystack is not configured for this store currency.")
        return redirect("order_done_token", token=order.public_token)
    pending_attempt = order.payment_attempts.filter(status="pending").first()
    if pending_attempt and pending_attempt.authorization_url:
        return HttpResponseRedirect(pending_attempt.authorization_url)
    if pending_attempt:
        pending_attempt.status = "failed"
        pending_attempt.save(update_fields=["status"])
    attempt = PaymentAttempt.objects.create(order=order, reference=secrets.token_hex(16))
    callback_url = request.build_absolute_uri(reverse("paystack_return"))
    try:
        authorization_url = initialize_transaction(
            attempt.reference, order.email, order.total, callback_url,
        )
    except PaystackError as exc:
        attempt.status = "failed"
        attempt.save(update_fields=["status"])
        logger.warning("Paystack initialization failed for order %s: %s", order.pk, exc)
        messages.error(request, "Could not start payment. You can try again from this order page.")
        return redirect("order_done_token", token=order.public_token)
    attempt.authorization_url = authorization_url
    attempt.save(update_fields=["authorization_url"])
    return HttpResponseRedirect(authorization_url)


@require_POST
def retry_order_payment(request, token):
    order = get_object_or_404(Order, public_token=token)
    return _start_order_payment(request, order)


def _verify_and_record_payment(reference):
    attempt = PaymentAttempt.objects.select_related("order").filter(reference=reference).first()
    if not attempt:
        return None, False
    if not paystack_is_configured():
        raise PaystackError("Paystack is not configured.")
    data = verify_transaction(reference)
    if isinstance(data, dict) and data.get("reference") == reference and data.get("status") in {"failed", "abandoned"}:
        attempt.status = "failed"
        attempt.save(update_fields=["status"])
    if not successful_payment_matches(attempt.order, reference, data):
        return attempt.order, False
    with transaction.atomic():
        attempt = PaymentAttempt.objects.select_for_update().get(pk=attempt.pk)
        order = Order.objects.select_for_update().get(pk=attempt.order_id)
        if not successful_payment_matches(order, reference, data):
            return order, False
        attempt.status = "paid"
        attempt.save(update_fields=["status"])
        if order.status not in {"paid", "shipped", "done"}:
            order.status = "paid"
            order.save(update_fields=["status"])
            issue_order_tickets(order)
    return order, True


@require_http_methods(["GET"])
def paystack_return(request):
    reference = request.GET.get("reference") or request.GET.get("trxref", "")
    if not reference or len(reference) > 100:
        messages.error(request, "The payment reference is missing or invalid.")
        return redirect("cart")
    attempt = PaymentAttempt.objects.select_related("order").filter(reference=reference).first()
    if not attempt:
        messages.error(request, "We could not match this payment to an order.")
        return redirect("home")
    try:
        order, paid = _verify_and_record_payment(reference)
    except PaystackError as exc:
        logger.warning("Paystack verification failed for reference %s: %s", reference, exc)
        messages.error(request, "Payment verification is temporarily unavailable. Please check this order again.")
        return redirect("order_done_token", token=attempt.order.public_token)
    if paid:
        messages.success(request, "Payment verified. Your order is confirmed.")
    else:
        messages.error(request, "Payment has not been confirmed. Your order remains unpaid.")
    return redirect("order_done_token", token=order.public_token)


@csrf_exempt
@require_POST
def paystack_webhook(request):
    signature = request.headers.get("x-paystack-signature", "")
    if not verify_webhook_signature(request.body, signature):
        return HttpResponse(status=400)
    try:
        event = json.loads(request.body.decode("utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return HttpResponse(status=400)
    if not isinstance(event, dict) or event.get("event") != "charge.success":
        return HttpResponse(status=200)
    data = event.get("data")
    reference = data.get("reference") if isinstance(data, dict) else None
    if not isinstance(reference, str) or not reference:
        return HttpResponse(status=400)
    if not PaymentAttempt.objects.filter(reference=reference).exists():
        return HttpResponse(status=200)
    try:
        _, paid = _verify_and_record_payment(reference)
    except PaystackError:
        logger.warning("Paystack webhook verification is temporarily unavailable for reference %s", reference)
        return HttpResponse(status=503)
    if not paid:
        logger.warning("Paystack webhook payment did not match the stored order for reference %s", reference)
    return HttpResponse(status=200)


def order_message(order, tracking_url=""):
    from .templatetags.site_tags import money
    rows = [f"New order #{order.pk}"]
    rows += [f"{l.qty} × {l.title} ({money(l.price, order.currency)})" for l in order.lines.all()]
    rows += [f"Total: {money(order.total, order.currency)}", f"Name: {order.name}", f"Phone: {order.phone}"]
    if order.address:
        rows.append(f"Address: {order.address}")
    if order.note:
        rows.append(f"Note: {order.note}")
    if tracking_url:
        rows.append(f"Order status and tickets: {tracking_url}")
    return "\n".join(rows)


def order_done(request, token=None):
    orders = Order.objects.prefetch_related("lines__tickets")
    order = orders.filter(public_token=token).first() if token else orders.filter(pk=request.session.get("last_order")).first()
    tickets = [ticket for line in order.lines.all() for ticket in line.tickets.all() if ticket.is_valid] if order else []
    payment_enabled = bool(
        order and order.status == "new" and paystack_is_configured()
        and currency_is_supported(order.currency)
    )
    return render(request, "core/order_done.html", {
        "order": order, "tickets": tickets, "payment_enabled": payment_enabled,
    })


def ticket_detail(request, token):
    ticket = get_object_or_404(Ticket.objects.select_related("order_item__item", "order_item__order"), token=token)
    verification_url = request.build_absolute_uri(reverse("ticket_verify", args=[ticket.token]))
    return render(request, "core/ticket.html", {
        "ticket": ticket, "qr_data": qr_data_uri(verification_url),
        "item": ticket.order_item.item,
    })


def ticket_qr_download(request, token):
    ticket = get_object_or_404(
        Ticket.objects.select_related("order_item__order"),
        token=token,
    )
    if not ticket.is_valid:
        raise Http404("A QR code is only available for a valid, paid ticket.")
    verification_url = request.build_absolute_uri(reverse("ticket_verify", args=[ticket.token]))
    response = HttpResponse(qr_svg_bytes(verification_url), content_type="image/svg+xml")
    response["Content-Disposition"] = f'attachment; filename="ticket-{ticket.code}-qr.svg"'
    response["X-Content-Type-Options"] = "nosniff"
    return response


def ticket_verify(request, token):
    ticket = get_object_or_404(Ticket.objects.select_related("order_item__item", "order_item__order"), token=token)
    return render(request, "core/ticket_verify.html", {"ticket": ticket, "item": ticket.order_item.item})


# ---------------------------------------------------------------- owner login
class OwnerLoginForm(AuthenticationForm):
    def __init__(self, *a, **k):
        super().__init__(*a, **k)
        self.fields["username"].widget.attrs.update({"placeholder": "Username", "autocapitalize": "none"})
        self.fields["password"].widget.attrs.update({"placeholder": "Password"})

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not (user.is_staff or user.is_superuser):
            raise ValidationError(
                "This account has no site-owner role. Enable Staff status for an owner account, "
                "or Superuser status for the platform owner.",
                code="no_access",
            )


class OwnerLoginView(auth_views.LoginView):
    template_name = "core/login.html"
    authentication_form = OwnerLoginForm
    redirect_authenticated_user = True
    MAX_TRIES, WINDOW = 5, 15 * 60

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["site"] = self.request.site
        return context

    def _key(self):
        return "login-fail:" + client_ip(self.request)

    def post(self, request, *a, **k):
        if cache.get(self._key(), 0) >= self.MAX_TRIES:
            form = self.get_form()
            form.add_error(None, "Too many attempts. Wait 15 minutes and try again.")
            return self.render_to_response(self.get_context_data(form=form), status=429)
        return super().post(request, *a, **k)

    def form_invalid(self, form):
        cache.set(self._key(), cache.get(self._key(), 0) + 1, self.WINDOW)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._key())
        return super().form_valid(form)

    def get_success_url(self):
        return self.get_redirect_url() or reverse("home")


@require_POST
def owner_logout(request):
    from django.contrib.auth import logout
    logout(request)
    return redirect("home")


@require_POST
def edit_toggle(request):
    if not request.is_platform_admin:
        raise Http404
    request.session["edit"] = not request.session.get("edit", False)
    nxt = request.POST.get("next", "/")
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    return redirect(nxt)
