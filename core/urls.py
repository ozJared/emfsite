from django.urls import path, re_path
from django.views.generic import RedirectView

from . import api, dash, views

KIND = r"(?P<kind>catalog|blog|news)"

urlpatterns = [
    path("", views.home, name="home"),
    path("services/", views.page, {"name": "features"}, name="features"),
    path("about/", RedirectView.as_view(pattern_name="contact", permanent=True), name="about"),
    path("contact/", views.page, {"name": "contact"}, name="contact"),
    re_path(rf"^{KIND}/$", views.listing, name="list"),
    re_path(rf"^{KIND}/(?P<slug>[-\w]+)/$", views.detail, name="detail"),
    # cart + orders
    path("cart/", views.cart, name="cart"),
    path("cart/add/<int:pk>/", views.cart_add, name="cart_add"),
    path("cart/remove/<int:pk>/", views.cart_remove, name="cart_remove"),
    path("checkout/", views.checkout, name="checkout"),
    path("order/thanks/", views.order_done, name="order_done"),
    path("order/thanks/<uuid:token>/", views.order_done, name="order_done_token"),
    path("order/thanks/<uuid:token>/pay/", views.retry_order_payment, name="retry_order_payment"),
    path("payment/paystack/return/", views.paystack_return, name="paystack_return"),
    path("payment/paystack/webhook/", views.paystack_webhook, name="paystack_webhook"),
    path("ticket/<uuid:token>/", views.ticket_detail, name="ticket_detail"),
    path("ticket/<uuid:token>/qr.svg", views.ticket_qr_download, name="ticket_qr_download"),
    path("ticket/<uuid:token>/verify/", views.ticket_verify, name="ticket_verify"),
    # owner
    path("login/", views.OwnerLoginView.as_view(), name="login"),
    path("logout/", views.owner_logout, name="logout"),
    path("owner/edit/", views.edit_toggle, name="edit_toggle"),
    # dashboard (full CRUD)
    path("dashboard/", dash.overview, name="dash"),
    path("dashboard/items/<str:kind>/", dash.item_list, name="dash_items"),
    path("dashboard/items/<str:kind>/new/", dash.item_edit, name="dash_item_new"),
    path("dashboard/item/<int:pk>/edit/", dash.item_edit, name="dash_item_edit"),
    path("dashboard/item/<int:pk>/delete/", dash.item_delete, name="dash_item_delete"),
    path("dashboard/item/<int:pk>/toggle/", dash.item_toggle, name="dash_item_toggle"),
    path("dashboard/orders/", dash.orders, name="dash_orders"),
    path("dashboard/orders/<int:pk>/", dash.order_detail, name="dash_order"),
    path("dashboard/orders/<int:pk>/delete/", dash.order_delete, name="dash_order_delete"),
    path("dashboard/messages/", dash.inbox, name="dash_messages"),
    path("dashboard/messages/<int:pk>/", dash.message_action, name="dash_message"),
    path("dashboard/settings/", dash.settings_view, name="dash_settings"),
    path("dashboard/settings/preset/", dash.apply_preset, name="dash_preset"),
    # edit-mode API
    path("api/text/", api.text, name="api_text"),
    path("api/vis/", api.vis, name="api_vis"),
    path("api/section/", api.section, name="api_section"),
    path("api/image/", api.image, name="api_image"),
    path("api/item/", api.item_publish, name="api_item"),
    path("api/item-order/", api.item_order, name="api_item_order"),
    path("api/preset/", api.preset, name="api_preset"),
    path("api/theme/", api.theme, name="api_theme"),
]
