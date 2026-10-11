from decimal import Decimal

from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from .models import RechargeTransaction


class RechargeAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(username="wallet-user", password="pass12345")
        self.client.force_authenticate(self.user)

    def test_duplicate_success_callback_credits_wallet_once(self):
        response = self.client.post(
            "/api/wallet/recharges/",
            {"amount": "500.00", "reference": "payment-ref-1"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)

        self.client.force_authenticate(user=None)
        callback_url = "/api/wallet/recharges/payment-ref-1/callback/"
        first = self.client.post(callback_url, {"status": "success"}, format="json")
        second = self.client.post(callback_url, {"status": "success"}, format="json")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.user.wallet.refresh_from_db()
        transaction = RechargeTransaction.objects.get(reference="payment-ref-1")
        self.assertEqual(self.user.wallet.balance, Decimal("500.00"))
        self.assertEqual(transaction.status, RechargeTransaction.Status.SUCCESS)
        self.assertIsNotNone(transaction.credited_at)

    def test_recharge_amount_must_be_positive(self):
        response = self.client.post(
            "/api/wallet/recharges/", {"amount": "0.00"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_pending_recharge_does_not_change_balance(self):
        response = self.client.post(
            "/api/wallet/recharges/",
            {"amount": "75.00", "reference": "pending-ref"},
            format="json",
        )

        self.user.wallet.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data["status"], RechargeTransaction.Status.PENDING)
        self.assertEqual(self.user.wallet.balance, Decimal("0.00"))

    def test_failed_callback_is_idempotent_and_does_not_credit(self):
        self.client.post(
            "/api/wallet/recharges/",
            {"amount": "75.00", "reference": "failed-ref"},
            format="json",
        )
        callback_url = "/api/wallet/recharges/failed-ref/callback/"

        first = self.client.post(callback_url, {"status": "failed"}, format="json")
        second = self.client.post(callback_url, {"status": "failed"}, format="json")

        self.user.wallet.refresh_from_db()
        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(self.user.wallet.balance, Decimal("0.00"))

    def test_terminal_callback_cannot_be_reversed(self):
        self.client.post(
            "/api/wallet/recharges/",
            {"amount": "75.00", "reference": "terminal-ref"},
            format="json",
        )
        callback_url = "/api/wallet/recharges/terminal-ref/callback/"
        self.client.post(callback_url, {"status": "success"}, format="json")

        response = self.client.post(callback_url, {"status": "failed"}, format="json")

        self.user.wallet.refresh_from_db()
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(self.user.wallet.balance, Decimal("75.00"))

    def test_recharge_list_is_scoped_to_authenticated_user(self):
        RechargeTransaction.objects.create(
            user=self.user, amount=Decimal("10.00"), reference="own-ref"
        )
        other = User.objects.create_user(username="other-wallet", password="pass12345")
        RechargeTransaction.objects.create(
            user=other, amount=Decimal("20.00"), reference="other-ref"
        )

        response = self.client.get("/api/wallet/recharges/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data), 1)
        self.assertEqual(response.data[0]["reference"], "own-ref")

    def test_wallet_endpoint_requires_authentication_and_returns_balance(self):
        response = self.client.get("/api/wallet/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(Decimal(response.data["balance"]), Decimal("0.00"))

        self.client.force_authenticate(user=None)
        unauthorized = self.client.get("/api/wallet/")
        self.assertEqual(unauthorized.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_unknown_callback_reference_returns_404(self):
        self.client.force_authenticate(user=None)
        response = self.client.post(
            "/api/wallet/recharges/does-not-exist/callback/",
            {"status": "success"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
