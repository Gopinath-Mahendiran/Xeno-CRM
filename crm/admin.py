from django.contrib import admin
from .models import Customer, Order, Segment, Campaign, CommunicationLog, ChatSession


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display    = ['id', 'name', 'email', 'phone', 'city', 'total_spent', 'order_count', 'last_order_at']
    search_fields   = ['name', 'email', 'phone', 'city']
    list_filter     = ['city']
    ordering        = ['-created_at']


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display    = ['id', 'customer', 'amount', 'status', 'ordered_at']
    search_fields   = ['customer__name', 'customer__email']
    list_filter     = ['status']
    ordering        = ['-ordered_at']


@admin.register(Segment)
class SegmentAdmin(admin.ModelAdmin):
    list_display    = ['id', 'name', 'natural_query', 'customer_count', 'created_at']
    search_fields   = ['name', 'natural_query']
    ordering        = ['-created_at']


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display    = [
        'id', 'name', 'channel', 'status',
        'sent_count', 'delivered_count', 'failed_count',
        'read_count', 'clicked_count', 'order_count',
        'created_at'
    ]
    search_fields   = ['name']
    list_filter     = ['status', 'channel']
    ordering        = ['-created_at']


@admin.register(CommunicationLog)
class CommunicationLogAdmin(admin.ModelAdmin):
    list_display    = ['message_id', 'customer', 'campaign', 'channel', 'status', 'status_updated_at']
    search_fields   = ['customer__name', 'campaign__name']
    list_filter     = ['status', 'channel']
    ordering        = ['-created_at']


@admin.register(ChatSession)
class ChatSessionAdmin(admin.ModelAdmin):
    list_display    = ['id', 'session_id', 'created_at', 'updated_at']
    search_fields   = ['session_id']
    ordering        = ['-created_at']