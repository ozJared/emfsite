from django.conf import settings
from django.contrib import admin
from django.urls import include, path, re_path
from django.views.static import serve

handler404 = "core.views.not_found"

urlpatterns = [
    path("django-admin/", admin.site.urls),
    re_path(r"^media/(?P<path>.*)$", serve, {"document_root": settings.MEDIA_ROOT}),
    path("", include("core.urls")),
]
