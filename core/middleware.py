from .models import SiteSettings


class SiteMiddleware:
    """Attaches the site settings and the owner edit-mode flag to every request."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.site = SiteSettings.load()
        u = request.user
        request.is_owner = bool(u.is_authenticated and u.is_active and (u.is_staff or u.is_superuser))
        request.is_platform_admin = bool(request.is_owner and u.is_superuser)
        request.edit = bool(request.is_platform_admin and request.session.get("edit"))
        return self.get_response(request)
