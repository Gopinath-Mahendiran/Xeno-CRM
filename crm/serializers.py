# crm/serializers.py

from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from .models import Customer, Order, Segment, Campaign, CommunicationLog, ChatSession, ChatMessage


class OrderSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Order
        fields = ['id', 'amount', 'status', 'ordered_at', 'created_at']


class CustomerSerializer(serializers.ModelSerializer):
    orders = OrderSerializer(many=True, read_only=True)

    class Meta:
        model  = Customer
        fields = [
            'id', 'name', 'email', 'phone', 'city',
            'total_spent', 'order_count', 'last_order_at',
            'created_at', 'orders'
        ]

class CustomerPreviewSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Customer
        fields = ['id', 'name', 'email', 'phone', 'city', 'total_spent', 'order_count', 'last_order_at']


class SegmentSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Segment
        fields = ['id', 'name', 'natural_query', 'customer_count', 'created_at']


class CampaignSerializer(serializers.ModelSerializer):
    segment         = SegmentSerializer(read_only=True)
    delivery_rate   = serializers.ReadOnlyField()
    read_rate       = serializers.ReadOnlyField()
    click_rate      = serializers.ReadOnlyField()

    class Meta:
        model  = Campaign
        fields = [
            'id', 'name', 'segment', 'message_template', 'channel', 'status',
            'sent_count', 'delivered_count', 'failed_count',
            'read_count', 'clicked_count', 'order_count',
            'delivery_rate', 'read_rate', 'click_rate',
            'created_at', 'updated_at'
        ]


class CampaignListSerializer(serializers.ModelSerializer):
    segment         = SegmentSerializer(read_only=True)
    delivery_rate   = serializers.ReadOnlyField()
    read_rate       = serializers.ReadOnlyField()
    click_rate      = serializers.ReadOnlyField()

    class Meta:
        model  = Campaign
        fields = [
            'id', 'name', 'segment', 'message_template', 'channel', 'status',
            'sent_count', 'delivered_count', 'failed_count',
            'read_count', 'clicked_count', 'order_count',
            'delivery_rate', 'read_rate', 'click_rate',
            'created_at'
        ]


class CommunicationLogSerializer(serializers.ModelSerializer):
    customer = CustomerPreviewSerializer(read_only=True)

    class Meta:
        model  = CommunicationLog
        fields = [
            'id', 'message_id', 'customer', 'channel',
            'message_body', 'status', 'status_updated_at', 'created_at'
        ]


class ReceiptSerializer(serializers.Serializer):
    message_id  = serializers.UUIDField()
    status      = serializers.ChoiceField(choices=[
        'sent', 'failed', 'delivered', 'read', 'clicked', 'ordered'
    ])


class ChatMessageSerializer(serializers.Serializer):
    """Serializer for incoming chat requests."""
    message     = serializers.CharField()
    session_id  = serializers.CharField(default='default')


class ChatSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model  = ChatSession
        fields = ['id', 'session_id', 'created_at', 'updated_at']


# ─────────────────────────────────────────────────────────────────────────────
# Auth Serializers
# ─────────────────────────────────────────────────────────────────────────────

class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email    = serializers.EmailField()
    password = serializers.CharField(min_length=6, write_only=True)

    def validate_username(self, value):
        if User.objects.filter(username=value).exists():
            raise serializers.ValidationError("Username already taken.")
        return value

    def validate_email(self, value):
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Email already registered.")
        return value

    def create(self, validated_data):
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
        )
        return user


class LoginSerializer(serializers.Serializer):
    username = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, attrs):
        user = authenticate(
            username=attrs['username'],
            password=attrs['password'],
        )
        if not user:
            raise serializers.ValidationError("Invalid username or password.")
        attrs['user'] = user
        return attrs


# ─────────────────────────────────────────────────────────────────────────────
# Chat Persistence Serializers
# ─────────────────────────────────────────────────────────────────────────────

class ChatMessageDBSerializer(serializers.ModelSerializer):
    """Serializer for stored ChatMessage records."""
    class Meta:
        model  = ChatMessage
        fields = ['id', 'role', 'content', 'tool_used', 'tool_result', 'created_at']


class ChatSessionListSerializer(serializers.ModelSerializer):
    """Serializer for listing user chat sessions with metadata."""
    message_count = serializers.SerializerMethodField()
    last_message  = serializers.SerializerMethodField()

    class Meta:
        model  = ChatSession
        fields = ['id', 'session_id', 'title', 'message_count', 'last_message', 'created_at', 'updated_at']

    def get_message_count(self, obj):
        return obj.messages.count()

    def get_last_message(self, obj):
        last = obj.messages.order_by('-created_at').first()
        if last:
            return last.content[:80]
        return None