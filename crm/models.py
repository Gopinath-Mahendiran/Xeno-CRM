from django.db import models
import uuid
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    name            = models.CharField(max_length=255)
    email           = models.EmailField(unique=True)
    phone           = models.CharField(max_length=20)
    city            = models.CharField(max_length=100, blank=True)
    total_spent     = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    order_count     = models.IntegerField(default=0)
    last_order_at   = models.DateTimeField(null=True, blank=True)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.email})"


class Order(models.Model):
    STATUS_CHOICES = [
        ('completed', 'Completed'),
        ('returned',  'Returned'),
        ('cancelled', 'Cancelled'),
    ]

    customer    = models.ForeignKey(Customer, related_name='orders', on_delete=models.CASCADE)
    amount      = models.DecimalField(max_digits=10, decimal_places=2)
    status      = models.CharField(max_length=50, choices=STATUS_CHOICES, default='completed')
    ordered_at  = models.DateTimeField()
    created_at  = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Order #{self.id} - {self.customer.name} - ₹{self.amount}"


class Segment(models.Model):
    name            = models.CharField(max_length=255)
    natural_query   = models.TextField()
    sql_filter      = models.TextField()
    customer_count  = models.IntegerField(default=0)
    created_at      = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.name} ({self.customer_count} customers)"

    def get_customers(self):
        from crm.services.segmentation import apply_filters
        import json
        filters = json.loads(self.sql_filter)
        return apply_filters(filters)


class Campaign(models.Model):
    STATUS_CHOICES = [
        ('draft',     'Draft'),
        ('running',   'Running'),
        ('completed', 'Completed'),
    ]

    CHANNEL_CHOICES = [
        ('whatsapp', 'WhatsApp'),
        ('sms',      'SMS'),
        ('email',    'Email'),
        ('rcs',      'RCS'),
    ]

    name                = models.CharField(max_length=255)
    segment             = models.ForeignKey(Segment, on_delete=models.CASCADE)
    message_template    = models.TextField()
    channel             = models.CharField(max_length=20, choices=CHANNEL_CHOICES, default='whatsapp')
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='draft')

    # Aggregate stats — updated on every callback
    sent_count          = models.IntegerField(default=0)
    delivered_count     = models.IntegerField(default=0)
    failed_count        = models.IntegerField(default=0)
    read_count          = models.IntegerField(default=0)
    clicked_count       = models.IntegerField(default=0)
    order_count         = models.IntegerField(default=0)

    created_at          = models.DateTimeField(auto_now_add=True)
    updated_at          = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.name} [{self.status}]"

    @property
    def delivery_rate(self):
        if self.sent_count == 0:
            return 0
        return round((self.delivered_count / self.sent_count) * 100, 1)

    @property
    def read_rate(self):
        if self.delivered_count == 0:
            return 0
        return round((self.read_count / self.delivered_count) * 100, 1)

    @property
    def click_rate(self):
        if self.read_count == 0:
            return 0
        return round((self.clicked_count / self.read_count) * 100, 1)


class CommunicationLog(models.Model):
    STATUS_CHOICES = [
        ('pending',   'Pending'),
        ('sent',      'Sent'),
        ('failed',    'Failed'),
        ('delivered', 'Delivered'),
        ('read',      'Read'),
        ('clicked',   'Clicked'),
        ('ordered',   'Ordered'),
    ]

    STATUS_RANK = {
        'pending':   0,
        'sent':      1,
        'failed':    2,
        'delivered': 3,
        'read':      4,
        'clicked':   5,
        'ordered':   6,
    }

    message_id          = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    campaign            = models.ForeignKey(Campaign, related_name='logs', on_delete=models.CASCADE)
    customer            = models.ForeignKey(Customer, related_name='logs', on_delete=models.CASCADE)
    channel             = models.CharField(max_length=20)
    message_body        = models.TextField()
    status              = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending')
    status_updated_at   = models.DateTimeField(auto_now=True)
    created_at          = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.message_id} → {self.customer.name} [{self.status}]"

    def can_advance_to(self, new_status: str) -> bool:
        return self.STATUS_RANK.get(new_status, -1) > self.STATUS_RANK.get(self.status, -1)


class ChatSession(models.Model):
    session_id  = models.CharField(max_length=100, unique=True)
    user        = models.ForeignKey(
        'auth.User', related_name='chat_sessions',
        on_delete=models.CASCADE, null=True, blank=True
    )
    title       = models.CharField(max_length=120, default='New Chat')
    created_at  = models.DateTimeField(auto_now_add=True)
    updated_at  = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def __str__(self):
        return f"Session {self.session_id} — {self.title}"


class ChatMessage(models.Model):
    ROLE_CHOICES = [
        ('human', 'Human'),
        ('ai',    'AI'),
    ]

    session     = models.ForeignKey(ChatSession, related_name='messages', on_delete=models.CASCADE)
    role        = models.CharField(max_length=10, choices=ROLE_CHOICES)
    content     = models.TextField()
    tool_used   = models.CharField(max_length=60, null=True, blank=True)
    tool_result = models.JSONField(null=True, blank=True)
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f"[{self.role}] {self.content[:50]}"