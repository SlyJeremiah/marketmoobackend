from django.urls import path

from .views import DownloadView, ManifestView

urlpatterns = [
    path("packs/manifest", ManifestView.as_view()),
    path("packs/<int:pk>/download", DownloadView.as_view()),
]
