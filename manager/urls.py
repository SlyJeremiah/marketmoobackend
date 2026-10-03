from django.urls import path

from . import views as v

urlpatterns = [
    path("stats", v.StatsView.as_view()),
    path("listings", v.ListingsView.as_view()),
    path("listings/<uuid:pk>/status", v.ListingStatusView.as_view()),
    path("users", v.UsersView.as_view()),
    path("users/<int:pk>/verify", v.UserVerifyView.as_view()),
    path("reports", v.ReportsView.as_view()),
    path("reports/<uuid:pk>/status", v.ReportStatusView.as_view()),
    path("reports/<uuid:pk>/publish", v.OutbreakPublishFromReportView.as_view()),
    path("outbreaks", v.OutbreaksView.as_view()),
    path("outbreaks/<int:pk>/close", v.OutbreakCloseView.as_view()),
    path("pools", v.PoolsView.as_view()),
    path("pools/<int:pk>/status", v.PoolStatusView.as_view()),
    path("packs", v.PacksView.as_view()),
]
