"""AI API views."""
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticatedOrReadOnly
from rest_framework.response import Response
from rest_framework.views import APIView

from ai.models import BrowsingEvent, EventType
from ai.models import BrowsingEvent, EventType
from ai.serializers import ChatRequestSerializer
from ai.services import chat_with_assistant, get_recommendations


class ChatView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = ChatRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        result = chat_with_assistant(
            messages=serializer.validated_data['messages'],
            branch_id=serializer.validated_data.get('branch_id'),
            request=request,
        )
        return Response({
            'reply': result['reply'],
            'suggestions': result.get('suggestions', []),
            'products': result.get('products', []),
        })


class RecommendationsView(APIView):
    permission_classes = [IsAuthenticatedOrReadOnly]

    def get(self, request):
        branch_id = request.query_params.get('branch_id')
        limit = int(request.query_params.get('limit', 8))

        result = get_recommendations(
            user=request.user,
            branch_id=int(branch_id) if branch_id else None,
            limit=limit,
            request=request,
        )
        return Response(result)


class BrowsingEventView(APIView):
    permission_classes = [AllowAny]

    def post(self, request):
        event_type = request.data.get('event_type')
        allowed = {choice[0] for choice in EventType.CHOICES}
        if event_type not in allowed:
            return Response({'detail': 'event_type inválido'}, status=status.HTTP_400_BAD_REQUEST)

        customer = None
        if request.user.is_authenticated and hasattr(request.user, 'customer_profile'):
            customer = request.user.customer_profile

        BrowsingEvent.objects.create(
            customer=customer,
            product_id=request.data.get('product_id'),
            event_type=event_type,
            query=request.data.get('query', '')[:200],
        )
        return Response({'ok': True}, status=status.HTTP_201_CREATED)
