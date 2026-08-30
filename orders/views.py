"""
Views for orders app.
"""
from rest_framework import viewsets, status, generics
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from django_filters.rest_framework import DjangoFilterBackend
from django_filters import FilterSet, DateFilter
from django.db.models import Count, Sum, F, Q
from django.http import FileResponse, Http404

from orders.models import Cart, CartItem, Order, OrderStatus
from orders.serializers import (
    CartSerializer,
    CartItemSerializer,
    OrderListSerializer,
    OrderDetailSerializer,
    CheckoutSerializer,
    AddToCartSerializer,
    UpdateCartItemSerializer,
)
from orders.services import checkout_from_cart, cancel_order, refund_order
from core.permissions import IsAdmin, IsBranchStaff
from core.exceptions import BusinessError
from accounts.models import Role
from orders.receipts import (
    get_or_create_order_receipt,
    receipt_number,
    user_can_access_order_receipt,
)


class OrderFilter(FilterSet):
    created_at__date = DateFilter(field_name='created_at', lookup_expr='date')

    class Meta:
        model = Order
        fields = ['status', 'channel', 'branch', 'created_at__date']


class CartViewSet(viewsets.ViewSet):
    """
    Shopping cart management.

    Customers manage their own cart.
    """
    permission_classes = [IsAuthenticated]

    def list(self, request):
        """Get current user's cart."""
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'Solo clientes pueden tener carrito'},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            customer = request.user.customer_profile
        except AttributeError:
            return Response(
                {'detail': 'Perfil de cliente no encontrado'},
                status=status.HTTP_404_NOT_FOUND
            )

        # Get or create cart
        cart, created = Cart.objects.get_or_create(customer=customer)

        # Annotate cart with totals
        cart_data = Cart.objects.filter(id=cart.id).annotate(
            total_items=Count('items'),
            subtotal=Sum(F('items__quantity') * F('items__variant__product__base_price'))
        ).first()

        serializer = CartSerializer(cart_data, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['post'])
    def add_item(self, request):
        """Add item to cart or update quantity if exists."""
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'Solo clientes pueden agregar al carrito'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = AddToCartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer = request.user.customer_profile
        cart, _ = Cart.objects.get_or_create(customer=customer)

        variant_id = serializer.validated_data['variant_id']
        quantity = serializer.validated_data['quantity']

        # Check if item already in cart
        cart_item, created = CartItem.objects.get_or_create(
            cart=cart,
            variant_id=variant_id,
            defaults={'quantity': quantity}
        )

        if not created:
            # Update quantity
            cart_item.quantity += quantity
            cart_item.save()

        # Return updated cart
        cart_data = Cart.objects.filter(id=cart.id).annotate(
            total_items=Count('items'),
            subtotal=Sum(F('items__quantity') * F('items__variant__product__base_price'))
        ).first()

        cart_serializer = CartSerializer(cart_data, context={'request': request})

        return Response(
            {
                'message': 'Producto agregado al carrito',
                'cart': cart_serializer.data
            },
            status=status.HTTP_200_OK
        )

    def _cart_response(self, request, cart_id):
        cart_data = Cart.objects.filter(id=cart_id).annotate(
            total_items=Count('items'),
            subtotal=Sum(F('items__quantity') * F('items__variant__product__base_price'))
        ).first()
        serializer = CartSerializer(cart_data, context={'request': request})
        return Response(serializer.data)

    @action(detail=False, methods=['patch', 'delete'], url_path='items/(?P<item_id>[^/.]+)')
    def item_detail(self, request, item_id=None):
        """Update quantity (PATCH) or remove (DELETE) a cart line item."""
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'No autorizado'},
                status=status.HTTP_403_FORBIDDEN
            )

        customer = request.user.customer_profile

        try:
            cart_item = CartItem.objects.get(
                id=item_id,
                cart__customer=customer,
            )
        except CartItem.DoesNotExist:
            return Response(
                {'detail': 'Item no encontrado en el carrito'},
                status=status.HTTP_404_NOT_FOUND
            )

        if request.method == 'DELETE':
            cart_id = cart_item.cart_id
            cart_item.delete()
            return self._cart_response(request, cart_id)

        serializer = UpdateCartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        cart_item.quantity = serializer.validated_data['quantity']
        cart_item.save(update_fields=['quantity', 'updated_at'])
        return self._cart_response(request, cart_item.cart_id)

    @action(detail=False, methods=['delete'])
    def clear(self, request):
        """Clear cart."""
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'No autorizado'},
                status=status.HTTP_403_FORBIDDEN
            )

        customer = request.user.customer_profile

        try:
            cart = Cart.objects.get(customer=customer)
            cart.items.all().delete()
        except Cart.DoesNotExist:
            pass

        return Response({'message': 'Carrito vaciado'}, status=status.HTTP_200_OK)

    @action(detail=False, methods=['post'])
    def checkout(self, request):
        """
        Convert cart to order.

        Creates order in PENDING_PAYMENT status but doesn't deduct stock yet.
        Stock is deducted when payment is confirmed via webhook.
        """
        if request.user.role != Role.CUSTOMER:
            return Response(
                {'detail': 'Solo clientes pueden realizar checkout'},
                status=status.HTTP_400_BAD_REQUEST
            )

        serializer = CheckoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        customer = request.user.customer_profile

        from branches.models import Branch
        branch = Branch.objects.get(id=serializer.validated_data['branch_id'])

        try:
            order = checkout_from_cart(
                customer=customer,
                branch=branch,
                channel=serializer.validated_data['channel'],
                promotion_code=serializer.validated_data.get('promotion_code'),
            )

            order_serializer = OrderDetailSerializer(order, context={'request': request})

            return Response(
                {
                    'message': 'Orden creada exitosamente',
                    'order': order_serializer.data
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


class OrderViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Order management.

    Customers see their own orders.
    Branch staff see orders for their branch.
    Admins see all orders.
    """
    queryset = Order.objects.select_related(
        'customer__user',
        'branch',
        'reservation'
    ).prefetch_related('items__variant__product')
    permission_classes = [IsAuthenticated]
    filter_backends = [DjangoFilterBackend]
    filterset_class = OrderFilter

    def get_serializer_class(self):
        if self.action == 'list':
            return OrderListSerializer
        return OrderDetailSerializer

    def get_queryset(self):
        """Filter orders by role."""
        user = self.request.user

        if user.role == Role.ADMIN:
            return self.queryset.all()

        elif user.role == Role.CUSTOMER:
            return self.queryset.filter(customer__user=user)

        elif user.role in [Role.BRANCH_MANAGER, Role.CASHIER]:
            # Branch staff see orders for their branch
            try:
                branch_id = user.employee_profile.branch_id
                return self.queryset.filter(branch_id=branch_id)
            except AttributeError:
                return Order.objects.none()

        return Order.objects.none()

    @action(detail=True, methods=['post'])
    def cancel(self, request, pk=None):
        """
        Cancel an order.

        Only pending payment orders can be cancelled.
        """
        order = self.get_object()

        # Check permissions
        if request.user.role == Role.CUSTOMER:
            if order.customer.user_id != request.user.id:
                return Response(
                    {'detail': 'No autorizado'},
                    status=status.HTTP_403_FORBIDDEN
                )
        elif request.user.role not in [Role.ADMIN, Role.BRANCH_MANAGER]:
            return Response(
                {'detail': 'No autorizado'},
                status=status.HTTP_403_FORBIDDEN
            )

        try:
            cancelled_order = cancel_order(order_id=order.id)

            return Response(
                {
                    'message': 'Orden cancelada',
                    'order': OrderDetailSerializer(cancelled_order).data
                }
            )

        except BusinessError as e:
            return Response(
                {'code': e.code, 'message': e.message, 'details': e.details},
                status=e.status_code
            )

    @action(detail=True, methods=['post'])
    def refund(self, request, pk=None):
        """
        Refund an order.

        Admin or branch manager only.
        Returns items to stock and processes Stripe refund.
        """
        if request.user.role not in [Role.ADMIN, Role.BRANCH_MANAGER]:
            return Response(
                {'detail': 'No autorizado'},
                status=status.HTTP_403_FORBIDDEN
            )

        order = self.get_object()

        reason = request.data.get('reason', '')

        try:
            refunded_order = refund_order(order_id=order.id, reason=reason)

            return Response(
                {
                    'message': 'Orden reembolsada',
                    'order': OrderDetailSerializer(refunded_order).data
                }
            )

        except BusinessError as e:
            return Response(
                {'code': e.code, 'message': e.message, 'details': e.details},
                status=e.status_code
            )

    @action(detail=True, methods=['get'], url_path='receipt')
    def receipt(self, request, pk=None):
        """Receipt metadata for an order."""
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

        pdf_url = None
        if receipt.pdf_file:
            pdf_url = request.build_absolute_uri(
                f'/api/v1/orders/{order.id}/receipt/pdf/'
            )

        return Response({
            'id': receipt.id,
            'receipt_number': receipt_number(receipt),
            'pdf_url': pdf_url,
            'order_code': order.code,
        })

    @action(detail=True, methods=['get'], url_path='receipt/pdf')
    def receipt_pdf(self, request, pk=None):
        """Download receipt PDF."""
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
