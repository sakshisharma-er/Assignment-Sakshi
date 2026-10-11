from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from accounts.models import User
from wallets.models import Wallet

from .models import ConsultationSession, SessionCharge


def _transition_error(action, status):
    raise ValidationError(
        {"detail": f"Cannot {action} a session while it is '{status}'."}
    )


@transaction.atomic
def assign_session(session_id, actor, provider):
    session = ConsultationSession.objects.select_for_update().get(pk=session_id)
    if actor != session.user and not actor.is_staff:
        raise ValidationError({"detail": "Only the session user can assign a provider."})
    if session.status != ConsultationSession.Status.UNASSIGNED:
        _transition_error("assign", session.status)
    if provider.role != User.Role.PROVIDER:
        raise ValidationError({"provider": "The selected account is not a provider."})
    if provider == session.user:
        raise ValidationError({"provider": "A user cannot be their own provider."})

    session.provider = provider
    session.status = ConsultationSession.Status.ASSIGNED
    session.save(update_fields=("provider", "status", "updated_at"))
    return session


@transaction.atomic
def accept_session(session_id, actor):
    session = ConsultationSession.objects.select_for_update().get(pk=session_id)
    if actor != session.provider:
        raise ValidationError({"detail": "Only the assigned provider can accept."})
    if session.status != ConsultationSession.Status.ASSIGNED:
        _transition_error("accept", session.status)

    session.status = ConsultationSession.Status.ACCEPTED
    session.save(update_fields=("status", "updated_at"))
    return session


@transaction.atomic
def start_session(session_id, actor, at=None):
    session = ConsultationSession.objects.select_for_update().get(pk=session_id)
    if actor != session.user:
        raise ValidationError({"detail": "Only the session user can start the session."})
    if session.status != ConsultationSession.Status.ACCEPTED:
        _transition_error("start", session.status)

    wallet = Wallet.objects.select_for_update().get(user=session.user)
    minimum_balance = session.per_minute_cost * Decimal("5")
    if wallet.balance < minimum_balance:
        raise ValidationError(
            {
                "detail": "Insufficient balance to start the session.",
                "minimum_required": str(minimum_balance),
                "current_balance": str(wallet.balance),
            }
        )
    if (
        ConsultationSession.objects.select_for_update()
        .filter(user=session.user, status=ConsultationSession.Status.IN_PROGRESS)
        .exclude(pk=session.pk)
        .exists()
    ):
        raise ValidationError({"detail": "The user already has an active session."})

    session.status = ConsultationSession.Status.IN_PROGRESS
    session.started_at = at or timezone.now()
    try:
        session.save(update_fields=("status", "started_at", "updated_at"))
    except IntegrityError:
        raise ValidationError({"detail": "The user already has an active session."})
    return session


def _bill_locked(session, as_of):
    elapsed_seconds = max(0, int((as_of - session.started_at).total_seconds()))
    elapsed_minutes = elapsed_seconds // 60
    minutes_due = max(0, elapsed_minutes - session.billed_minutes)
    if minutes_due == 0:
        return session

    wallet = Wallet.objects.select_for_update().get(user=session.user)
    affordable_minutes = int(wallet.balance // session.per_minute_cost)
    minutes_to_charge = min(minutes_due, affordable_minutes)

    if minutes_to_charge:
        total = session.per_minute_cost * minutes_to_charge
        first_minute = session.billed_minutes + 1
        SessionCharge.objects.bulk_create(
            [
                SessionCharge(
                    session=session,
                    minute_number=minute,
                    amount=session.per_minute_cost,
                )
                for minute in range(first_minute, first_minute + minutes_to_charge)
            ]
        )
        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") - total)
        session.billed_minutes += minutes_to_charge
        session.billed_amount += total

    if minutes_to_charge < minutes_due:
        session.status = ConsultationSession.Status.COMPLETED
        session.ended_at = as_of
        session.actual_talk_seconds = elapsed_seconds
        session.ended_by = ConsultationSession.EndedBy.SYSTEM
        session.end_reason = "Insufficient balance"

    session.save(
        update_fields=(
            "billed_minutes",
            "billed_amount",
            "status",
            "ended_at",
            "actual_talk_seconds",
            "ended_by",
            "end_reason",
            "updated_at",
        )
    )
    return session


@transaction.atomic
def bill_session(session_id, as_of=None):
    session = ConsultationSession.objects.select_for_update().get(pk=session_id)
    if session.status != ConsultationSession.Status.IN_PROGRESS:
        _transition_error("bill", session.status)
    return _bill_locked(session, as_of or timezone.now())


@transaction.atomic
def end_session(session_id, actor, as_of=None):
    session = ConsultationSession.objects.select_for_update().get(pk=session_id)
    if session.status != ConsultationSession.Status.IN_PROGRESS:
        _transition_error("end", session.status)
    if actor == session.user:
        ended_by = ConsultationSession.EndedBy.USER
    elif actor == session.provider:
        ended_by = ConsultationSession.EndedBy.PROVIDER
    else:
        raise ValidationError({"detail": "Only a session participant can end it."})

    ended_at = as_of or timezone.now()
    session = _bill_locked(session, ended_at)
    if session.status == ConsultationSession.Status.COMPLETED:
        return session

    session.status = ConsultationSession.Status.COMPLETED
    session.ended_at = ended_at
    session.actual_talk_seconds = max(
        0, int((ended_at - session.started_at).total_seconds())
    )
    session.ended_by = ended_by
    session.end_reason = f"Ended by {ended_by}"
    session.save(
        update_fields=(
            "status",
            "ended_at",
            "actual_talk_seconds",
            "ended_by",
            "end_reason",
            "updated_at",
        )
    )
    return session
