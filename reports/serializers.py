"""Reports API serializers."""
from rest_framework import serializers

from reports.models import ReportRequest


class ReportRequestSerializer(serializers.ModelSerializer):
    prompt = serializers.CharField(source='prompt_text', read_only=True)
    result_text = serializers.SerializerMethodField()
    report_type = serializers.SerializerMethodField()

    class Meta:
        model = ReportRequest
        fields = [
            'id',
            'report_type',
            'status',
            'prompt',
            'result_text',
            'created_at',
        ]

    def get_result_text(self, obj: ReportRequest) -> str:
        if isinstance(obj.result, dict):
            return obj.result.get('text', '')
        return str(obj.result or '')

    def get_report_type(self, obj: ReportRequest) -> str:
        if isinstance(obj.interpreted_spec, dict):
            return obj.interpreted_spec.get('report_type', 'GENERATIVE')
        return 'GENERATIVE'


class GenerateReportSerializer(serializers.Serializer):
    prompt = serializers.CharField()
    report_type = serializers.CharField(required=False, allow_blank=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
