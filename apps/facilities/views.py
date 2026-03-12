from django.db import models
from rest_framework import viewsets, permissions
from .models import Facility
from .serializers import FacilitySerializer


class FacilityViewSet(viewsets.ModelViewSet):
    serializer_class = FacilitySerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        # A user can see facilities they own or are members of
        user = self.request.user
        return Facility.objects.filter(models.Q(owner=user) | models.Q(members=user)).distinct()

    def perform_create(self, serializer):
        serializer.save(owner=self.request.user)
