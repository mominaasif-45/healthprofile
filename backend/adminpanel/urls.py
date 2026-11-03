from django.urls import path

from .views import (
    AdminAuditEventListView,
    AdminLoginView,
    AdminLogoutView,
    AdminMeView,
    AdminProfileAuditView,
    AdminProfileDeactivateView,
    AdminProfileDetailView,
    AdminProfileListView,
    AdminProfileReactivateView,
)

urlpatterns = [
    path("login/", AdminLoginView.as_view(), name="admin-login"),
    path("logout/", AdminLogoutView.as_view(), name="admin-logout"),
    path("me/", AdminMeView.as_view(), name="admin-me"),
    path("profiles/", AdminProfileListView.as_view(), name="admin-profile-list"),
    path("profiles/<int:pk>/", AdminProfileDetailView.as_view(), name="admin-profile-detail"),
    path("profiles/<int:pk>/deactivate/", AdminProfileDeactivateView.as_view(), name="admin-profile-deactivate"),
    path("profiles/<int:pk>/reactivate/", AdminProfileReactivateView.as_view(), name="admin-profile-reactivate"),
    path("profiles/<int:pk>/audit-events/", AdminProfileAuditView.as_view(), name="admin-profile-audit"),
    path("audit-events/", AdminAuditEventListView.as_view(), name="admin-audit-events"),
]
