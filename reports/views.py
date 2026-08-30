"""Reports API views."""
from django.http import HttpResponse
from rest_framework import viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.models import Role
from core.exceptions import BusinessError
from core.permissions import HasAppPermission
from reports.models import ReportRequest
from reports.serializers import GenerateReportSerializer, ReportRequestSerializer
from reports.services import EXPORT_REPORT_TYPES, build_report_summary, export_report_csv, generate_report


class ReportsAccessMixin:
    permission_classes = [IsAuthenticated, HasAppPermission]
    required_permission = 'reports.view'


class ReportSummaryView(ReportsAccessMixin, APIView):
    def get(self, request):
        branch_id = request.query_params.get('branch_id')
        summary = build_report_summary(
            branch_id=int(branch_id) if branch_id else None,
            date_from=request.query_params.get('from'),
            date_to=request.query_params.get('to'),
        )
        return Response(summary)


class ReportRequestViewSet(ReportsAccessMixin, viewsets.ReadOnlyModelViewSet):
    serializer_class = ReportRequestSerializer

    def get_queryset(self):
        user = self.request.user
        if user.role == Role.ADMIN:
            return ReportRequest.objects.all().order_by('-created_at')
        return ReportRequest.objects.filter(user=user).order_by('-created_at')


class GenerateReportView(ReportsAccessMixin, APIView):
    def post(self, request):
        serializer = GenerateReportSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        report = generate_report(
            user=request.user,
            prompt=serializer.validated_data['prompt'],
            report_type=serializer.validated_data.get('report_type'),
            branch_id=serializer.validated_data.get('branch_id'),
        )
        return Response(ReportRequestSerializer(report).data, status=201)


class ExportReportView(ReportsAccessMixin, APIView):
    def get(self, request, report_type):
        if report_type not in EXPORT_REPORT_TYPES:
            raise BusinessError(
                code='INVALID_REPORT_TYPE',
                message=f'Tipo de exportación no soportado: {report_type}',
                status_code=400,
                details={'allowed_types': sorted(EXPORT_REPORT_TYPES)},
            )

        branch_id = request.query_params.get('branch_id')
        csv_content = export_report_csv(
            report_type=report_type,
            branch_id=int(branch_id) if branch_id else None,
            date_from=request.query_params.get('from'),
            date_to=request.query_params.get('to'),
        )
        response = HttpResponse(csv_content, content_type='text/csv; charset=utf-8')
        response['Content-Disposition'] = (
            f'attachment; filename="{report_type}-{request.query_params.get("from", "all")}.csv"'
        )
        return response
