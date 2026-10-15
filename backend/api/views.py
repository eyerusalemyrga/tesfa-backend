import secrets
from rest_framework import generics, status, parsers, viewsets, mixins
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework_simplejwt.tokens import RefreshToken
from django.conf import settings
from django.core.cache import cache
from django.core.mail import send_mail
from django.db import transaction
from django.shortcuts import get_object_or_404
from drf_spectacular.utils import extend_schema, OpenApiParameter
from users.models import User
from conversations.models import Conversation, Message
from .permissions import IsAdmin
from . import tesfa_data
from .tesfa_client import query_tesfa, TesfaAIError
from .serializers import (
    UserSerializer, ProfileSerializer, SignupSerializer, LoginSerializer,
    ForgotPasswordSerializer, VerifyCodeSerializer, ResetPasswordSerializer,
    ConversationSerializer, ConversationDetailSerializer, MessageSerializer,
    QuerySerializer, ChartSerializer, CountrySerializer,
    CountryDetailSerializer, GraphsSerializer,
)

USER_PARSERS = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)


# ---------- Auth ----------

class SignupView(generics.CreateAPIView):
    """Health professionals register themselves."""
    serializer_class = SignupSerializer
    permission_classes = [AllowAny]
    parser_classes = USER_PARSERS

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Registration successful."}, status=status.HTTP_201_CREATED)


class LoginView(generics.GenericAPIView):
    serializer_class = LoginSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.validated_data["user"]
        refresh = RefreshToken.for_user(user)
        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": UserSerializer(user, context={"request": request}).data,
        })


class ForgotPasswordView(generics.GenericAPIView):
    serializer_class = ForgotPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = User.objects.get(email=serializer.validated_data["email"])
        otp = f"{secrets.randbelow(9000) + 1000}"
        cache.set(f"otp_{user.id}", otp, timeout=600)
        send_mail(
            "Your Tesfa OTP Code",
            f"Use this OTP to reset your password: {otp}\nIt expires in 10 minutes.",
            settings.DEFAULT_FROM_EMAIL,
            [user.email],
            fail_silently=False,
        )
        return Response({"message": "OTP sent to your email"})


class VerifyCodeView(generics.GenericAPIView):
    serializer_class = VerifyCodeSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        return Response({"message": "OTP verified successfully"})


class ResetPasswordView(generics.GenericAPIView):
    serializer_class = ResetPasswordSerializer
    permission_classes = [AllowAny]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response({"message": "Password has been reset successfully"})


# ---------- Users ----------

class ProfileView(generics.RetrieveUpdateAPIView):
    """The logged-in user's own profile."""
    serializer_class = ProfileSerializer
    permission_classes = [IsAuthenticated]
    parser_classes = USER_PARSERS

    def get_object(self):
        return self.request.user


class UserViewSet(viewsets.ModelViewSet):
    """Admins manage all users (filter with ?user_type=Admin or ?user_type=Health Professional)."""
    serializer_class = UserSerializer
    permission_classes = [IsAdmin]
    parser_classes = USER_PARSERS

    def get_queryset(self):
        queryset = User.objects.all().order_by('-date_joined')
        user_type = self.request.query_params.get('user_type')
        if user_type:
            queryset = queryset.filter(user_type=user_type)
        return queryset


# ---------- Tesfa AI conversations ----------

class ConversationViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin,
                          mixins.UpdateModelMixin, mixins.DestroyModelMixin,
                          viewsets.GenericViewSet):
    """A user's conversations with Tesfa AI. Admins can see everyone's."""
    queryset = Conversation.objects.none()
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Conversation.objects.all()
        if not self.request.user.is_admin:
            queryset = queryset.filter(user=self.request.user)
        return queryset

    def get_serializer_class(self):
        if self.action == 'retrieve':
            return ConversationDetailSerializer
        return ConversationSerializer


class QueryView(generics.GenericAPIView):
    """Ask Tesfa AI a question. Saves the question and answer in a conversation."""
    serializer_class = QuerySerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(request=QuerySerializer, responses=MessageSerializer)
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        region = data.get("region") or None
        conflict_type = data.get("conflict_type") or None

        conversation = None
        if data.get("conversation_id"):
            conversation = get_object_or_404(Conversation, pk=data["conversation_id"], user=request.user)

        try:
            answer = query_tesfa(data["query"], region, conflict_type)
        except TesfaAIError as e:
            return Response({"detail": str(e)}, status=e.status_code)

        with transaction.atomic():
            if conversation is None:
                conversation = Conversation.objects.create(user=request.user, title=data["query"][:255])
            Message.objects.create(
                conversation=conversation, role='user', content=data["query"],
                region=region or '', conflict_type=conflict_type or '',
            )
            reply = Message.objects.create(
                conversation=conversation, role='assistant', content=answer["analysis_text"],
                region=region or '', conflict_type=conflict_type or '',
                metrics=answer["metrics"], top_conflicts=answer["top_conflicts"],
                chart=answer["chart"], countries=answer["countries"],
            )
            conversation.save(update_fields=['updated_at'])

        return Response(MessageSerializer(reply).data, status=status.HTTP_201_CREATED)


class ChartListView(generics.ListAPIView):
    """Tesfa AI answers that contain countries and chart data (filter with ?country=Sudan)."""
    serializer_class = ChartSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        queryset = Message.objects.filter(role='assistant', chart__isnull=False).select_related('conversation').order_by('-created_at')
        if not self.request.user.is_admin:
            queryset = queryset.filter(conversation__user=self.request.user)
        country = self.request.query_params.get('country')
        if country:
            ids = [m.id for m in queryset if country.lower() in (c.lower() for c in m.countries)]
            queryset = queryset.filter(id__in=ids)
        return queryset


# ---------- Countries & graphs (read from Tesfa AI's database) ----------

class CountryListView(generics.GenericAPIView):
    """All countries in the Tesfa database, with conflict and risk stats."""
    serializer_class = CountrySerializer
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        return Response(self.get_serializer(tesfa_data.list_countries(), many=True).data)


class CountryDetailView(generics.GenericAPIView):
    """One country's stats and its highest-risk conflicts (?limit=50)."""
    serializer_class = CountryDetailSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(operation_id='countries_detail', parameters=[OpenApiParameter('limit', int, description='Max conflicts to return (default 50, max 500)')])
    def get(self, request, pk, *args, **kwargs):
        try:
            limit = min(max(int(request.query_params.get('limit', 50)), 1), 500)
        except ValueError:
            return Response({"detail": "limit must be a number."}, status=status.HTTP_400_BAD_REQUEST)
        country = tesfa_data.get_country(pk, limit)
        if country is None:
            return Response({"detail": "Country not found."}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(country).data)


class GraphsView(generics.GenericAPIView):
    """Chart-ready data (labels + values) for the dashboard. Filter with ?country=Ukraine."""
    serializer_class = GraphsSerializer
    permission_classes = [IsAuthenticated]

    @extend_schema(parameters=[OpenApiParameter('country', str, description='Only conflicts involving this country')])
    def get(self, request, *args, **kwargs):
        country = request.query_params.get('country') or None
        return Response(self.get_serializer(tesfa_data.get_graphs(country)).data)

