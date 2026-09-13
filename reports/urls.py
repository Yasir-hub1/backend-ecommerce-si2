from django.urls import include, path
from rest_framework.routers import DefaultRouter

from reports.views import (
    DashboardView,
    ExportReportView,
    GenerateReportView,
    ReportRequestViewSet,
    ReportSummaryView,
)

router = DefaultRouter()
router.register(r'', ReportRequestViewSet, basename='report')

urlpatterns = [
    path('summary/', ReportSummaryView.as_view(), name='reports-summary'),
    path('dashboard/', DashboardView.as_view(), name='reports-dashboard'),
    path('generate/', GenerateReportView.as_view(), name='reports-generate'),
    path('export/<str:report_type>/', ExportReportView.as_view(), name='reports-export'),
    path('', include(router.urls)),
]
