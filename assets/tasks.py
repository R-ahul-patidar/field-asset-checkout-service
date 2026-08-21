import logging
from django.utils import timezone
from django.db import IntegrityError
from celery import shared_task

from .models import CheckOut, OverdueNotice

logger = logging.getLogger(__name__)


@shared_task(name='assets.tasks.flag_overdue_checkouts')
def flag_overdue_checkouts():
    """
    Periodic Celery background task:
    1. Queries all open check-outs where due_at is past now (returned_at__isnull=True, due_at__lt=now).
    2. Idempotently creates an OverdueNotice for today's date for each checkout.
    3. Handles database unique constraints gracefully so running multiple times in a single day
       never produces duplicate notices.
    """
    now = timezone.now()
    today = timezone.localdate()

    overdue_checkouts = CheckOut.objects.filter(
        returned_at__isnull=True,
        due_at__lt=now
    )

    created_count = 0
    skipped_count = 0

    for checkout in overdue_checkouts.iterator():
        try:
            _, created = OverdueNotice.objects.get_or_create(
                checkout=checkout,
                notice_date=today
            )
            if created:
                created_count += 1
            else:
                skipped_count += 1
        except IntegrityError:
            skipped_count += 1

    logger.info(
        "flag_overdue_checkouts finished for date %s: %d created, %d skipped/already existed.",
        today,
        created_count,
        skipped_count
    )
    return {
        "date": str(today),
        "notices_created": created_count,
        "notices_skipped": skipped_count
    }
