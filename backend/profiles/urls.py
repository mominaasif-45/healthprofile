from django.urls import path

from .views import (
    ContactDetailView,
    ContactListView,
    DemographicsView,
    MyActivityView,
    MyProfileView,
    WellnessView,
)

# Every route is under /api/profiles/me/ ... : there is deliberately no route that takes a profile id.
urlpatterns = [
    path("me/", MyProfileView.as_view(), name="profile-me"),
    path("me/demographics/", DemographicsView.as_view(), name="profile-demographics"),
    path("me/wellness/", WellnessView.as_view(), name="profile-wellness"),
    path("me/emergency-contacts/", ContactListView.as_view(), name="profile-contacts"),
    path("me/emergency-contacts/<int:pk>/", ContactDetailView.as_view(), name="profile-contact-detail"),
    path("me/activity/", MyActivityView.as_view(), name="profile-activity"),
]
