"""
Views for accounts app.
"""
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework_simplejwt.views import TokenObtainPairView
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from accounts.models import User, CustomerProfile, EmployeeProfile, Role
from accounts.serializers import (
    UserSerializer,
    CustomerProfileSerializer,
    EmployeeProfileSerializer,
    CustomerRegistrationSerializer,
    EmployeeCreateSerializer,
    CustomTokenObtainPairSerializer,
    ChangePasswordSerializer,
    PasswordResetRequestSerializer,
    PasswordResetConfirmSerializer,
)
from core.permissions import IsAdmin, IsBranchStaff, HasAppPermission


class CustomTokenObtainPairView(TokenObtainPairView):
    """Custom JWT token view with role and branch in claims."""
    serializer_class = CustomTokenObtainPairSerializer


class CustomerRegistrationView(generics.CreateAPIView):
    """
    Public endpoint for customer registration.

    POST /api/v1/auth/register/
    """
    serializer_class = CustomerRegistrationSerializer
    permission_classes = [AllowAny]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                'message': 'Usuario registrado exitosamente',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                }
            },
            status=status.HTTP_201_CREATED
        )


class UserViewSet(viewsets.ModelViewSet):
    """
    User management viewset (RF02).

    RBAC: accounts.users.view / accounts.users.manage
    Users can retrieve their own profile without admin permission.
    """
    queryset = User.objects.all()
    serializer_class = UserSerializer
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['role', 'is_active']
    search_fields = ['email', 'first_name', 'last_name']
    ordering = ['-date_joined']
    permission_map = {
        'list': 'accounts.users.view',
        'retrieve': 'accounts.users.view',
        'create': 'accounts.users.manage',
        'update': 'accounts.users.manage',
        'partial_update': 'accounts.users.manage',
        'destroy': 'accounts.users.manage',
    }

    def get_permissions(self):
        if self.action in ('me', 'change_password'):
            return [IsAuthenticated()]
        if self.action in ('list', 'create', 'update', 'partial_update', 'destroy'):
            return [IsAuthenticated(), HasAppPermission()]
        return [IsAuthenticated()]

    def get_required_permission(self):
        return self.permission_map.get(self.action)

    def get_queryset(self):
        """Admin sees all, others see only themselves."""
        user = self.request.user
        if user.role == Role.ADMIN:
            return User.objects.all()
        return User.objects.filter(id=user.id)

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current user profile."""
        serializer = self.get_serializer(request.user)
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def change_password(self, request):
        """Change current user password."""
        serializer = ChangePasswordSerializer(
            data=request.data,
            context={'request': request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()

        return Response({
            'message': 'Contraseña actualizada exitosamente'
        })


class CustomerProfileViewSet(viewsets.ModelViewSet):
    """
    Customer profile management.

    Customers can view/update their own profile.
    Admins can view all customer profiles.
    """
    queryset = CustomerProfile.objects.select_related('user').all()
    serializer_class = CustomerProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filter by role."""
        user = self.request.user

        if user.role == Role.ADMIN:
            return CustomerProfile.objects.select_related('user').all()
        elif user.role == Role.CUSTOMER:
            return CustomerProfile.objects.filter(user=user)

        # Branch staff shouldn't access customer profiles directly
        return CustomerProfile.objects.none()

    def get_object(self):
        """Non-admins can only access their own profile."""
        obj = super().get_object()

        if self.request.user.role != Role.ADMIN:
            if obj.user_id != self.request.user.id:
                self.permission_denied(self.request)

        return obj

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current customer profile."""
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'Solo clientes tienen perfil de cliente'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            profile = request.user.customer_profile
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except CustomerProfile.DoesNotExist:
            return Response(
                {'detail': 'Perfil de cliente no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )


class EmployeeProfileViewSet(viewsets.ModelViewSet):
    """
    Employee profile management.

    Only admins can create/update/delete.
    Employees can view their own profile.
    """
    queryset = EmployeeProfile.objects.select_related('user', 'branch').all()
    serializer_class = EmployeeProfileSerializer
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        """Admin required for modifications."""
        if self.action in ['create', 'update', 'partial_update', 'destroy']:
            return [IsAdmin()]
        return [IsAuthenticated()]

    def get_queryset(self):
        """Filter by role and branch."""
        user = self.request.user

        if user.role == Role.ADMIN:
            return EmployeeProfile.objects.select_related('user', 'branch').all()
        elif user.role in [Role.BRANCH_MANAGER, Role.CASHIER]:
            # Employees can only see employees from their branch
            try:
                branch_id = user.employee_profile.branch_id
                return EmployeeProfile.objects.filter(branch_id=branch_id)
            except EmployeeProfile.DoesNotExist:
                return EmployeeProfile.objects.none()

        return EmployeeProfile.objects.none()

    @action(detail=False, methods=['get'])
    def me(self, request):
        """Get current employee profile."""
        if request.user.role not in [Role.BRANCH_MANAGER, Role.CASHIER]:
            return Response(
                {'detail': 'Solo empleados tienen perfil de empleado'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            profile = request.user.employee_profile
            serializer = self.get_serializer(profile)
            return Response(serializer.data)
        except EmployeeProfile.DoesNotExist:
            return Response(
                {'detail': 'Perfil de empleado no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )


class EmployeeCreateView(generics.CreateAPIView):
    """
    Create employee users (RF02).

    Requires accounts.users.manage
    POST /api/v1/employees/create/
    """
    serializer_class = EmployeeCreateSerializer
    permission_classes = [IsAuthenticated, HasAppPermission]
    required_permission = 'accounts.users.manage'

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = serializer.save()

        return Response(
            {
                'message': 'Empleado creado exitosamente',
                'user': {
                    'id': user.id,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                    'role': user.role,
                }
            },
            status=status.HTTP_201_CREATED
        )


class PasswordResetRequestView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetRequestSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from accounts.services.password_reset import request_password_reset

        request_password_reset(email=serializer.validated_data['email'])
        return Response({
            'message': 'Si el correo está registrado, recibirás instrucciones para restablecer tu contraseña.',
        })


class PasswordResetConfirmView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = PasswordResetConfirmSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        from accounts.services.password_reset import confirm_password_reset
        from django.core.exceptions import ValidationError

        try:
            confirm_password_reset(
                token=serializer.validated_data['token'],
                password=serializer.validated_data['password'],
            )
        except ValidationError as err:
            return Response(
                {'message': err.messages[0] if err.messages else str(err)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({'message': 'Contraseña actualizada exitosamente'})
