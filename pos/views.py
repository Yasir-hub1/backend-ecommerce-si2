"""POS API views."""
from decimal import Decimal

from django.db.models import Prefetch
from django.http import FileResponse, Http404
from django.utils import timezone
from rest_framework import generics, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, DateFilter

from accounts.models import CustomerProfile, Role
from accounts.services.staff import parse_branch_id
from core.exceptions import BusinessError
from core.permissions import HasAppPermission
from orders.models import Order, OrderChannel, OrderItem, OrderStatus
from orders.receipts import (
    get_or_create_order_receipt,
    receipt_number,
    user_can_access_order_receipt,
)
from orders.services import PAID_ORDER_STATUSES, create_pos_sale
from payments.services import validate_pos_payment
from pos.serializers import (
    POSPaymentPreviewSerializer,
    POSPaymentSerializer,
    POSQuoteSerializer,
    POSSaleSerializer,
)
from pos.services import (
    get_cashier_branch,
    get_daily_pos_summary,
    lookup_variant_by_barcode,
    quote_pos_sale,
    search_pos_catalog,
)
from reservations.models import Reservation
from reservations.serializers import ReservationDetailSerializer


class POSPermissionMixin:
    permission_classes = [IsAuthenticated, HasAppPermission]
    required_permission = 'pos.sales'


class POSBranchMixin:
    """Resolve branch context from query/body (admin and custom roles need branch_id)."""

    def resolve_pos_branch(self, request, *, from_body: bool = False):
        branch_id = parse_branch_id(request.query_params.get('branch_id'))
        if from_body and branch_id is None:
            branch_id = parse_branch_id(request.data.get('branch_id'))
        return get_cashier_branch(user=request.user, branch_id=branch_id)

    def branch_error_response(self, err: BusinessError) -> Response:
        return Response(
            {'code': err.code, 'message': err.message, 'details': err.details},
            status=err.status_code,
        )


class POSCatalogSearchView(POSBranchMixin, POSPermissionMixin, generics.GenericAPIView):
    """Quick search by product name, SKU or barcode."""

    def get(self, request):
        query = request.query_params.get('q', '').strip()
        if not query:
            return Response(
                {'detail': 'Parámetro q requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            branch = self.resolve_pos_branch(request)
        except BusinessError as err:
            return self.branch_error_response(err)

        limit = min(int(request.query_params.get('limit', 20)), 50)
        results = search_pos_catalog(branch=branch, query=query, limit=limit)
        return Response({'count': len(results), 'results': results})


class POSBarcodeLookupView(POSBranchMixin, POSPermissionMixin, generics.GenericAPIView):
    """Resolve a single variant by barcode or SKU (scanner)."""

    def get(self, request):
        barcode = request.query_params.get('barcode', '').strip()
        if not barcode:
            return Response(
                {'detail': 'Parámetro barcode requerido.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            branch = self.resolve_pos_branch(request)
        except BusinessError as err:
            return self.branch_error_response(err)

        result = lookup_variant_by_barcode(branch=branch, barcode=barcode)
        if result is None:
            return Response(
                {'detail': 'Variante no encontrada.'},
                status=status.HTTP_404_NOT_FOUND,
            )
        return Response(result)


class POSQuoteView(POSBranchMixin, POSPermissionMixin, generics.GenericAPIView):
    """Preview cart totals before charging."""

    serializer_class = POSQuoteSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            branch = self.resolve_pos_branch(request, from_body=True)
            payload = quote_pos_sale(
                branch=branch,
                items=serializer.validated_data['items'],
            )
        except BusinessError as err:
            return self.branch_error_response(err)

        return Response(payload)


class POSPaymentPreviewView(POSBranchMixin, POSPermissionMixin, generics.GenericAPIView):
    """Validate mixed payments and calculate change (vuelto)."""

    serializer_class = POSPaymentPreviewSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            branch = self.resolve_pos_branch(request, from_body=True)
            quote = quote_pos_sale(
                branch=branch,
                items=serializer.validated_data['items'],
            )
            payments = [dict(payment) for payment in serializer.validated_data['payments']]
            summary = validate_pos_payment(
                total_due=Decimal(quote['grand_total']),
                payments=payments,
            )
        except BusinessError as err:
            return self.branch_error_response(err)

        return Response({
            'quote': quote,
            'payment_summary': {
                'total_due': quote['grand_total'],
                'total_payment': str(summary['total_payment']),
                'total_change': str(summary['total_change']),
                'overpayment': str(summary['overpayment']),
                'payments': payments,
            },
        })


class POSSaleView(POSBranchMixin, POSPermissionMixin, generics.CreateAPIView):
    """Register a paid POS sale with stock deduction and receipt."""

    serializer_class = POSSaleSerializer

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            branch = self.resolve_pos_branch(request, from_body=True)
        except BusinessError as err:
            return self.branch_error_response(err)

        customer = None
        customer_id = serializer.validated_data.get('customer_id')
        if customer_id:
            try:
                customer = CustomerProfile.objects.get(user_id=customer_id)
            except CustomerProfile.DoesNotExist:
                return Response(
                    {'detail': 'Cliente no encontrado'},
                    status=status.HTTP_404_NOT_FOUND,
                )

        try:
            order = create_pos_sale(
                branch=branch,
                cashier=request.user,
                items=serializer.validated_data['items'],
                payments=serializer.validated_data['payments'],
                customer=customer,
                reservation_id=serializer.validated_data.get('reservation_id'),
            )
        except BusinessError as err:
            return Response(
                {'code': err.code, 'message': err.message, 'details': err.details},
                status=err.status_code,
            )

        order = Order.objects.prefetch_related(
            Prefetch('items', queryset=OrderItem.objects.select_related('variant__product')),
            'payments',
        ).get(pk=order.pk)

        receipt = get_or_create_order_receipt(order=order)
        pdf_url = request.build_absolute_uri(
            f'/api/v1/pos/sales/{order.id}/receipt/pdf/',
        )

        total_change = sum(
            payment.change_amount or 0
            for payment in order.payments.all()
            if payment.change_amount
        )

        return Response(
            {
                'message': 'Venta registrada exitosamente',
                'order': {
                    'id': order.id,
                    'code': order.code,
                    'status': order.status,
                    'subtotal': str(order.subtotal),
                    'tax_total': str(order.tax_total),
                    'grand_total': str(order.grand_total),
                    'currency': order.currency,
                    'paid_at': order.paid_at,
                    'reservation_id': order.reservation_id,
                    'items': [
                        {
                            'id': line.id,
                            'variant_id': line.variant_id,
                            'product_name': line.variant.product.name,
                            'sku': line.variant.sku,
                            'quantity': line.quantity,
                            'unit_price': str(line.unit_price),
                            'line_total': str(line.line_total),
                        }
                        for line in order.items.all()
                    ],
                    'payments': POSPaymentSerializer(order.payments.all(), many=True).data,
                },
                'receipt': {
                    'id': receipt.id,
                    'receipt_number': receipt_number(receipt),
                    'pdf_url': pdf_url,
                },
                'total_change': str(total_change),
            },
            status=status.HTTP_201_CREATED,
        )


class POSOrderFilter(FilterSet):
    paid_at__date = DateFilter(field_name='paid_at', lookup_expr='date')

    class Meta:
        model = Order
        fields = ['paid_at__date']


class POSOrderViewSet(POSBranchMixin, POSPermissionMixin, viewsets.ReadOnlyModelViewSet):
    """List and retrieve POS sales for the cashier's branch."""

    queryset = Order.objects.select_related('branch', 'customer__user', 'reservation').prefetch_related(
        'items__variant__product',
        'payments',
    )
    filter_backends = [DjangoFilterBackend]
    filterset_class = POSOrderFilter

    def get_queryset(self):
        try:
            branch = self.resolve_pos_branch(self.request)
        except BusinessError:
            return Order.objects.none()

        qs = self.queryset.filter(
            channel=OrderChannel.POS,
            branch=branch,
            status__in=PAID_ORDER_STATUSES,
        )

        if self.request.user.role == Role.CASHIER:
            qs = qs.filter(created_by=self.request.user)

        return qs.order_by('-paid_at')

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        rows = page if page is not None else queryset

        payload = [
            {
                'id': order.id,
                'code': order.code,
                'status': order.status,
                'status_display': order.get_status_display(),
                'grand_total': str(order.grand_total),
                'currency': order.currency,
                'paid_at': order.paid_at,
                'created_at': order.created_at,
                'customer_name': (
                    order.customer.user.get_full_name()
                    if order.customer_id
                    else None
                ),
                'item_count': order.items.count(),
            }
            for order in rows
        ]

        if page is not None:
            return self.get_paginated_response(payload)
        return Response(payload)

    def retrieve(self, request, *args, **kwargs):
        order = self.get_object()
        receipt = get_or_create_order_receipt(order=order)
        return Response({
            'id': order.id,
            'code': order.code,
            'status': order.status,
            'subtotal': str(order.subtotal),
            'tax_total': str(order.tax_total),
            'grand_total': str(order.grand_total),
            'currency': order.currency,
            'paid_at': order.paid_at,
            'reservation_id': order.reservation_id,
            'items': [
                {
                    'id': line.id,
                    'variant_id': line.variant_id,
                    'product_name': line.variant.product.name,
                    'sku': line.variant.sku,
                    'quantity': line.quantity,
                    'unit_price': str(line.unit_price),
                    'line_total': str(line.line_total),
                }
                for line in order.items.all()
            ],
            'payments': POSPaymentSerializer(order.payments.all(), many=True).data,
            'receipt': {
                'receipt_number': receipt_number(receipt),
                'pdf_url': request.build_absolute_uri(
                    f'/api/v1/pos/sales/{order.id}/receipt/pdf/',
                ),
            },
        })

    @action(detail=True, methods=['get'], url_path='receipt')
    def receipt(self, request, pk=None):
        order = self.get_object()
        if not user_can_access_order_receipt(user=request.user, order=order):
            return Response({'detail': 'No autorizado'}, status=status.HTTP_403_FORBIDDEN)

        try:
            receipt = get_or_create_order_receipt(order=order)
        except BusinessError as err:
            return Response(
                {'code': err.code, 'message': err.message, 'details': err.details},
                status=err.status_code,
            )

        pdf_url = request.build_absolute_uri(
            f'/api/v1/pos/sales/{order.id}/receipt/pdf/',
        )
        return Response({
            'id': receipt.id,
            'receipt_number': receipt_number(receipt),
            'pdf_url': pdf_url,
            'order_code': order.code,
        })

    @action(detail=True, methods=['get'], url_path='receipt/pdf')
    def receipt_pdf(self, request, pk=None):
        order = self.get_object()
        if not user_can_access_order_receipt(user=request.user, order=order):
            return Response({'detail': 'No autorizado'}, status=status.HTTP_403_FORBIDDEN)

        try:
            receipt = get_or_create_order_receipt(order=order)
        except BusinessError as err:
            return Response(
                {'code': err.code, 'message': err.message, 'details': err.details},
                status=err.status_code,
            )

        if not receipt.pdf_file:
            raise Http404('PDF no disponible')

        filename = f'{receipt_number(receipt)}.pdf'
        return FileResponse(
            receipt.pdf_file.open('rb'),
            content_type='application/pdf',
            filename=filename,
            as_attachment=False,
        )


class POSDailySummaryView(POSBranchMixin, POSPermissionMixin, generics.GenericAPIView):
    """Today's sales for the authenticated cashier."""

    def get(self, request):
        try:
            branch = self.resolve_pos_branch(request)
        except BusinessError as err:
            return self.branch_error_response(err)

        day_param = request.query_params.get('date')
        target_day = timezone.localdate()
        if day_param:
            from datetime import date as date_cls
            target_day = date_cls.fromisoformat(day_param)

        scope = 'cashier' if request.user.role == Role.CASHIER else 'branch'

        summary = get_daily_pos_summary(
            branch=branch,
            cashier=request.user,
            day=target_day,
            scope=scope,
        )
        summary['branch_id'] = branch.id
        summary['branch_name'] = branch.name
        return Response(summary)


class POSReservationLookupView(POSBranchMixin, POSPermissionMixin, generics.GenericAPIView):
    """Fetch reservation details for checkout at the register."""

    def get(self, request):
        code = request.query_params.get('code', '').strip()
        reservation_id = request.query_params.get('id')

        if not code and not reservation_id:
            return Response(
                {'detail': 'Indica code o id de la reserva.'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            branch = self.resolve_pos_branch(request)
        except BusinessError as err:
            return self.branch_error_response(err)

        qs = Reservation.objects.select_related(
            'customer__user',
            'branch',
        ).prefetch_related('items__variant__product')

        if code:
            reservation = qs.filter(code=code, branch=branch).first()
        else:
            reservation = qs.filter(id=reservation_id, branch=branch).first()

        if reservation is None:
            return Response(
                {'detail': 'Reserva no encontrada en esta sucursal.'},
                status=status.HTTP_404_NOT_FOUND,
            )

        data = ReservationDetailSerializer(reservation, context={'request': request}).data
        return Response(data)
