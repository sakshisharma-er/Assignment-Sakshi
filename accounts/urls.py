from django.urls import path

from .views import LoginView, MeView, RegisterView

urlpatterns = [
    path("register/", RegisterView.as_view(), name="register"),
    path("token/", LoginView.as_view(), name="token"),
    path("me/", MeView.as_view(), name="me"),
]
