from django.urls import path
from .views import LoginAPIView, GetMeAPIView, LogoutAPIView, TokenRefreshAPIView
from .register_views import RegisterAPIView, RegisterLookupAPIView

urlpatterns = [
    path('login/', LoginAPIView.as_view(), name='api-login'),
    path('logout/', LogoutAPIView.as_view(), name='api-logout'),
    path('token/refresh/', TokenRefreshAPIView.as_view(), name='api-token-refresh'),
    path('register/', RegisterAPIView.as_view(), name='api-register'),
    path('register/lookup/', RegisterLookupAPIView.as_view(), name='api-register-lookup'),
    path('me/', GetMeAPIView.as_view(), name='api-get-me'),
]
