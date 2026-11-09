from django.urls import path

from .views import ClustersView, NoShowPredictView, WorkbenchView

# Mounted at /api/ml/v1/: v1 is the request/response contract, not the model version.
urlpatterns = [
    path("no-show/predict/", NoShowPredictView.as_view(), name="ml-no-show-predict"),
    path("workbench/", WorkbenchView.as_view(), name="ml-workbench"),
    path("clusters/", ClustersView.as_view(), name="ml-clusters"),
]
