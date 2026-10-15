from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView
from .views import (
    SignupView, LoginView, ForgotPasswordView, VerifyCodeView, ResetPasswordView,
    ProfileView, UserViewSet, ConversationViewSet, QueryView, ChartListView,
    CountryListView, CountryDetailView, GraphsView,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='users')
router.register(r'conversations', ConversationViewSet, basename='conversations')

urlpatterns = [
    path('register/', SignupView.as_view(), name='register'),
    path('login/', LoginView.as_view(), name='login'),
    path('token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path('forgot-password/', ForgotPasswordView.as_view(), name='forgot-password'),
    path('verify-otp/', VerifyCodeView.as_view(), name='verify-otp'),
    path('reset-password/', ResetPasswordView.as_view(), name='reset-password'),
    path('profile/', ProfileView.as_view(), name='profile'),
    path('query/', QueryView.as_view(), name='query'),
    path('charts/', ChartListView.as_view(), name='charts'),
    path('countries/', CountryListView.as_view(), name='countries'),
    path('countries/<int:pk>/', CountryDetailView.as_view(), name='country-detail'),
    path('graphs/', GraphsView.as_view(), name='graphs'),
    path('', include(router.urls)),
    path('schema/', SpectacularAPIView.as_view(), name='schema'),
    path('schema/swagger-ui/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('schema/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]
