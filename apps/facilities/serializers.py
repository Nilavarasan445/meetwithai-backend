from rest_framework import serializers
from .models import Facility


class FacilitySerializer(serializers.ModelSerializer):
    owner_email = serializers.ReadOnlyField(source="owner.email")

    class Meta:
        model = Facility
        fields = [
            "id",
            "name",
            "description",
            "owner",
            "owner_email",
            "members",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["owner", "created_at", "updated_at"]

    def create(self, validated_data):
        validated_data["owner"] = self.context["request"].user
        return super().create(validated_data)
