"""
Views for inventory app.
"""
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import OrderingFilter

from inventory.models import BranchStock, InventoryMovement, MovementType, ReferenceType
from inventory.serializers import (
    BranchStockSerializer,
    InventoryMovementSerializer,
    StockAdjustSerializer,
    StockTransferSerializer,
    BranchStockThresholdSerializer,
)
from inventory.services import apply_movements
from core.permissions import HasAppPermission
from core.mixins import BranchScopedQuerysetMixin, RBACMixin
from core.exceptions import BusinessError
from branches.models import Branch
from catalog.models import ProductVariant


class BranchStockViewSet(BranchScopedQuerysetMixin, RBACMixin, viewsets.ReadOnlyModelViewSet):
    """
    Stock levels by branch and variant (RF08, RF21).

    Branch staff see only their branch; admin sees all.
    """

    queryset = BranchStock.objects.select_related(
        'branch', 'variant__product', 'variant__size', 'variant__color',
    ).all()
    serializer_class = BranchStockSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['branch', 'variant']
    ordering_fields = ['on_hand', 'reserved', 'updated_at']
    ordering = ['branch__code', 'variant__sku']
    branch_field = 'branch'
    permission_map = {
        'list': 'inventory.stock.view',
        'retrieve': 'inventory.stock.view',
        'adjust': 'inventory.stock.manage',
        'transfer': 'inventory.stock.manage',
        'update_threshold': 'inventory.stock.manage',
        'low_stock': 'inventory.stock.view',
    }

    @action(detail=False, methods=['post'])
    def adjust(self, request):
        """Manual stock adjustment (ADJUST_IN / ADJUST_OUT)."""
        serializer = StockAdjustSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        branch = Branch.objects.get(pk=data['branch_id'])
        movement_type = (
            MovementType.ADJUST_IN if data['direction'] == 'in'
            else MovementType.ADJUST_OUT
        )

        apply_movements(
            branch=branch,
            lines=[(data['variant_id'], data['quantity'])],
            movement_type=movement_type,
            reference_type=ReferenceType.MANUAL,
            user=request.user,
            note=data.get('note', ''),
        )
        stock = BranchStock.objects.get(branch=branch, variant_id=data['variant_id'])
        return Response(BranchStockSerializer(stock).data)

    @action(detail=False, methods=['post'])
    def transfer(self, request):
        """Transfer stock between branches."""
        serializer = StockTransferSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data

        from_branch = Branch.objects.get(pk=data['from_branch_id'])
        to_branch = Branch.objects.get(pk=data['to_branch_id'])
        lines = [(data['variant_id'], data['quantity'])]
        note = data.get('note', '')

        apply_movements(
            branch=from_branch,
            lines=lines,
            movement_type=MovementType.TRANSFER_OUT,
            reference_type=ReferenceType.TRANSFER,
            user=request.user,
            note=f"Transferencia a {to_branch.code}. {note}".strip(),
        )
        apply_movements(
            branch=to_branch,
            lines=lines,
            movement_type=MovementType.TRANSFER_IN,
            reference_type=ReferenceType.TRANSFER,
            user=request.user,
            note=f"Transferencia desde {from_branch.code}. {note}".strip(),
        )

        stock = BranchStock.objects.get(branch=to_branch, variant_id=data['variant_id'])
        return Response(BranchStockSerializer(stock).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['patch'], url_path='threshold')
    def update_threshold(self, request, pk=None):
        """Update minimum stock alert threshold."""
        stock = self.get_object()
        serializer = BranchStockThresholdSerializer(stock, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(BranchStockSerializer(stock).data)

    @action(detail=False, methods=['get'])
    def low_stock(self, request):
        """Variants at or below minimum threshold."""
        from django.db.models import F

        qs = self.get_queryset().filter(
            on_hand__lte=F('min_threshold'),
            min_threshold__gt=0,
        )
        if request.query_params.get('branch'):
            qs = qs.filter(branch_id=request.query_params['branch'])
        page = self.paginate_queryset(qs)
        if page is not None:
            return self.get_paginated_response(BranchStockSerializer(page, many=True).data)
        return Response(BranchStockSerializer(qs, many=True).data)


class InventoryMovementViewSet(BranchScopedQuerysetMixin, RBACMixin, viewsets.ReadOnlyModelViewSet):
    """
    Inventory movement ledger (RF22). Append-only — read API only.
    """

    queryset = InventoryMovement.objects.select_related(
        'branch', 'variant', 'created_by',
    ).all()
    serializer_class = InventoryMovementSerializer
    filter_backends = [DjangoFilterBackend, OrderingFilter]
    filterset_fields = ['branch', 'variant', 'movement_type', 'reference_type']
    ordering = ['-created_at']
    branch_field = 'branch'
    permission_map = {
        'list': 'inventory.stock.view',
        'retrieve': 'inventory.stock.view',
    }
