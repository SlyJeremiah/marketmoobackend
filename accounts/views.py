from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.module_loading import import_string
from rest_framework import serializers, status
from rest_framework.authtoken.models import Token
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .models import DISTRICTS, OtpCode, User, normalise_phone


class OtpThrottle(AnonRateThrottle):
    scope = "otp"


class OtpVerifyThrottle(AnonRateThrottle):
    scope = "otp_verify"


class OtpRequestSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)


class OtpVerifySerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=20)
    code = serializers.CharField(max_length=6, min_length=6)
    consent = serializers.BooleanField(required=False, default=False)


class OtpRequestView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [OtpThrottle]

    def post(self, request):
        s = OtpRequestSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = normalise_phone(s.validated_data["phone"])
        if len(phone) < 10 or len(phone) > 16:
            return Response({"detail": "Enter a valid phone number."}, status=status.HTTP_400_BAD_REQUEST)
        # per-number limit on top of the per-IP throttle
        recent = OtpCode.objects.filter(phone=phone, created_at__gte=timezone.now() - timedelta(hours=1)).count()
        if recent >= 5:
            return Response({"detail": "Too many codes requested. Try again later."}, status=status.HTTP_429_TOO_MANY_REQUESTS)
        _row, code = OtpCode.issue(phone)
        import_string(settings.SMS_BACKEND)().send(phone, f"Your MarketMoo code is {code}. It expires in {settings.OTP_TTL_SECONDS // 60} minutes.")
        body = {"detail": "Code sent.", "expires_in": settings.OTP_TTL_SECONDS}
        if settings.OTP_DEV_ECHO:
            body["dev_code"] = code  # development only
        return Response(body)


class OtpVerifyView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [OtpVerifyThrottle]

    @transaction.atomic
    def post(self, request):
        s = OtpVerifySerializer(data=request.data)
        s.is_valid(raise_exception=True)
        phone = normalise_phone(s.validated_data["phone"])
        row = OtpCode.objects.filter(phone=phone, used=False).order_by("-created_at").first()
        if row is None or not row.verify_code(s.validated_data["code"]):
            return Response({"detail": "Code is wrong or expired."}, status=status.HTTP_400_BAD_REQUEST)
        user, created = User.objects.get_or_create(phone=phone, defaults={"username": phone})
        if s.validated_data["consent"] and not user.consent_at:
            user.consent_at = timezone.now(); user.save(update_fields=["consent_at"])
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "created": created, "profile": ProfileSerializer(user).data})


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        fields = ["phone", "role", "language", "district", "verified"]
        read_only_fields = ["phone", "verified"]


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ProfileSerializer(request.user).data)

    def patch(self, request):
        s = ProfileSerializer(request.user, data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        if s.validated_data.get("role") == User.Role.ADMIN:
            return Response({"detail": "Not allowed."}, status=status.HTTP_403_FORBIDDEN)
        s.save()
        return Response(s.data)

    def delete(self, request):
        """Delete my data (Design Document 13): removes the account and everything it owns (cascade)."""
        request.user.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class StaffThrottle(AnonRateThrottle):
    scope = "staff_login"


class StaffLoginView(APIView):
    """Password login for the manager dashboard. Farmers never have passwords, so only staff or admin-role users succeed."""
    permission_classes = [AllowAny]
    authentication_classes: list = []
    throttle_classes = [StaffThrottle]

    def post(self, request):
        from django.contrib.auth import authenticate

        ident = str(request.data.get("username", "")).strip()
        user = authenticate(request, username=ident, password=str(request.data.get("password", "")))
        if user is None:
            user = authenticate(request, username=normalise_phone(ident) if ident else "", password=str(request.data.get("password", "")))
        if user is None or not (user.is_staff or user.role == User.Role.ADMIN) or not user.is_active:
            return Response({"detail": "Wrong username or password."}, status=status.HTTP_400_BAD_REQUEST)
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "profile": ProfileSerializer(user).data})
