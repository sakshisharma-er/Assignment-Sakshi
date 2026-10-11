from rest_framework import status
from rest_framework.test import APITestCase

from wallets.models import Wallet
from .models import User


class AuthenticationAPITests(APITestCase):
    def test_registration_creates_user_and_wallet(self):
        response = self.client.post(
            "/api/auth/register/",
            {
                "username": "new-user",
                "email": "new@example.com",
                "password": "StrongPass123!",
                "role": User.Role.USER,
            },
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        user = User.objects.get(username="new-user")
        self.assertTrue(user.check_password("StrongPass123!"))
        self.assertTrue(Wallet.objects.filter(user=user).exists())

    def test_token_login_and_profile(self):
        user = User.objects.create_user(
            username="token-user", password="StrongPass123!", role=User.Role.PROVIDER
        )
        token_response = self.client.post(
            "/api/auth/token/",
            {"username": "token-user", "password": "StrongPass123!"},
            format="json",
        )

        self.assertEqual(token_response.status_code, status.HTTP_200_OK)
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Token {token_response.data['token']}"
        )
        profile = self.client.get("/api/auth/me/")
        self.assertEqual(profile.status_code, status.HTTP_200_OK)
        self.assertEqual(profile.data["id"], user.pk)
        self.assertEqual(profile.data["role"], User.Role.PROVIDER)

    def test_profile_requires_authentication(self):
        response = self.client.get("/api/auth/me/")
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_registration_rejects_invalid_role_and_weak_password(self):
        invalid_role = self.client.post(
            "/api/auth/register/",
            {
                "username": "bad-role",
                "password": "StrongPass123!",
                "role": "ADMIN",
            },
            format="json",
        )
        weak_password = self.client.post(
            "/api/auth/register/",
            {
                "username": "weak-password",
                "password": "123",
                "role": User.Role.USER,
            },
            format="json",
        )

        self.assertEqual(invalid_role.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(weak_password.status_code, status.HTTP_400_BAD_REQUEST)
