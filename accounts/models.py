import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, unique=True)

    class Role(models.TextChoices):
        USER = "USER", "User"
        PROVIDER = "PROVIDER", "Provider"

    role = models.CharField(max_length=10, choices=Role.choices, default=Role.USER)

    def __str__(self):
        return f"{self.username} ({self.role})"
