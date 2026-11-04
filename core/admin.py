from django.contrib import admin
from .models import Item, ItemImage, Message, Order, OrderItem, SiteSettings, Ticket

admin.site.register(Message)


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    def has_module_permission(self, request):
        return request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_add_permission(self, request):
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


class GalleryInline(admin.TabularInline):
    model = ItemImage
    extra = 0


@admin.register(Item)
class ItemAdmin(admin.ModelAdmin):
    list_display = ("title", "kind", "price", "is_ticket", "date", "is_published")
    list_filter = ("kind", "is_published")
    search_fields = ("title",)
    inlines = [GalleryInline]


class LineInline(admin.TabularInline):
    model = OrderItem
    extra = 0


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "phone", "total", "status", "created")
    list_filter = ("status",)
    inlines = [LineInline]


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ("code", "order_item", "number", "issued_at")
    search_fields = ("code", "order_item__title", "order_item__order__name")
