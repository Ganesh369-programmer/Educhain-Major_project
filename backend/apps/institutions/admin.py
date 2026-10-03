from django.contrib import admin
from apps.institutions.models import Institution, IssuerProfile


@admin.register(Institution)
class InstitutionAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'institution_type',
        'status',
        'trust_tier',
        'wallet_address',
        'registered_wallet_address',
        'created_at',
    )
    list_filter = ('status', 'institution_type', 'trust_tier')
    search_fields = ('name', 'wallet_address', 'registration_number', 'official_email_domain')
    ordering = ('-created_at',)
    readonly_fields = (
        'id',
        'created_at',
        'updated_at',
        'reviewed_at',
        'wallet_address',
        'registered_wallet_address',
    )

    # encrypted_private_key is intentionally excluded from ALL fieldsets —
    # it must never be readable or editable through the admin UI.
    fieldsets = (
        ('Identity', {
            'fields': (
                'id',
                'name',
                'institution_type',
                'official_website',
                'official_email_domain',
                'registration_number',
                'gst_number',
                'proof_document',
            ),
        }),
        ('Blockchain / Wallet', {
            'fields': (
                'wallet_address',
                'registered_wallet_address',
            ),
        }),
        ('Review', {
            'fields': (
                'status',
                'trust_tier',
                'reviewed_by',
                'reviewed_at',
                'rejection_reason',
            ),
        }),
        ('Timestamps', {
            'fields': ('created_at', 'updated_at'),
        }),
    )

    def get_exclude(self, request, obj=None):
        # Belt-and-suspenders: always exclude encrypted_private_key
        # even if fieldsets are modified accidentally in future.
        return ['encrypted_private_key']


@admin.register(IssuerProfile)
class IssuerProfileAdmin(admin.ModelAdmin):
    list_display = ('user', 'institution', 'is_primary_contact', 'created_at')
    list_filter = ('is_primary_contact',)
    search_fields = ('user__email', 'institution__name')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at', 'updated_at')
