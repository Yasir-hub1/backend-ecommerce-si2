"""
Views for reservations app.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django.db.models import Count
from rest_framework.filters import SearchFilter

from reservations.models import Reservation, ReservationStatus
from reservations.serializers import (
    ReservationListSerializer,
    ReservationDetailSerializer,
    CreateReservationSerializer,
    TransitionReservationSerializer,
    CancelReservationSerializer,
)
from reservations.services import (
    create_reservation,
    transition_reservation,
    cancel_reservation,
)
from core.exceptions import BusinessError
from core.permissions import IsBranchStaff
from accounts.models import Role


class ReservationViewSet(viewsets.ModelViewSet):
    """
    Reservation management.

    - Customers can create reservations and see their own
    - Branch staff see reservations for their branch
    - Admins see all reservations
    """
    queryset = Reservation.objects.select_related(
        'customer__user',
        'branch',
        'prepared_by'
    ).prefetch_related('items__variant__product')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, SearchFilter]
    filterset_fields = ['status', 'branch', 'scheduled_for']
    search_fields = ['code']
    http_method_names = ['get', 'post', 'patch', 'delete']

    def get_serializer_class(self):
        if self.action == 'list':
            return ReservationListSerializer
        elif self.action == 'create':
            return CreateReservationSerializer
        return ReservationDetailSerializer

    def get_queryset(self):
        """Filter reservations by role."""
        user = self.request.user

        # Annotate with items count for list view
        qs = self.queryset.annotate(items_count=Count('items'))

        if user.role == Role.ADMIN:
            return qs.all()

        elif user.role == Role.CUSTOMER:
            # Customers see their own reservations
            return qs.filter(customer__user=user)

        elif user.role in [Role.BRANCH_MANAGER, Role.CASHIER]:
            # Branch staff see reservations for their branch
            try:
                branch_id = user.employee_profile.branch_id
                return qs.filter(branch_id=branch_id)
            except AttributeError:
                return Reservation.objects.none()

        return Reservation.objects.none()

    def create(self, request, *args, **kwargs):
        """Create a new reservation."""
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'Solo clientes pueden crear reservas'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer = request.user.customer_profile

        from branches.models import Branch
        branch = Branch.objects.get(id=serializer.validated_data['branch_id'])

        try:
            reservation = create_reservation(
                customer=customer,
                branch=branch,
                scheduled_for=serializer.validated_data['scheduled_for'],
                items=serializer.validated_data['items'],
                notes=serializer.validated_data.get('notes', ''),
            )

            detail_serializer = ReservationDetailSerializer(
                reservation,
                context={'request': request}
            )

            return Response(
                {
                    'message': 'Reserva creada exitosamente',
                    'reservation': detail_serializer.data
                },
                status=status.HTTP_201_CREATED
            )

        except BusinessError as e:
            return Response(
                {
                    'code': e.code,
                    'message': e.message,
                    'details': e.details
                },
                status=e.status_code
            )

    def retrieve(self, request, *args, **kwargs):
        """Get reservation by ID or code."""
        # Try to get by code first if pk looks like a code
        pk = kwargs.get('pk')
        if pk and pk.startswith('RSV-'):
            try:
                instance = self.get_queryset().get(code=pk)
            except Reservation.DoesNotExist:
                return Response(
                    {'detail': 'Reserva no encontrada'},
                    status=status.HTTP_404_NOT_FOUND
                )
        else:
            instance = self.get_object()

        serializer = self.get_serializer(instance)
        return Response(serializer.data)

    @action(detail=True, methods=['post'])
    def transition(self, request, pk=None):
        """
        Transition reservation to a new status.

        Branch staff only.
        """
        if request.user.role not in [Role.BRANCH_MANAGER, Role.CASHIER, Role.ADMIN]:
            return Response(
                {'detail': 'No autorizado'},
                status=status.HTTP_403_FORBIDDEN
            )

        reservation = self.get_object()

        # Verify branch staff can only transition their branch's reservations
        if request.user.role in [Role.BRANCH_MANAGER, Role.CASHIER]:
            if reservation.branch_id != request.user.employee_profile.branch_id:
                return Response(
                    {'detail': 'No autorizado'},
                    status=status.HTTP_403_FORBIDDEN
                )

        serializer = TransitionReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            updated_reservation = transition_reservation(
                reservation_id=reservation.id,
                new_status=serializer.validated_data['new_status'],
                user=request.user,
            )

            return Response(
                {
                    'message': 'Estado actualizado',
                    'reservation': ReservationDetailSerializer(updated_reservation).data
                }
            )

        except BusinessError as e:
            return Response(
                {'code': e.code, 'message': e.message, 'details': e.details},
                status=e.status_code
            )

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel a reservation.

        Customer can cancel their own reservations.
        Branch staff can cancel reservations for their branch.
        """
        reservation = self.get_object()

        # Check permissions
        if request.user.role == Role.CUSTOMER:
            if reservation.customer.user_id != request.user.id:
                return Response(
                    {'detail': 'No autorizado'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif request.user.role in [Role.BRANCH_MANAGER, Role.CASHIER]:
            if reservation.branch_id != request.user.employee_profile.branch_id:
                return Response(
                    {'detail': 'No autorizado'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif request.user.role != Role.ADMIN:
            return Response(
                {'detail': 'No autorizado'},
                status=status.HTTP_403_FORBIDDEN
            )

        serializer = CancelReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            cancelled_reservation = cancel_reservation(
                reservation_id=reservation.id,
                reason=serializer.validated_data.get('reason', ''),
            )

            return Response(
                {
                    'message': 'Reserva cancelada',
                    'reservation': ReservationDetailSerializer(cancelled_reservation).data
                }
            )

        except BusinessError as e:
            return Response(
                {'code': e.code, 'message': e.message, 'details': e.details},
                status=e.status_code
            )

    @action(detail=False, methods=['get'])
    def my_reservations(self, request):
        """Get current customer's reservations."""
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'Solo clientes tienen reservas'},
                status=status.HTTP_400_BAD_REQUEST
            )

        reservations = self.get_queryset().filter(
            customer__user=request.user
        ).order_by('-scheduled_for')

        page = self.paginate_queryset(reservations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def today(self, request):
        """Reservations scheduled for today (staff branch scope)."""
        if request.user.role not in [Role.BRANCH_MANAGER, Role.CASHIER, Role.ADMIN]:
            return Response(
                {'detail': 'Solo personal de sucursal puede ver reservas del día'},
                status=status.HTTP_403_FORBIDDEN,
            )

        from django.utils import timezone

        today = timezone.localdate()
        reservations = self.get_queryset().filter(
            scheduled_for__date=today,
        ).order_by('scheduled_for')

        page = self.paginate_queryset(reservations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)

    @action(detail=False, methods=['get'])
    def upcoming(self, request):
        """
        Get upcoming reservations for branch staff.

        Branch staff only - shows upcoming reservations for their branch.
        """
        if request.user.role not in [Role.BRANCH_MANAGER, Role.CASHIER]:
            return Response(
                {'detail': 'Solo personal de sucursal puede ver reservas próximas'},
                status=status.HTTP_403_FORBIDDEN
            )

        from django.utils import timezone

        reservations = self.get_queryset().filter(
            status__in=[
                ReservationStatus.PENDING,
                ReservationStatus.PREPARING,
                ReservationStatus.READY,
            ],
            scheduled_for__gte=timezone.now()
        ).order_by('scheduled_for')

        page = self.paginate_queryset(reservations)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(reservations, many=True)
        return Response(serializer.data)
