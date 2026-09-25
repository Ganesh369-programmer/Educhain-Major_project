from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView

from apps.accounts.serializers import (
    UserRegisterSerializer,
    CustomTokenObtainPairSerializer,
    LogoutSerializer,
    UserSerializer,
)


class RegisterView(generics.CreateAPIView):
    """
    POST /auth/register/
    Registers a new STUDENT, ISSUER, or RECRUITER.
    ADMIN accounts cannot be self-registered.
    """
    permission_classes = [AllowAny]
    serializer_class = UserRegisterSerializer


class LoginView(TokenObtainPairView):
    """
    POST /auth/login/
    Validates email + password, returns { access, refresh, role }.
    """
    permission_classes = [AllowAny]
    serializer_class = CustomTokenObtainPairSerializer


class CustomTokenRefreshView(TokenRefreshView):
    """
    POST /auth/refresh/
    Exchanges a valid refresh token for a new access token.
    """
    permission_classes = [AllowAny]


class LogoutView(APIView):
    """
    POST /auth/logout/
    Blacklists the provided refresh token. Requires authentication.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(
            {"detail": "Successfully logged out.", "code": "LOGGED_OUT"},
            status=status.HTTP_205_RESET_CONTENT
        )


class CurrentUserView(generics.RetrieveUpdateAPIView):
    """
    GET /users/me/
    PATCH /users/me/
    Retrieves or updates the current authenticated user's profile.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = UserSerializer

    def get_object(self):
        return self.request.user
