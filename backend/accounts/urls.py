from django.urls import path

from .views import MeView, SignupView, UserLoginView, UserLogoutView, UserRefreshView

urlpatterns = [
    path("signup/", SignupView.as_view(), name="signup"),
    path("user/login/", UserLoginView.as_view(), name="user-login"),
    path("user/refresh/", UserRefreshView.as_view(), name="user-refresh"),
    path("user/logout/", UserLogoutView.as_view(), name="user-logout"),
    path("me/", MeView.as_view(), name="me"),
]