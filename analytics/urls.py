"""URLs of the sales page, included at /analytics/ (config/urls.py), namespace "analytics"."""

from django.urls import path

from .views import SalesAnalyticsView

app_name = "analytics"

urlpatterns = [
    path("", SalesAnalyticsView.as_view(), name="sales"),
]
