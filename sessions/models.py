import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ConsultationSession(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)

    class Status(models.TextChoices):
        UNASSIGNED = "unassigned", "Unassigned"
        ASSIGNED = "assigned", "Assigned"
        ACCEPTED = "accepted_by_provider", "Accepted by provider"
        IN_PROGRESS = "in_progress", "In progress"
        COMPLETED = "completed", "Completed"

    class EndedBy(models.TextChoices):
        USER = "user", "User"
        PROVIDER = "provider", "Provider"
        SYSTEM = "system", "System"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="consultation_sessions",
    )
    provider = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="provided_sessions",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=24, choices=Status.choices, default=Status.UNASSIGNED
    )
    per_minute_cost = models.DecimalField(max_digits=10, decimal_places=2)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)
    billed_minutes = models.PositiveIntegerField(default=0)
    billed_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    actual_talk_seconds = models.PositiveIntegerField(default=0)
    ended_by = models.CharField(max_length=10, choices=EndedBy.choices, blank=True)
    end_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.CheckConstraint(
                check=Q(per_minute_cost__gt=0), name="session_rate_positive"
            ),
            models.UniqueConstraint(
                fields=("user",),
                condition=Q(status="in_progress"),
                name="one_active_session_per_user",
            ),
        ]

    def __str__(self):
        return f"Session {self.pk}: {self.status}"


class SessionCharge(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)
    session = models.ForeignKey(
        ConsultationSession, on_delete=models.CASCADE, related_name="charges"
    )
    minute_number = models.PositiveIntegerField()
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    charged_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("minute_number",)
        constraints = [
            models.UniqueConstraint(
                fields=("session", "minute_number"), name="unique_session_minute_charge"
            )
        ]

    def __str__(self):
        return f"Session {self.session_id}, minute {self.minute_number}"
