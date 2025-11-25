from django.urls import path
from .views import LoginView, CreateAccountView, ForgotPasswordView, ResetPasswordView, CustomerPlansView


urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("create-account/", CreateAccountView.as_view(), name="auth-create-account"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("customer/plans/", CustomerPlansView.as_view(), name="customer-plans"),
]

