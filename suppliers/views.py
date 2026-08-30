"""
Views for suppliers app.
"""
from rest_framework import viewsets, status, mixins
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from accounts.models import Role
from suppliers.models import Supplier, PurchaseReceipt, PurchaseReceiptStatus, ProductSubmission
from suppliers.serializers import (
    SupplierSerializer,
    PurchaseReceiptSerializer,
    PurchaseReceiptListSerializer,
    CancelReceiptSerializer,
    ProductSubmissionSerializer,
)
from suppliers.services import confirm_receipt, cancel_receipt
from core.mixins import RBACMixin, BranchScopedQuerysetMixin, PublicReadRBACWriteMixin
from core.exceptions import BusinessError


class SupplierViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    Supplier management (RF06).

    Suppliers provide products for seasons and collections.
    """

    queryset = Supplier.objects.all().order_by('legal_name')
    serializer_class = SupplierSerializer
    write_permission = 'suppliers.manage'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active']
    search_fields = ['legal_name', 'trade_name', 'tax_id']
    ordering = ['legal_name']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ('list', 'retrieve') and not self.request.user.is_authenticated:
            return qs.filter(is_active=True)
        from accounts.models import Role
        user = self.request.user
        if user.is_authenticated and user.role == Role.SUPPLIER:
            try:
                return qs.filter(pk=user.supplier.pk)
            except Exception:
                return qs.none()
        return qs


class PurchaseReceiptViewSet(BranchScopedQuerysetMixin, RBACMixin, viewsets.ModelViewSet):
    """
    Purchase receipt / goods receiving (RF06, RF22).

    Confirming a receipt creates IN_RECEIPT inventory movements.
    """

    queryset = PurchaseReceipt.objects.select_related(
        'supplier', 'branch', 'received_by',
    ).prefetch_related('items__variant').all()
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status', 'branch', 'supplier']
    ordering = ['-created_at']
    branch_field = 'branch'
    permission_map = {
        'list': 'suppliers.view',
        'retrieve': 'suppliers.view',
        'create': 'suppliers.manage',
        'update': 'suppliers.manage',
        'partial_update': 'suppliers.manage',
        'destroy': 'suppliers.manage',
        'confirm': 'suppliers.manage',
        'cancel': 'suppliers.manage',
    }
    http_method_names = ['get', 'post', 'put', 'patch', 'delete']

    def get_serializer_class(self):
        if self.action == 'list':
            return PurchaseReceiptListSerializer
        return PurchaseReceiptSerializer

    def destroy(self, request, *args, **kwargs):
        receipt = self.get_object()
        if receipt.status != PurchaseReceiptStatus.DRAFT:
            return Response(
                {'detail': 'Solo se pueden eliminar recepciones en borrador'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=['post'])
    def confirm(self, request, pk=None):
        """Confirm receipt and add stock (IN_RECEIPT)."""
        try:
            receipt = confirm_receipt(receipt_id=int(pk), user=request.user)
        except BusinessError as err:
            return Response(
                {'error': {'code': err.code, 'message': err.message, 'details': err.details}},
                status=err.status_code,
            )
        return Response(PurchaseReceiptSerializer(receipt).data)

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """Cancel a draft receipt."""
        serializer = CancelReceiptSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            receipt = cancel_receipt(
                receipt_id=int(pk),
                reason=serializer.validated_data.get('reason', ''),
            )
        except BusinessError as err:
            return Response(
                {'error': {'code': err.code, 'message': err.message, 'details': err.details}},
                status=err.status_code,
            )
        return Response(PurchaseReceiptSerializer(receipt).data)


class ProductSubmissionViewSet(
    mixins.CreateModelMixin,
    mixins.ListModelMixin,
    mixins.RetrieveModelMixin,
    viewsets.GenericViewSet,
):
    """Supplier portal: propose new catalog products."""

    serializer_class = ProductSubmissionSerializer
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['status']
    ordering = ['-created_at']

    def get_queryset(self):
        user = self.request.user
        qs = ProductSubmission.objects.select_related('supplier', 'collection').all()

        if user.role == Role.ADMIN:
            return qs

        if user.role == Role.SUPPLIER:
            try:
                return qs.filter(supplier=user.supplier)
            except Exception:
                return ProductSubmission.objects.none()

        return ProductSubmission.objects.none()

    def perform_create(self, serializer):
        if self.request.user.role != Role.SUPPLIER:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied('Solo proveedores pueden enviar propuestas')

        try:
            supplier = self.request.user.supplier
        except Exception as err:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': 'Usuario sin proveedor asociado'}) from err

        serializer.save(supplier=supplier)
