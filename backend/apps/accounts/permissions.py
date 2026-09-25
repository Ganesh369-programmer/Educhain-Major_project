"""
Role-based permission classes per USER_ROLES_AND_PERMISSIONS.md and BACKEND_GUIDELINES.md.
"""

from rest_framework.permissions import BasePermission
from apps.accounts.models import UserRole


class BaseRolePermission(BasePermission):
    """Base class for role-based permission checks."""
    allowed_roles = ()

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.is_active
            and request.user.role in self.allowed_roles
        )


class IsAdmin(BaseRolePermission):
    """Allows access only to users with role=ADMIN."""
    allowed_roles = (UserRole.ADMIN,)


class IsStudent(BaseRolePermission):
    """Allows access only to users with role=STUDENT."""
    allowed_roles = (UserRole.STUDENT,)


class IsIssuer(BaseRolePermission):
    """Allows access only to users with role=ISSUER."""
    allowed_roles = (UserRole.ISSUER,)


class IsRecruiter(BaseRolePermission):
    """Allows access only to users with role=RECRUITER."""
    allowed_roles = (UserRole.RECRUITER,)


def HasAnyRole(*roles):
    """Helper factory to enforce that the user has at least one of the specified roles."""
    class DynamicRolePermission(BaseRolePermission):
        allowed_roles = roles
    return DynamicRolePermission
