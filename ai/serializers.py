"""AI API serializers."""
from rest_framework import serializers


class ChatMessageSerializer(serializers.Serializer):
    role = serializers.ChoiceField(choices=['user', 'assistant'])
    content = serializers.CharField()


class ChatRequestSerializer(serializers.Serializer):
    messages = ChatMessageSerializer(many=True, min_length=1)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
