from rest_framework.permissions import BasePermission
from apps.accounts.models import UserRole
from apps.institutions.models import IssuerProfile


class IsAdmin(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role == UserRole.ADMIN
        )


class IsIssuer(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role == UserRole.ISSUER
        )


class IsAdminOrOwnInstitution(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role in (UserRole.ADMIN, UserRole.ISSUER)
        )

    def has_object_permission(self, request, view, obj):
        if request.user.role == UserRole.ADMIN:
            return True
        if request.user.role == UserRole.ISSUER:
            return IssuerProfile.objects.filter(
                user=request.user,
                institution=obj,
            ).exists()
        return False


class IsAdminOrListOwnInstitution(BasePermission):
    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role in (UserRole.ADMIN, UserRole.ISSUER)
        )
