from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from accounts.models import User
from .models import ConsultationSession, SessionCharge


class ConsultationSessionAPITests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username="customer", password="pass12345", role=User.Role.USER
        )
        self.provider = User.objects.create_user(
            username="provider", password="pass12345", role=User.Role.PROVIDER
        )
        self.other_user = User.objects.create_user(
            username="other-customer", password="pass12345", role=User.Role.USER
        )
        self.other_provider = User.objects.create_user(
            username="other-provider",
            password="pass12345",
            role=User.Role.PROVIDER,
        )

    def _create_accepted_session(self, rate="50.00"):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            "/api/sessions/", {"per_minute_cost": rate}, format="json"
        )
        self.assertEqual(created.status_code, status.HTTP_201_CREATED)
        session_id = created.data["id"]
        assigned = self.client.post(
            f"/api/sessions/{session_id}/assign/",
            {"provider_id": self.provider.pk},
            format="json",
        )
        self.assertEqual(assigned.status_code, status.HTTP_200_OK)
        self.client.force_authenticate(self.provider)
        accepted = self.client.post(f"/api/sessions/{session_id}/accept/")
        self.assertEqual(accepted.status_code, status.HTTP_200_OK)
        return ConsultationSession.objects.get(pk=session_id)

    def _start(self, session, balance=Decimal("500.00")):
        self.user.wallet.balance = balance
        self.user.wallet.save(update_fields=("balance",))
        self.client.force_authenticate(self.user)
        response = self.client.post(f"/api/sessions/{session.pk}/start/")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        return session

    def test_insufficient_five_minute_balance_cannot_start(self):
        session = self._create_accepted_session()
        self.user.wallet.balance = Decimal("249.99")
        self.user.wallet.save(update_fields=("balance",))

        self.client.force_authenticate(self.user)
        response = self.client.post(f"/api/sessions/{session.pk}/start/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        session.refresh_from_db()
        self.assertEqual(session.status, ConsultationSession.Status.ACCEPTED)

    def test_happy_path_recharge_bill_two_minutes_and_end(self):
        self.client.force_authenticate(self.user)
        recharge = self.client.post(
            "/api/wallet/recharges/",
            {"amount": "500.00", "reference": "happy-path-recharge"},
            format="json",
        )
        self.assertEqual(recharge.status_code, status.HTTP_201_CREATED)
        callback = self.client.post(
            "/api/wallet/recharges/happy-path-recharge/callback/",
            {"status": "success"},
            format="json",
        )
        self.assertEqual(callback.status_code, status.HTTP_200_OK)

        session = self._create_accepted_session()
        session = self._start(session)
        started_at = timezone.now() - timedelta(minutes=2, seconds=5)
        ConsultationSession.objects.filter(pk=session.pk).update(started_at=started_at)

        billed = self.client.post(f"/api/sessions/{session.pk}/bill/")
        ended = self.client.post(f"/api/sessions/{session.pk}/end/")

        self.assertEqual(billed.status_code, status.HTTP_200_OK)
        self.assertEqual(ended.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.user.wallet.refresh_from_db()
        self.assertEqual(session.status, ConsultationSession.Status.COMPLETED)
        self.assertEqual(session.billed_minutes, 2)
        self.assertEqual(session.billed_amount, Decimal("100.00"))
        self.assertEqual(session.ended_by, ConsultationSession.EndedBy.USER)
        self.assertEqual(self.user.wallet.balance, Decimal("400.00"))

    def test_balance_runs_out_and_system_ends_session(self):
        session = self._start(
            self._create_accepted_session(), balance=Decimal("250.00")
        )
        ConsultationSession.objects.filter(pk=session.pk).update(
            started_at=timezone.now() - timedelta(minutes=6, seconds=5)
        )

        response = self.client.post(f"/api/sessions/{session.pk}/bill/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.user.wallet.refresh_from_db()
        self.assertEqual(session.status, ConsultationSession.Status.COMPLETED)
        self.assertEqual(session.ended_by, ConsultationSession.EndedBy.SYSTEM)
        self.assertEqual(session.end_reason, "Insufficient balance")
        self.assertEqual(session.billed_minutes, 5)
        self.assertGreaterEqual(session.actual_talk_seconds, 360)
        self.assertEqual(self.user.wallet.balance, Decimal("0.00"))

    def test_ending_before_start_is_invalid_transition(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            "/api/sessions/", {"per_minute_cost": "50.00"}, format="json"
        )

        response = self.client.post(f"/api/sessions/{created.data['id']}/end/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot end", response.data["detail"])

    def test_duplicate_billing_does_not_charge_same_minute_twice(self):
        session = self._start(self._create_accepted_session())
        ConsultationSession.objects.filter(pk=session.pk).update(
            started_at=timezone.now() - timedelta(minutes=1, seconds=5)
        )

        first = self.client.post(f"/api/sessions/{session.pk}/bill/")
        second = self.client.post(f"/api/sessions/{session.pk}/bill/")

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.user.wallet.refresh_from_db()
        self.assertEqual(session.billed_minutes, 1)
        self.assertEqual(SessionCharge.objects.filter(session=session).count(), 1)
        self.assertEqual(self.user.wallet.balance, Decimal("450.00"))

    def test_user_cannot_have_two_active_sessions(self):
        first = self._start(self._create_accepted_session())
        second = self._create_accepted_session()

        self.client.force_authenticate(self.user)
        response = self.client.post(f"/api/sessions/{second.pk}/start/")

        self.assertEqual(first.status, ConsultationSession.Status.IN_PROGRESS)
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_exact_five_minute_balance_can_start(self):
        session = self._create_accepted_session()

        started = self._start(session, balance=Decimal("250.00"))

        self.assertEqual(started.status, ConsultationSession.Status.IN_PROGRESS)
        self.user.wallet.refresh_from_db()
        self.assertEqual(self.user.wallet.balance, Decimal("250.00"))

    def test_provider_cannot_create_a_customer_session(self):
        self.client.force_authenticate(self.provider)
        response = self.client.post(
            "/api/sessions/", {"per_minute_cost": "50.00"}, format="json"
        )
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_non_provider_cannot_be_assigned(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            "/api/sessions/", {"per_minute_cost": "50.00"}, format="json"
        )

        response = self.client.post(
            f"/api/sessions/{created.data['id']}/assign/",
            {"provider_id": self.other_user.pk},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)

    def test_only_assigned_provider_can_accept(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            "/api/sessions/", {"per_minute_cost": "50.00"}, format="json"
        )
        session_id = created.data["id"]
        self.client.post(
            f"/api/sessions/{session_id}/assign/",
            {"provider_id": self.provider.pk},
            format="json",
        )

        user_attempt = self.client.post(f"/api/sessions/{session_id}/accept/")
        self.client.force_authenticate(self.other_provider)
        other_provider_attempt = self.client.post(
            f"/api/sessions/{session_id}/accept/"
        )

        self.assertEqual(user_attempt.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(
            other_provider_attempt.status_code, status.HTTP_404_NOT_FOUND
        )

    def test_invalid_transition_cannot_start_unassigned_session(self):
        self.client.force_authenticate(self.user)
        created = self.client.post(
            "/api/sessions/", {"per_minute_cost": "50.00"}, format="json"
        )

        response = self.client.post(f"/api/sessions/{created.data['id']}/start/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot start", response.data["detail"])

    def test_provider_can_end_session_and_actor_is_recorded(self):
        session = self._start(self._create_accepted_session())
        self.client.force_authenticate(self.provider)

        response = self.client.post(f"/api/sessions/{session.pk}/end/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.assertEqual(session.status, ConsultationSession.Status.COMPLETED)
        self.assertEqual(session.ended_by, ConsultationSession.EndedBy.PROVIDER)

    def test_billing_before_a_full_minute_does_not_charge(self):
        session = self._start(self._create_accepted_session())
        ConsultationSession.objects.filter(pk=session.pk).update(
            started_at=timezone.now() - timedelta(seconds=59)
        )

        response = self.client.post(f"/api/sessions/{session.pk}/bill/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.user.wallet.refresh_from_db()
        self.assertEqual(session.billed_minutes, 0)
        self.assertEqual(self.user.wallet.balance, Decimal("500.00"))

    def test_billing_charges_affordable_minutes_then_system_ends(self):
        session = self._start(self._create_accepted_session())
        self.user.wallet.balance = Decimal("120.00")
        self.user.wallet.save(update_fields=("balance",))
        ConsultationSession.objects.filter(pk=session.pk).update(
            started_at=timezone.now() - timedelta(minutes=3, seconds=5)
        )

        response = self.client.post(f"/api/sessions/{session.pk}/bill/")

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        session.refresh_from_db()
        self.user.wallet.refresh_from_db()
        self.assertEqual(session.status, ConsultationSession.Status.COMPLETED)
        self.assertEqual(session.billed_minutes, 2)
        self.assertEqual(session.billed_amount, Decimal("100.00"))
        self.assertEqual(self.user.wallet.balance, Decimal("20.00"))
        self.assertEqual(SessionCharge.objects.filter(session=session).count(), 2)

    def test_completed_session_cannot_be_billed_again(self):
        session = self._start(self._create_accepted_session())
        self.client.post(f"/api/sessions/{session.pk}/end/")

        response = self.client.post(f"/api/sessions/{session.pk}/bill/")

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("Cannot bill", response.data["detail"])

    def test_session_list_is_visible_only_to_participants(self):
        session = self._create_accepted_session()
        self.client.force_authenticate(self.other_user)

        listing = self.client.get("/api/sessions/")
        detail = self.client.get(f"/api/sessions/{session.pk}/")

        self.assertEqual(listing.status_code, status.HTTP_200_OK)
        self.assertEqual(listing.data, [])
        self.assertEqual(detail.status_code, status.HTTP_404_NOT_FOUND)

    def test_session_rate_cannot_be_modified(self):
        session = self._create_accepted_session()
        self.client.force_authenticate(self.user)

        response = self.client.patch(
            f"/api/sessions/{session.pk}/",
            {"per_minute_cost": "1.00"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_405_METHOD_NOT_ALLOWED)
        session.refresh_from_db()
        self.assertEqual(session.per_minute_cost, Decimal("50.00"))
