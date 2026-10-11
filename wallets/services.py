from django.db import transaction
from django.db.models import F
from django.utils import timezone
from rest_framework.exceptions import ValidationError

from .models import RechargeTransaction, Wallet


@transaction.atomic
def process_recharge_callback(reference, status):
    recharge = RechargeTransaction.objects.select_for_update().get(reference=reference)

    if recharge.status == RechargeTransaction.Status.SUCCESS:
        if status != RechargeTransaction.Status.SUCCESS:
            raise ValidationError({"status": "A successful recharge cannot be changed."})
        return recharge

    if recharge.status == RechargeTransaction.Status.FAILED:
        if status != RechargeTransaction.Status.FAILED:
            raise ValidationError({"status": "A failed recharge cannot be changed."})
        return recharge

    if status == RechargeTransaction.Status.SUCCESS:
        wallet = Wallet.objects.select_for_update().get(user=recharge.user)
        Wallet.objects.filter(pk=wallet.pk).update(balance=F("balance") + recharge.amount)
        recharge.status = RechargeTransaction.Status.SUCCESS
        recharge.credited_at = timezone.now()
        recharge.save(update_fields=("status", "credited_at", "updated_at"))
    elif status == RechargeTransaction.Status.FAILED:
        recharge.status = RechargeTransaction.Status.FAILED
        recharge.save(update_fields=("status", "updated_at"))
    else:
        raise ValidationError({"status": "Callback status must be success or failed."})

    return recharge
