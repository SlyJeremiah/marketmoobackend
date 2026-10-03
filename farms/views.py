from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import FarmBoundary


class MyBoundaryView(APIView):
    """The signed-in farmer's own boundary. Nobody else's is ever returned."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        b = FarmBoundary.objects.filter(owner=request.user).first()
        if b is None:
            return Response({"detail": "No boundary saved."}, status=status.HTTP_404_NOT_FOUND)
        return Response({"id": str(b.id), "geometry": b.geometry, "area_ha": round(b.area_ha, 2), "centroid": {"lat": b.centroid_lat, "lon": b.centroid_lon},
                         "source": b.source, "updated_at": b.updated_at})

    def delete(self, request):
        FarmBoundary.objects.filter(owner=request.user).delete()
        return Response(status=status.HTTP_204_NO_CONTENT)
