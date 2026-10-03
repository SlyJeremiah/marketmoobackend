from django.urls import path

from .views import ActiveOutbreaksView, ReportView, ZoneCheckView

urlpatterns = [
    path("outbreaks/active", ActiveOutbreaksView.as_view()),
    path("outbreaks/zone-check", ZoneCheckView.as_view()),
    path("outbreak-reports", ReportView.as_view()),
]
