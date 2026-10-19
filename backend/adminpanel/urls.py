from django.urls import path

from .views import (
    AdminLoginView,
    AdminLogoutView,
    AdminMeView,
    AdminProfileDeactivateView,
    AdminProfileDetailView,
    AdminProfileListView,
)

urlpatterns = [
    path("login/", AdminLoginView.as_view(), name="admin-login"),
    path("logout/", AdminLogoutView.as_view(), name="admin-logout"),
    path("me/", AdminMeView.as_view(), name="admin-me"),
    path("profiles/", AdminProfileListView.as_view(), name="admin-profile-list"),
    path("profiles/<int:pk>/", AdminProfileDetailView.as_view(), name="admin-profile-detail"),
    path(
        "profiles/<int:pk>/deactivate/",
        AdminProfileDeactivateView.as_view(),
        name="admin-profile-deactivate",
    ),
]
