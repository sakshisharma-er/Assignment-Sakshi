from rest_framework import serializers

from .models import RechargeTransaction, Wallet


class WalletSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wallet
        fields = ("balance", "updated_at")
        read_only_fields = fields


class RechargeSerializer(serializers.ModelSerializer):
    class Meta:
        model = RechargeTransaction
        fields = (
            "id",
            "amount",
            "reference",
            "status",
            "credited_at",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("id", "status", "credited_at", "created_at", "updated_at")

    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Amount must be greater than zero.")
        return value

    def create(self, validated_data):
        return RechargeTransaction.objects.create(
            user=self.context["request"].user, **validated_data
        )


class RechargeCallbackSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=(
            RechargeTransaction.Status.SUCCESS,
            RechargeTransaction.Status.FAILED,
        )
    )
