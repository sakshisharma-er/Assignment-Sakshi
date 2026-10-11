from django.shortcuts import get_object_or_404
from rest_framework import generics, permissions
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import RechargeTransaction, Wallet
from .serializers import (
    RechargeCallbackSerializer,
    RechargeSerializer,
    WalletSerializer,
)
from .services import process_recharge_callback


class WalletDetailView(APIView):
    def get(self, request):
        wallet, _ = Wallet.objects.get_or_create(user=request.user)
        return Response(WalletSerializer(wallet).data)


class RechargeListCreateView(generics.ListCreateAPIView):
    serializer_class = RechargeSerializer

    def get_queryset(self):
        return RechargeTransaction.objects.filter(user=self.request.user)


class RechargeCallbackView(APIView):
    permission_classes = [permissions.AllowAny]

    def post(self, request, reference):
        get_object_or_404(RechargeTransaction, reference=reference)
        serializer = RechargeCallbackSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        recharge = process_recharge_callback(reference, serializer.validated_data["status"])
        return Response(RechargeSerializer(recharge).data)
