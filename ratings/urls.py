from django.urls import path

from . import views

# Namespace: "ratings:rate"
app_name = "ratings"

urlpatterns = [
    path("rate/<int:book_id>/", views.rate, name="rate"),
]
