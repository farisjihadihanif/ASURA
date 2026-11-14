from django.urls import path
from .views import LoginAPIView, GetMeAPIView, LogoutAPIView
from .register_views import RegisterAPIView, RegisterLookupAPIView, RegisterOptionsAPIView

urlpatterns = [
    path('login/', LoginAPIView.as_view(), name='api-login'),
    path('logout/', LogoutAPIView.as_view(), name='api-logout'),
    path('register/', RegisterAPIView.as_view(), name='api-register'),
    path('register/lookup/', RegisterLookupAPIView.as_view(), name='api-register-lookup'),
    path('register/options/', RegisterOptionsAPIView.as_view(), name='api-register-options'),
    path('me/', GetMeAPIView.as_view(), name='api-get-me'),
]
