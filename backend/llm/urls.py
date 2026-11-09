from django.urls import path

from .views import FaqAskView, PolicyUploadView

# Mounted at /api/llm/v1/: v1 is the request/response contract, not the model or prompt version.
urlpatterns = [
    path("faq/ask/", FaqAskView.as_view(), name="llm-faq-ask"),
    path("policies/", PolicyUploadView.as_view(), name="llm-policy-upload"),
]
