"""
Centralized exception handler conforming to API_SPECIFICATION.md:
All error responses follow: { "detail": "human readable message", "code": "MACHINE_CODE" }
"""

from rest_framework import exceptions, status
from rest_framework.views import exception_handler
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError


def custom_exception_handler(exc, context):
    response = exception_handler(exc, context)

    if response is None:
        return None

    detail_message = "An unexpected error occurred."
    code = "UNKNOWN_ERROR"

    # Default code by status code
    status_code_map = {
        status.HTTP_400_BAD_REQUEST: "VALIDATION_ERROR",
        status.HTTP_401_UNAUTHORIZED: "UNAUTHENTICATED",
        status.HTTP_403_FORBIDDEN: "FORBIDDEN",
        status.HTTP_404_NOT_FOUND: "NOT_FOUND",
        status.HTTP_405_METHOD_NOT_ALLOWED: "METHOD_NOT_ALLOWED",
        status.HTTP_409_CONFLICT: "CONFLICT",
        status.HTTP_429_TOO_MANY_REQUESTS: "RATE_LIMITED",
        status.HTTP_500_INTERNAL_SERVER_ERROR: "INTERNAL_SERVER_ERROR",
        status.HTTP_502_BAD_GATEWAY: "BLOCKCHAIN_ERROR",
    }
    code = status_code_map.get(response.status_code, "ERROR")

    # Specific JWT handling per AUTHENTICATION.md
    raw_str = f"{str(exc)} {str(response.data)}".lower()
    if "blacklisted" in raw_str:
        code = "REFRESH_INVALID"
        detail_message = "Token is blacklisted."
    elif isinstance(exc, (InvalidToken, TokenError)):
        msg = str(exc)
        if "expired" in msg.lower() or "token_not_valid" in msg.lower():
            code = "TOKEN_EXPIRED"
            detail_message = "Token is invalid or expired."
        else:
            code = "UNAUTHENTICATED"
            detail_message = msg or "Authentication credentials were not provided or are invalid."
    elif isinstance(response.data, dict):
        # Extract existing detail or message
        if "detail" in response.data:
            detail_val = response.data["detail"]
            detail_message = str(detail_val)
            if hasattr(detail_val, "code") and detail_val.code:
                if detail_val.code == "not_authenticated":
                    code = "UNAUTHENTICATED"
                elif detail_val.code == "permission_denied":
                    code = "FORBIDDEN"
                elif detail_val.code == "token_not_valid":
                    code = "TOKEN_EXPIRED"
        else:
            # Flatten validation errors
            messages = []
            for field, errs in response.data.items():
                if isinstance(errs, list):
                    err_str = ", ".join(str(e) for e in errs)
                else:
                    err_str = str(errs)
                messages.append(f"{field}: {err_str}")
            detail_message = "; ".join(messages)
            code = "VALIDATION_ERROR"
    elif isinstance(response.data, list):
        detail_message = "; ".join(str(e) for e in response.data)
        code = "VALIDATION_ERROR"

    response.data = {
        "detail": detail_message,
        "code": code,
    }

    return response
