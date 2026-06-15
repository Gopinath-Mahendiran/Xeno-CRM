# crm/views.py
"""
Django REST Framework API views for Xeno CRM.

Endpoints:
  POST   /api/auth/register/             RegisterView
  POST   /api/auth/login/                LoginView
  POST   /api/auth/logout/               LogoutView
  GET    /api/auth/me/                   UserInfoView

  POST   /api/chat/                      ChatAPIView
  GET    /api/chat/sessions/             ChatSessionListView
  POST   /api/chat/sessions/             ChatSessionCreateView
  GET    /api/chat/sessions/{id}/messages/ ChatSessionHistoryView

  GET    /api/customers/                 CustomerListView
  GET    /api/segments/                  SegmentListView
  GET    /api/campaigns/                 CampaignListView
  GET    /api/campaigns/{id}/            CampaignDetailView
  POST   /api/campaigns/{id}/fire/       CampaignFireView
  GET    /api/campaigns/{id}/stats/      CampaignStatsView
  GET    /api/campaigns/{id}/logs/       CampaignLogsView
  POST   /api/receipts/                  ReceiptAPIView
"""

import json
import uuid
import logging

from django.db import transaction
from django.contrib.auth.models import User
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.authtoken.models import Token
from rest_framework import status

from crm.models import (
    Customer, Segment, Campaign, CommunicationLog, ChatSession, ChatMessage
)
from crm.serializers import (
    CustomerSerializer,
    SegmentSerializer,
    CampaignSerializer,
    CampaignListSerializer,
    CommunicationLogSerializer,
    ReceiptSerializer,
    ChatMessageSerializer,
    RegisterSerializer,
    LoginSerializer,
    ChatSessionListSerializer,
    ChatMessageDBSerializer,
)
from crm.tasks import fire_campaign_task

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Auth — Register / Login / Logout / Me
# ─────────────────────────────────────────────────────────────────────────────

class RegisterView(APIView):
    """POST /api/auth/register/"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = RegisterSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user  = serializer.save()
        token = Token.objects.create(user=user)

        return Response({
            "message":  "Registration successful",
            "token":    token.key,
            "user": {
                "id":       user.id,
                "username": user.username,
                "email":    user.email,
            }
        }, status=status.HTTP_201_CREATED)


class LoginView(APIView):
    """POST /api/auth/login/"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = LoginSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = serializer.validated_data['user']
        token, _ = Token.objects.get_or_create(user=user)

        return Response({
            "message": "Login successful",
            "token":   token.key,
            "user": {
                "id":       user.id,
                "username": user.username,
                "email":    user.email,
            }
        })


class LogoutView(APIView):
    """POST /api/auth/logout/"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
        except Exception:
            pass
        return Response({"message": "Logged out successfully"})


class UserInfoView(APIView):
    """GET /api/auth/me/"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            "id":       request.user.id,
            "username": request.user.username,
            "email":    request.user.email,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Chat — main agentic endpoint
# ─────────────────────────────────────────────────────────────────────────────

class ChatAPIView(APIView):
    """
    POST /api/chat/
    Body: { "message": "...", "session_id": "abc" }

    Runs the LangChain agent and returns:
    {
        "reply":        "...",
        "tool_used":    "segment_customers" | null,
        "tool_result":  { ... } | null,
        "session_id":   "abc"
    }
    """
    permission_classes = [AllowAny]  # Supports both authed and anon

    def post(self, request):
        serializer = ChatMessageSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        message    = serializer.validated_data["message"]
        session_id = serializer.validated_data["session_id"]

        # Ensure ChatSession record exists, optionally link to authenticated user
        session, created = ChatSession.objects.get_or_create(session_id=session_id)
        if request.user.is_authenticated and session.user is None:
            session.user = request.user
            session.save(update_fields=['user'])

        # Auto-derive title from first message
        if created or session.title == 'New Chat':
            session.title = message[:60].strip() or 'New Chat'
            session.save(update_fields=['title'])

        try:
            from crm.agent.agent import run_agent
            result = run_agent(message=message, session_id=session_id)
        except Exception as exc:
            logger.error("Agent error: %s", exc)
            return Response(
                {"error": "Agent unavailable. Please check your API key."},
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        # Parse tool_result for storage
        reply       = result.get("reply", "")
        tool_used   = result.get("tool_used")
        tool_result = result.get("tool_result")

        # Parse tool_result if it's a string
        tool_result_parsed = None
        if tool_result:
            try:
                tool_result_parsed = json.loads(tool_result) if isinstance(tool_result, str) else tool_result
            except (json.JSONDecodeError, TypeError):
                tool_result_parsed = tool_result

        # Persist messages to DB
        ChatMessage.objects.create(
            session=session, role='human', content=message
        )
        ChatMessage.objects.create(
            session=session, role='ai', content=reply,
            tool_used=tool_used, tool_result=tool_result_parsed,
        )

        # Touch session updated_at
        session.save(update_fields=['updated_at'])

        return Response({
            **result,
            "session_id": session_id,
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────────────────────
# Chat Sessions — list, create, history
# ─────────────────────────────────────────────────────────────────────────────

class ChatSessionListView(APIView):
    """GET /api/chat/sessions/ — list sessions for the authenticated user."""
    permission_classes = [AllowAny]

    def get(self, request):
        if request.user.is_authenticated:
            sessions = ChatSession.objects.filter(user=request.user).order_by('-updated_at')
        else:
            sessions = ChatSession.objects.none()

        serializer = ChatSessionListSerializer(sessions, many=True)
        return Response({"results": serializer.data})


class ChatSessionCreateView(APIView):
    """POST /api/chat/sessions/ — create a new chat session."""
    permission_classes = [AllowAny]

    def post(self, request):
        new_session_id = f"session-{uuid.uuid4().hex[:12]}"
        title = request.data.get('title', 'New Chat')

        session = ChatSession.objects.create(
            session_id=new_session_id,
            title=title,
            user=request.user if request.user.is_authenticated else None,
        )

        return Response({
            "id":         session.id,
            "session_id": session.session_id,
            "title":      session.title,
            "created_at": session.created_at,
        }, status=status.HTTP_201_CREATED)


class ChatSessionHistoryView(APIView):
    """GET /api/chat/sessions/<session_id>/messages/ — get full message history."""
    permission_classes = [AllowAny]

    def get(self, request, session_id):
        try:
            session = ChatSession.objects.get(session_id=session_id)
        except ChatSession.DoesNotExist:
            return Response({"error": "Session not found"}, status=status.HTTP_404_NOT_FOUND)

        messages = session.messages.all().order_by('created_at')
        serializer = ChatMessageDBSerializer(messages, many=True)
        return Response({
            "session_id": session_id,
            "title":      session.title,
            "results":    serializer.data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Customers
# ─────────────────────────────────────────────────────────────────────────────

class CustomerListView(APIView):
    """GET /api/customers/?search=&city=&page=1&page_size=20"""
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Customer.objects.all().order_by("-created_at")

        search = request.query_params.get("search")
        if search:
            from django.db.models import Q
            qs = qs.filter(
                Q(name__icontains=search) |
                Q(email__icontains=search) |
                Q(phone__icontains=search)
            )

        city = request.query_params.get("city")
        if city:
            qs = qs.filter(city__iexact=city)

        # Simple pagination
        page      = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 20))
        start     = (page - 1) * page_size
        end       = start + page_size
        total     = qs.count()

        serializer = CustomerSerializer(qs[start:end], many=True)
        return Response({
            "count":   total,
            "page":    page,
            "results": serializer.data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Segments
# ─────────────────────────────────────────────────────────────────────────────

class SegmentListView(APIView):
    """GET /api/segments/"""
    permission_classes = [AllowAny]

    def get(self, request):
        qs         = Segment.objects.all().order_by("-created_at")
        serializer = SegmentSerializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})


class SegmentPreviewView(APIView):
    """GET /api/segments/{id}/preview/?page=1&page_size=50 — returns paginated matching customers"""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            segment = Segment.objects.get(pk=pk)
        except Segment.DoesNotExist:
            return Response({"error": "Segment not found"}, status=status.HTTP_404_NOT_FOUND)

        all_customers = segment.get_customers()
        total         = len(all_customers)

        page      = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 50))
        start     = (page - 1) * page_size
        end       = start + page_size

        from crm.serializers import CustomerPreviewSerializer
        serializer = CustomerPreviewSerializer(all_customers[start:end], many=True)
        return Response({
            "segment":        segment.name,
            "natural_query":  segment.natural_query,
            "customer_count": total,
            "page":           page,
            "page_size":      page_size,
            "results":        serializer.data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Campaigns
# ─────────────────────────────────────────────────────────────────────────────

class CampaignListView(APIView):
    """GET /api/campaigns/?status=&channel="""
    permission_classes = [AllowAny]

    def get(self, request):
        qs = Campaign.objects.select_related("segment").order_by("-created_at")

        status_filter  = request.query_params.get("status")
        channel_filter = request.query_params.get("channel")
        if status_filter:
            qs = qs.filter(status=status_filter)
        if channel_filter:
            qs = qs.filter(channel=channel_filter)

        serializer = CampaignListSerializer(qs, many=True)
        return Response({"count": qs.count(), "results": serializer.data})


class CampaignDetailView(APIView):
    """GET /api/campaigns/{id}/"""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            campaign = Campaign.objects.select_related("segment").get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

        serializer = CampaignSerializer(campaign)
        return Response(serializer.data)


class CampaignFireView(APIView):
    """
    POST /api/campaigns/{id}/fire/

    Sends the campaign to Celery for async dispatch.
    The marketer calls this after confirming from the chat UI.
    """
    permission_classes = [AllowAny]

    def post(self, request, pk):
        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

        if campaign.status == "running":
            return Response(
                {"error": "Campaign is already running"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if campaign.status == "completed":
            return Response(
                {"error": "Campaign already completed. Duplicate sends are prevented."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Fire async Celery task
        fire_campaign_task.delay(campaign.id)

        logger.info("Campaign %s queued for delivery", campaign.id)
        return Response({
            "message":     f"Campaign '{campaign.name}' queued for delivery.",
            "campaign_id": campaign.id,
            "status":      "queued",
        }, status=status.HTTP_202_ACCEPTED)


class CampaignStatsView(APIView):
    """GET /api/campaigns/{id}/stats/"""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        from crm.services.campaign import get_campaign_stats
        stats = get_campaign_stats(pk)
        if "error" in stats:
            return Response(stats, status=status.HTTP_404_NOT_FOUND)
        return Response(stats)


class CampaignLogsView(APIView):
    """GET /api/campaigns/{id}/logs/?status="""
    permission_classes = [AllowAny]

    def get(self, request, pk):
        try:
            campaign = Campaign.objects.get(pk=pk)
        except Campaign.DoesNotExist:
            return Response({"error": "Campaign not found"}, status=status.HTTP_404_NOT_FOUND)

        logs = campaign.logs.select_related("customer").order_by("-created_at")

        status_filter = request.query_params.get("status")
        if status_filter:
            logs = logs.filter(status=status_filter)

        # Pagination
        page      = int(request.query_params.get("page", 1))
        page_size = int(request.query_params.get("page_size", 50))
        start     = (page - 1) * page_size
        end       = start + page_size
        total     = logs.count()

        serializer = CommunicationLogSerializer(logs[start:end], many=True)
        return Response({
            "campaign_id": pk,
            "count":       total,
            "page":        page,
            "results":     serializer.data,
        })


# ─────────────────────────────────────────────────────────────────────────────
# Receipts — delivery callbacks from channel service
# ─────────────────────────────────────────────────────────────────────────────

class ReceiptAPIView(APIView):
    """
    POST /api/receipts/
    Body: { "message_id": "<uuid>", "status": "delivered" | "read" | ... }

    Called by the channel_service microservice to update delivery status.
    Updates CommunicationLog + Campaign aggregate counters.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ReceiptSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        message_id = serializer.validated_data["message_id"]
        new_status = serializer.validated_data["status"]

        try:
            with transaction.atomic():
                log = CommunicationLog.objects.select_for_update().select_related("campaign").get(
                    message_id=message_id
                )

                # Enforce monotonic status progression
                if not log.can_advance_to(new_status):
                    return Response({
                        "message":     "Status not advanced (already at same or higher rank)",
                        "current":     log.status,
                        "requested":   new_status,
                    }, status=status.HTTP_200_OK)

                old_status     = log.status
                log.status     = new_status
                log.save(update_fields=["status"])

                # Update campaign aggregate counter
                from crm.services.campaign import _update_campaign_counter
                _update_campaign_counter(log.campaign, old_status, new_status)
        except CommunicationLog.DoesNotExist:
            return Response(
                {"error": f"Message {message_id} not found"},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response({
            "message":     "Status updated",
            "message_id":  str(message_id),
            "old_status":  old_status,
            "new_status":  new_status,
        })


class AgentInfoView(APIView):
    """
    GET /api/agent/info/
    Returns whether local or Gemini LLM is active and its details.
    """
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings
        if settings.USE_LOCAL_LLM:
            return Response({
                "provider": settings.LOCAL_LLM_PROVIDER,
                "model": settings.LOCAL_LLM_MODEL,
                "api_base": settings.LOCAL_LLM_API_BASE,
                "is_local": True
            })
        else:
            return Response({
                "provider": "google",
                "model": "gemini-2.5-flash",
                "is_local": False
            })