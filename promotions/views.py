"""
Views for promotions app.
"""
from django.utils import timezone
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.permissions import AllowAny
from rest_framework.views import APIView

from django_filters.rest_framework import DjangoFilterBackend
from rest_framework.filters import SearchFilter, OrderingFilter

from promotions.models import Promotion
from promotions.serializers import PromotionSerializer, PromotionValidateSerializer
from core.mixins import PublicReadRBACWriteMixin


class PromotionViewSet(PublicReadRBACWriteMixin, viewsets.ModelViewSet):
    """
    Promotion and coupon management.

    Admin manages promotions; customers validate codes at checkout.
    """

    queryset = Promotion.objects.prefetch_related(
        'categories', 'collections', 'products',
    ).all()
    serializer_class = PromotionSerializer
    write_permission = 'promotions.manage'
    filter_backends = [DjangoFilterBackend, SearchFilter, OrderingFilter]
    filterset_fields = ['is_active', 'discount_type']
    search_fields = ['name', 'code']
    ordering = ['-starts_at']

    def get_queryset(self):
        qs = super().get_queryset()
        if self.action in ('list', 'retrieve'):
            now = timezone.now()
            active_only = self.request.query_params.get('active_only')
            if active_only == 'true':
                return qs.filter(is_active=True, starts_at__lte=now, ends_at__gte=now)
        return qs


class ValidatePromotionView(APIView):
    """
    Public endpoint to validate a coupon before checkout.

    POST /api/v1/promotions/validate/
    """

    permission_classes = [AllowAny]

    def post(self, request):
        serializer = PromotionValidateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        code = serializer.validated_data['code'].strip().upper()
        order_amount = serializer.validated_data['order_amount']
        now = timezone.now()

        try:
            promo = Promotion.objects.get(code__iexact=code, is_active=True)
        except Promotion.DoesNotExist:
            return Response(
                {'valid': False, 'message': 'Código de promoción inválido'},
                status=status.HTTP_404_NOT_FOUND,
            )

        if promo.starts_at > now or promo.ends_at < now:
            return Response(
                {'valid': False, 'message': 'La promoción no está vigente'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if promo.max_uses is not None and promo.used_count >= promo.max_uses:
            return Response(
                {'valid': False, 'message': 'La promoción alcanzó el límite de usos'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if order_amount < promo.min_order_amount:
            return Response(
                {
                    'valid': False,
                    'message': f'Monto mínimo requerido: {promo.min_order_amount}',
                },
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({
            'valid': True,
            'promotion': PromotionSerializer(promo).data,
        })
