from django.urls import path
from apps.accounts.views import (
    RegisterView,
    LoginView,
    CustomTokenRefreshView,
    LogoutView,
    CurrentUserView,
)

urlpatterns = [
    path('register/', RegisterView.as_view(), name='auth_register'),
    path('login/', LoginView.as_view(), name='auth_login'),
    path('refresh/', CustomTokenRefreshView.as_view(), name='auth_refresh'),
    path('logout/', LogoutView.as_view(), name='auth_logout'),
    path('me/', CurrentUserView.as_view(), name='user_me'),
]
