"""
URL configuration for Educhain project.
Routes mirror docs/API_SPECIFICATION.md with both /api/ and /api/v1/ prefixes supported.
"""

from django.contrib import admin
from django.urls import path, include
from apps.accounts.views import CurrentUserView

urlpatterns = [
    path('admin/', admin.site.urls),

    # Auth routes (/api/auth/ and /api/v1/auth/)
    path('api/auth/', include('apps.accounts.urls')),
    path('api/v1/auth/', include('apps.accounts.urls')),

    # User profile routes (/api/users/me/ and /api/v1/users/me/)
    path('api/users/me/', CurrentUserView.as_view(), name='api_user_me'),
    path('api/v1/users/me/', CurrentUserView.as_view(), name='api_v1_user_me'),

    # Feature apps
    path('api/institutions/', include('apps.institutions.urls')),
    path('api/v1/institutions/', include('apps.institutions.urls')),

    path('api/credentials/', include('apps.credentials.urls')),
    path('api/v1/credentials/', include('apps.credentials.urls')),

    path('api/verification/', include('apps.verification.urls')),
    path('api/v1/verification/', include('apps.verification.urls')),

    path('api/recruiters/', include('apps.recruiters.urls')),
    path('api/v1/recruiters/', include('apps.recruiters.urls')),

    path('api/blockchain/', include('apps.blockchain.urls')),
    path('api/v1/blockchain/', include('apps.blockchain.urls')),
]
