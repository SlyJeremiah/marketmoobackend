from django.urls import path

from .views import MyBoundaryView

urlpatterns = [path("farm/boundary", MyBoundaryView.as_view())]
