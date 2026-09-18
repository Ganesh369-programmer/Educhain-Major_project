"""
URL configuration for Educhain project.
"""

from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/auth/', include('apps.accounts.urls')),
    path('api/institutions/', include('apps.institutions.urls')),
    path('api/credentials/', include('apps.credentials.urls')),
    path('api/verification/', include('apps.verification.urls')),
    path('api/recruiters/', include('apps.recruiters.urls')),
    path('api/blockchain/', include('apps.blockchain.urls')),
]
