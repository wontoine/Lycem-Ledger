from django.urls import path
from .views import LoginView, CreateAccountView


urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("create-account/", CreateAccountView.as_view(), name="auth-create-account"),
]

