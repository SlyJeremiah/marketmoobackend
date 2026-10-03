from django.urls import path

from .views import ListingFeedView, MyListingsView, PhotoPresignView, PoolCommitView, PoolListView

urlpatterns = [
    path("listings", ListingFeedView.as_view()),
    path("listings/mine", MyListingsView.as_view()),
    path("photos/presign", PhotoPresignView.as_view()),
    path("pools", PoolListView.as_view()),
    path("pools/<int:pk>/commitments", PoolCommitView.as_view()),
]
