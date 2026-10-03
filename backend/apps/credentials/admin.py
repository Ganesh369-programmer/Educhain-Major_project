from django.contrib import admin
from apps.credentials.models import Credential, CredentialShare


@admin.register(Credential)
class CredentialAdmin(admin.ModelAdmin):
    list_display = ('student', 'institution', 'credential_type', 'title', 'status', 'document_hash', 'tx_hash', 'created_at')
    list_filter = ('status', 'credential_type')
    search_fields = ('student__full_name', 'student__user__email', 'institution__name', 'document_hash', 'tx_hash', 'title')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at', 'revoked_at')


@admin.register(CredentialShare)
class CredentialShareAdmin(admin.ModelAdmin):
    list_display = ('share_token', 'credential', 'expires_at', 'created_at')
    search_fields = ('share_token', 'credential__title')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at')
