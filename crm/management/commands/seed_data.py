"""
Management command: seed_data
Usage: python manage.py seed_data

Populates the database with realistic sample data:
  - 500 Customers
  - ~1200 Orders  (1-5 per customer)
  - 8  Segments
  - 10 Campaigns  (linked to segments)
  - CommunicationLogs for every campaign × customer in segment
"""

import json
import random
import uuid
from datetime import timedelta
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.utils import timezone

from crm.models import (
    Campaign,
    ChatSession,
    CommunicationLog,
    Customer,
    Order,
    Segment,
)

# ──────────────────────────────────────────────────────────────────────────────
# Static name pools
# ──────────────────────────────────────────────────────────────────────────────
FIRST_NAMES = [
    "Aarav", "Vivaan", "Aditya", "Vihaan", "Arjun", "Sai", "Reyansh",
    "Ayaan", "Krishna", "Ishaan", "Priya", "Ananya", "Isha", "Khushi",
    "Diya", "Meera", "Pooja", "Neha", "Sneha", "Riya", "Rahul",
    "Rohan", "Karan", "Amit", "Suresh", "Ramesh", "Vijay", "Raj",
    "Nikhil", "Deepak", "Anjali", "Shruti", "Kavya", "Nisha", "Simran",
    "Preeti", "Swati", "Pallavi", "Divya", "Komal", "Aryan", "Dev",
    "Harshit", "Manish", "Akash", "Vishal", "Gaurav", "Rohit", "Shyam",
    "Mohan", "Lakshmi", "Sunita", "Geeta", "Radha", "Sita", "Parvati",
    "Usha", "Rekha", "Jyoti", "Savita",
]

LAST_NAMES = [
    "Sharma", "Verma", "Gupta", "Singh", "Kumar", "Patel", "Shah",
    "Mehta", "Joshi", "Rao", "Nair", "Pillai", "Menon", "Iyer",
    "Reddy", "Naidu", "Choudhury", "Mishra", "Pandey", "Tiwari",
    "Agarwal", "Bose", "Ghosh", "Chatterjee", "Banerjee", "Das",
    "Sen", "Roy", "Sinha", "Dutta", "Malhotra", "Chopra", "Kapoor",
    "Bajaj", "Birla", "Tata", "Ambani", "Adani", "Khanna", "Tandon",
]

CITIES = [
    "Mumbai", "Delhi", "Bangalore", "Hyderabad", "Chennai", "Kolkata",
    "Pune", "Ahmedabad", "Jaipur", "Surat", "Lucknow", "Kanpur",
    "Nagpur", "Indore", "Bhopal", "Patna", "Vadodara", "Coimbatore",
    "Agra", "Nashik", "Meerut", "Ranchi", "Guwahati", "Chandigarh",
    "Mysore", "Noida", "Gurgaon", "Kochi", "Visakhapatnam", "Bhubaneswar",
]

EMAIL_DOMAINS = [
    "gmail.com", "yahoo.com", "hotmail.com", "outlook.com",
    "rediffmail.com", "icloud.com", "protonmail.com",
]

# ──────────────────────────────────────────────────────────────────────────────
# Segment presets  (natural language → JSON filter structure)
# ──────────────────────────────────────────────────────────────────────────────
SEGMENTS = [
    {
        "name": "High Value Customers",
        "natural_query": "Customers who have spent more than ₹10,000",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [{"field": "total_spent", "operator": "gt", "value": 10000}],
        }),
    },
    {
        "name": "Frequent Shoppers",
        "natural_query": "Customers with more than 5 orders",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [{"field": "order_count", "operator": "gt", "value": 5}],
        }),
    },
    {
        "name": "Dormant Customers",
        "natural_query": "Customers who haven't ordered in the last 90 days",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [{"field": "last_order_at", "operator": "lt_days_ago", "value": 90}],
        }),
    },
    {
        "name": "New Customers",
        "natural_query": "Customers who joined in the last 30 days",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [{"field": "created_at", "operator": "gt_days_ago", "value": 30}],
        }),
    },
    {
        "name": "Mumbai VIPs",
        "natural_query": "High spenders from Mumbai",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [
                {"field": "city", "operator": "eq", "value": "Mumbai"},
                {"field": "total_spent", "operator": "gt", "value": 5000},
            ],
        }),
    },
    {
        "name": "At-Risk Customers",
        "natural_query": "Customers with exactly 1 order placed over 60 days ago",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [
                {"field": "order_count", "operator": "eq", "value": 1},
                {"field": "last_order_at", "operator": "lt_days_ago", "value": 60},
            ],
        }),
    },
    {
        "name": "Bangalore Shoppers",
        "natural_query": "All customers from Bangalore",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [{"field": "city", "operator": "eq", "value": "Bangalore"}],
        }),
    },
    {
        "name": "Big Spenders (₹25k+)",
        "natural_query": "Customers who have spent more than ₹25,000 total",
        "sql_filter": json.dumps({
            "operator": "AND",
            "rules": [{"field": "total_spent", "operator": "gt", "value": 25000}],
        }),
    },
]

# ──────────────────────────────────────────────────────────────────────────────
# Campaign templates  (one per segment, cycling through channels)
# ──────────────────────────────────────────────────────────────────────────────
CAMPAIGN_TEMPLATES = [
    {
        "name": "VIP Loyalty Rewards",
        "message_template": "Hi {name}, as one of our top customers you've unlocked exclusive rewards! Use code VIP20 for 20% off your next purchase. 🎁",
        "channel": "whatsapp",
        "status": "completed",
    },
    {
        "name": "Frequent Buyer Bonus",
        "message_template": "Hey {name}! You're on a roll 🔥 Buy 2 more items and get free shipping on your next 3 orders!",
        "channel": "email",
        "status": "completed",
    },
    {
        "name": "We Miss You Campaign",
        "message_template": "Hi {name}, it's been a while! Come back and enjoy flat ₹200 off on orders above ₹999. Valid for 7 days only. ⏰",
        "channel": "sms",
        "status": "completed",
    },
    {
        "name": "Welcome New Members",
        "message_template": "Welcome to Xeno CRM, {name}! 🎉 Here's a special 15% off coupon for your first purchase: WELCOME15. Happy shopping!",
        "channel": "email",
        "status": "running",
    },
    {
        "name": "Mumbai Exclusive Offers",
        "message_template": "Hello {name}! Mumbai shoppers get exclusive access to our Flash Sale starting tonight at 8 PM. Shop early, save big! 🛍️",
        "channel": "whatsapp",
        "status": "completed",
    },
    {
        "name": "Win-Back At-Risk",
        "message_template": "Hi {name}, we noticed you've been away. Here's a personalised offer just for you: 25% off + free returns. Don't miss out!",
        "channel": "rcs",
        "status": "completed",
    },
    {
        "name": "Bangalore Local Deals",
        "message_template": "Hey {name}, exclusive Bangalore deals are live! Visit our Indiranagar or Koramangala store for extra 10% off. Show this message! 📍",
        "channel": "sms",
        "status": "running",
    },
    {
        "name": "Premium Members Sale",
        "message_template": "Dear {name}, our Premium-only sale is live now! Up to 40% off on top brands. Your loyalty deserves the best. Shop now 👑",
        "channel": "email",
        "status": "completed",
    },
    {
        "name": "Summer Collection Launch",
        "message_template": "Hi {name}! ☀️ Our Summer 2026 collection just dropped. Be the first to grab your favourites before they sell out!",
        "channel": "whatsapp",
        "status": "draft",
    },
    {
        "name": "Referral Bonus Drive",
        "message_template": "Hey {name}, refer a friend and both of you get ₹500 off! Share your link: xeno.crm/ref/{name_slug}. Limited time offer! 🔗",
        "channel": "rcs",
        "status": "running",
    },
]

LOG_STATUSES = ["sent", "delivered", "read", "clicked", "ordered", "failed"]
LOG_STATUS_WEIGHTS = [5, 30, 30, 20, 10, 5]


class Command(BaseCommand):
    help = "Seed the database with 500 sample customers plus related data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Delete existing data before seeding.",
        )

    # ------------------------------------------------------------------
    def handle(self, *args, **options):
        if options["clear"]:
            self.stdout.write(self.style.WARNING("Clearing existing data …"))
            CommunicationLog.objects.all().delete()
            Campaign.objects.all().delete()
            Segment.objects.all().delete()
            Order.objects.all().delete()
            Customer.objects.all().delete()
            ChatSession.objects.all().delete()
            self.stdout.write(self.style.SUCCESS("Cleared."))

        now = timezone.now()

        # ── 1. Customers ──────────────────────────────────────────────
        self.stdout.write("Creating 500 customers …")
        customers = []
        used_emails = set(Customer.objects.values_list("email", flat=True))

        for i in range(500):
            first = random.choice(FIRST_NAMES)
            last = random.choice(LAST_NAMES)
            name = f"{first} {last}"

            # Guarantee a unique email
            base = f"{first.lower()}.{last.lower()}{random.randint(1, 9999)}"
            domain = random.choice(EMAIL_DOMAINS)
            email = f"{base}@{domain}"
            while email in used_emails:
                email = f"{first.lower()}.{last.lower()}{random.randint(1, 99999)}@{domain}"
            used_emails.add(email)

            phone = f"+91{random.randint(7000000000, 9999999999)}"
            city = random.choice(CITIES)
            created_at = now - timedelta(days=random.randint(1, 730))

            customers.append(
                Customer(
                    name=name,
                    email=email,
                    phone=phone,
                    city=city,
                    total_spent=Decimal("0.00"),
                    order_count=0,
                    last_order_at=None,
                    created_at=created_at,
                )
            )

        Customer.objects.bulk_create(customers, ignore_conflicts=True)
        all_customers = list(Customer.objects.all())
        self.stdout.write(self.style.SUCCESS(f"  Created {len(all_customers)} customers."))

        # ── 2. Orders ─────────────────────────────────────────────────
        self.stdout.write("Creating orders …")
        orders = []
        customer_stats: dict[int, dict] = {}

        for customer in all_customers:
            n_orders = random.randint(0, 7)
            last_order_dt = None
            total = Decimal("0.00")

            for _ in range(n_orders):
                amount = Decimal(str(round(random.uniform(199, 8999), 2)))
                status = random.choices(
                    ["completed", "returned", "cancelled"],
                    weights=[75, 15, 10],
                )[0]
                days_ago = random.randint(1, 365)
                ordered_at = now - timedelta(days=days_ago, hours=random.randint(0, 23))
                orders.append(
                    Order(
                        customer=customer,
                        amount=amount,
                        status=status,
                        ordered_at=ordered_at,
                    )
                )
                if status == "completed":
                    total += amount
                if last_order_dt is None or ordered_at > last_order_dt:
                    last_order_dt = ordered_at

            customer_stats[customer.pk] = {
                "total_spent": total,
                "order_count": n_orders,
                "last_order_at": last_order_dt,
            }

        Order.objects.bulk_create(orders)
        self.stdout.write(self.style.SUCCESS(f"  Created {len(orders)} orders."))

        # ── 3. Update customer aggregates ─────────────────────────────
        self.stdout.write("Updating customer aggregate stats …")
        for customer in all_customers:
            stats = customer_stats.get(customer.pk, {})
            customer.total_spent = stats.get("total_spent", Decimal("0.00"))
            customer.order_count = stats.get("order_count", 0)
            customer.last_order_at = stats.get("last_order_at")

        Customer.objects.bulk_update(
            all_customers, ["total_spent", "order_count", "last_order_at"]
        )
        self.stdout.write(self.style.SUCCESS("  Done."))

        # ── 4. Segments ───────────────────────────────────────────────
        self.stdout.write("Creating segments …")
        segment_objects = []
        for seg in SEGMENTS:
            obj, _ = Segment.objects.get_or_create(
                name=seg["name"],
                defaults={
                    "natural_query": seg["natural_query"],
                    "sql_filter": seg["sql_filter"],
                    "customer_count": random.randint(20, 150),
                },
            )
            segment_objects.append(obj)
        self.stdout.write(self.style.SUCCESS(f"  Created {len(segment_objects)} segments."))

        # ── 5. Campaigns ──────────────────────────────────────────────
        self.stdout.write("Creating campaigns …")
        campaign_objects = []
        for idx, tmpl in enumerate(CAMPAIGN_TEMPLATES):
            segment = segment_objects[idx % len(segment_objects)]
            obj, _ = Campaign.objects.get_or_create(
                name=tmpl["name"],
                defaults={
                    "segment": segment,
                    "message_template": tmpl["message_template"],
                    "channel": tmpl["channel"],
                    "status": tmpl["status"],
                    "sent_count": random.randint(50, 300),
                    "delivered_count": random.randint(40, 280),
                    "failed_count": random.randint(1, 20),
                    "read_count": random.randint(30, 200),
                    "clicked_count": random.randint(10, 100),
                    "order_count": random.randint(5, 50),
                },
            )
            campaign_objects.append(obj)
        self.stdout.write(self.style.SUCCESS(f"  Created {len(campaign_objects)} campaigns."))

        # ── 6. Communication Logs ─────────────────────────────────────
        self.stdout.write("Creating communication logs …")
        logs = []
        sample_customers = random.sample(all_customers, min(200, len(all_customers)))

        for campaign in campaign_objects:
            assigned = random.sample(sample_customers, min(30, len(sample_customers)))
            for customer in assigned:
                status = random.choices(LOG_STATUSES, weights=LOG_STATUS_WEIGHTS)[0]
                logs.append(
                    CommunicationLog(
                        message_id=uuid.uuid4(),
                        campaign=campaign,
                        customer=customer,
                        channel=campaign.channel,
                        message_body=campaign.message_template.replace(
                            "{name}", customer.name.split()[0]
                        ).replace("{name_slug}", customer.name.split()[0].lower()),
                        status=status,
                    )
                )

        CommunicationLog.objects.bulk_create(logs, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"  Created {len(logs)} communication logs."))

        # ── 7. Chat Sessions ──────────────────────────────────────────
        self.stdout.write("Creating chat sessions …")
        sessions = []
        for i in range(20):
            sessions.append(
                ChatSession(session_id=f"session_{uuid.uuid4().hex[:12]}")
            )
        ChatSession.objects.bulk_create(sessions, ignore_conflicts=True)
        self.stdout.write(self.style.SUCCESS(f"  Created {len(sessions)} chat sessions."))

        # ── Summary ───────────────────────────────────────────────────
        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS("═" * 50))
        self.stdout.write(self.style.SUCCESS("  Seed complete! Summary:"))
        self.stdout.write(f"    Customers  : {Customer.objects.count()}")
        self.stdout.write(f"    Orders     : {Order.objects.count()}")
        self.stdout.write(f"    Segments   : {Segment.objects.count()}")
        self.stdout.write(f"    Campaigns  : {Campaign.objects.count()}")
        self.stdout.write(f"    Comm Logs  : {CommunicationLog.objects.count()}")
        self.stdout.write(f"    Sessions   : {ChatSession.objects.count()}")
        self.stdout.write(self.style.SUCCESS("═" * 50))
