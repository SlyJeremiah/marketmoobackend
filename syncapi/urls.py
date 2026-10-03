from django.urls import path

from .views import SyncView

urlpatterns = [path("sync", SyncView.as_view())]
