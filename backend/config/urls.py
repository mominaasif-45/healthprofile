from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

urlpatterns = [
    # API documentation
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/docs/", SpectacularSwaggerView.as_view(url_name="schema"), name="swagger-ui"),
    # Shared endpoints: /api/health/ and /api/csrf/
    path("api/", include("core.urls")),
    # User auth (JWT cookies): signup, login, refresh, logout, me
    path("api/auth/", include("accounts.urls")),
    # Users: /api/profiles/me/ only (no /profiles/{id}/ route exists)
    path("api/profiles/", include("profiles.urls")),
    # Admins (server-side session): login, logout, me, list/search/detail/deactivate
    path("api/admin/", include("adminpanel.urls")),
]