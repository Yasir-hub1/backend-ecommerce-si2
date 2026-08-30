"""
URL configuration for accounts app.
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenRefreshView

from accounts.views import (
    CustomTokenObtainPairView,
    CustomerRegistrationView,
    UserViewSet,
    CustomerProfileViewSet,
    EmployeeProfileViewSet,
    EmployeeCreateView,
    PasswordResetRequestView,
    PasswordResetConfirmView,
)
from accounts.rbac_views import (
    AppPermissionViewSet,
    RoleDefinitionViewSet,
    CurrentUserPermissionsView,
)

router = DefaultRouter()
router.register(r'users', UserViewSet, basename='user')
router.register(r'customers', CustomerProfileViewSet, basename='customer')
router.register(r'employees', EmployeeProfileViewSet, basename='employee')
router.register(r'permissions', AppPermissionViewSet, basename='permission')
router.register(r'roles', RoleDefinitionViewSet, basename='role')

urlpatterns = [
    # Authentication
    path('auth/login/', CustomTokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('auth/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('auth/register/', CustomerRegistrationView.as_view(), name='customer_register'),
    path('auth/password-reset/', PasswordResetRequestView.as_view(), name='password_reset'),
    path('auth/password-reset/confirm/', PasswordResetConfirmView.as_view(), name='password_reset_confirm'),
    path('auth/me/permissions/', CurrentUserPermissionsView.as_view(), name='me_permissions'),

    # Employee creation (admin only)
    path('employees/create/', EmployeeCreateView.as_view(), name='employee_create'),

    # Viewsets
    path('', include(router.urls)),
]
