from django.urls import path
from .views import (
    LoginView,
    CreateAccountView,
    ForgotPasswordView,
    ResetPasswordView,
    CustomerPlansView,
    SubmitClaimView,
    AddItemWithImagesView,
    PolicyDetailView,
    CreateCustomerPlanView,
)


urlpatterns = [
    path("login/", LoginView.as_view(), name="auth-login"),
    path("create-account/", CreateAccountView.as_view(), name="auth-create-account"),
    path("forgot-password/", ForgotPasswordView.as_view(), name="auth-forgot-password"),
    path("reset-password/", ResetPasswordView.as_view(), name="auth-reset-password"),
    path("customer/plans/", CustomerPlansView.as_view(), name="customer-plans"),
    path("claims/submit/", SubmitClaimView.as_view(), name="submit-claim"),
    path("items/add/", AddItemWithImagesView.as_view(), name="add-item-with-images"),
    path("policies/<int:customerPlanID>/", PolicyDetailView.as_view(), name="policy-detail"),
    path("customer/plans/create/", CreateCustomerPlanView.as_view(), name="customer-plan-create"),
]

