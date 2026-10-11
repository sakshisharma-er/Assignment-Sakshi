from django.urls import path

from .views import RechargeCallbackView, RechargeListCreateView, WalletDetailView

urlpatterns = [
    path("", WalletDetailView.as_view(), name="wallet-detail"),
    path("recharges/", RechargeListCreateView.as_view(), name="recharge-list"),
    path(
        "recharges/<str:reference>/callback/",
        RechargeCallbackView.as_view(),
        name="recharge-callback",
    ),
]
