from django.contrib import admin
from apps.blockchain.models import BlockchainTransaction


@admin.register(BlockchainTransaction)
class BlockchainTransactionAdmin(admin.ModelAdmin):
    list_display = ('tx_hash', 'action', 'status', 'gas_used', 'related_object_id', 'created_at')
    list_filter = ('action', 'status')
    search_fields = ('tx_hash', 'related_object_id')
    ordering = ('-created_at',)
    readonly_fields = ('id', 'created_at')
