from django.urls import path

from . import views

# Namespace: "currencies:rates"
app_name = "currencies"

urlpatterns = [
    # Load the NBU rates, check, save with a button (staff with the right)
    path("rates/", views.NBURatesView.as_view(), name="rates"),
]
