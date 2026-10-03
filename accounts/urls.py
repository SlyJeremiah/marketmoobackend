from django.urls import path

from .views import ChangePasswordView, MeView, OtpRequestView, OtpVerifyView, PasswordLoginView, StaffLoginView

urlpatterns = [
    path("otp/request", OtpRequestView.as_view()),
    path("otp/verify", OtpVerifyView.as_view()),
    path("me", MeView.as_view()),
    path("staff-login", StaffLoginView.as_view()),
    path("login", PasswordLoginView.as_view()),
    path("password", ChangePasswordView.as_view()),
]
