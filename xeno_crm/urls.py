"""
URL configuration for xeno_crm project.

All /api/* routes → DRF views
Everything else   → React SPA (index.html served by WhiteNoise / Django)
"""

from django.contrib import admin
from django.urls import path, re_path
from django.views.generic import TemplateView
from django.conf import settings
from django.conf.urls.static import static

from crm.views import (
    # Auth
    RegisterView,
    LoginView,
    LogoutView,
    UserInfoView,
    # Chat
    ChatAPIView,
    ChatSessionListView,
    ChatSessionCreateView,
    ChatSessionHistoryView,
    # Data
    CustomerListView,
    SegmentListView,
    SegmentPreviewView,
    CampaignListView,
    CampaignDetailView,
    CampaignFireView,
    CampaignStatsView,
    CampaignLogsView,
    ReceiptAPIView,
    AgentInfoView,
)

urlpatterns = [
    # Django admin
    path("admin/", admin.site.urls),

    # ── Auth ─────────────────────────────────────────────────────────
    path("api/auth/register/",  RegisterView.as_view(),  name="auth-register"),
    path("api/auth/login/",     LoginView.as_view(),     name="auth-login"),
    path("api/auth/logout/",    LogoutView.as_view(),    name="auth-logout"),
    path("api/auth/me/",        UserInfoView.as_view(),  name="auth-me"),

    # ── Chat (Agentic) ───────────────────────────────────────────────
    path("api/chat/",                    ChatAPIView.as_view(),            name="chat"),
    path("api/chat/sessions/",           ChatSessionListView.as_view(),    name="chat-sessions-list"),
    path("api/chat/sessions/create/",    ChatSessionCreateView.as_view(),  name="chat-sessions-create"),
    path("api/chat/sessions/<str:session_id>/messages/",
         ChatSessionHistoryView.as_view(), name="chat-session-history"),
    path("api/agent/info/",              AgentInfoView.as_view(),          name="agent-info"),

    # ── Customers ────────────────────────────────────────────────────
    path("api/customers/",              CustomerListView.as_view(),    name="customers-list"),

    # ── Segments ─────────────────────────────────────────────────────
    path("api/segments/",                   SegmentListView.as_view(),    name="segments-list"),
    path("api/segments/<int:pk>/preview/",  SegmentPreviewView.as_view(), name="segment-preview"),

    # ── Campaigns ────────────────────────────────────────────────────
    path("api/campaigns/",               CampaignListView.as_view(),   name="campaigns-list"),
    path("api/campaigns/<int:pk>/",      CampaignDetailView.as_view(), name="campaign-detail"),
    path("api/campaigns/<int:pk>/fire/", CampaignFireView.as_view(),   name="campaign-fire"),
    path("api/campaigns/<int:pk>/stats/",CampaignStatsView.as_view(),  name="campaign-stats"),
    path("api/campaigns/<int:pk>/logs/", CampaignLogsView.as_view(),   name="campaign-logs"),

    # ── Delivery Receipts (channel service callbacks) ─────────────────
    path("api/receipts/",               ReceiptAPIView.as_view(),      name="receipts"),

    # ── Static/Public Files served from template folder ──────────────
    path("favicon.svg", TemplateView.as_view(template_name="favicon.svg", content_type="image/svg+xml")),
    path("icons.svg", TemplateView.as_view(template_name="icons.svg", content_type="image/svg+xml")),

    # ── React SPA catch-all ──────────────────────────────────────────
    # All non-API routes serve index.html so React Router can handle them
    re_path(r"^(?!api/).*$", TemplateView.as_view(template_name="index.html"), name="frontend"),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
