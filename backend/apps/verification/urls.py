"""
URL routing for the verification app (Phase 9).

These URLs are mounted under both /api/verify/ and /api/v1/verify/ in config/urls.py.
"""

from django.urls import path
from apps.verification.views import (
    VerifyCredentialView,
    VerifyUploadView,
    VerificationHistoryView,
)

urlpatterns = [
    # Public credential verification by ID
    path(
        '<uuid:credential_id>/',
        VerifyCredentialView.as_view(),
        name='verify_credential',
    ),

    # Public document upload & hash comparison
    path(
        'upload/',
        VerifyUploadView.as_view(),
        name='verify_upload',
    ),

    # Authenticated verification history for a credential
    path(
        'history/<uuid:credential_id>/',
        VerificationHistoryView.as_view(),
        name='verify_history',
    ),
]
