from rest_framework import serializers

from accounts.models import User
from accounts.serializers import UserSerializer

from .models import ConsultationSession, SessionCharge


class SessionChargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionCharge
        fields = ("minute_number", "amount", "charged_at")


class ConsultationSessionSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)
    provider = UserSerializer(read_only=True)
    charges = SessionChargeSerializer(many=True, read_only=True)

    class Meta:
        model = ConsultationSession
        fields = (
            "id",
            "user",
            "provider",
            "status",
            "per_minute_cost",
            "started_at",
            "ended_at",
            "billed_minutes",
            "billed_amount",
            "actual_talk_seconds",
            "ended_by",
            "end_reason",
            "charges",
            "created_at",
            "updated_at",
        )
        read_only_fields = (
            "id",
            "user",
            "provider",
            "status",
            "started_at",
            "ended_at",
            "billed_minutes",
            "billed_amount",
            "actual_talk_seconds",
            "ended_by",
            "end_reason",
            "charges",
            "created_at",
            "updated_at",
        )

    def validate_per_minute_cost(self, value):
        if value <= 0:
            raise serializers.ValidationError("Per-minute cost must be greater than zero.")
        return value

    def create(self, validated_data):
        request = self.context["request"]
        if request.user.role != User.Role.USER:
            raise serializers.ValidationError(
                {"detail": "Only users can create consultation sessions."}
            )
        return ConsultationSession.objects.create(user=request.user, **validated_data)


class AssignSessionSerializer(serializers.Serializer):
    provider_id = serializers.PrimaryKeyRelatedField(
        source="provider",
        queryset=User.objects.filter(role=User.Role.PROVIDER),
    )
