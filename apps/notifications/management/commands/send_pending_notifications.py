from collections import Counter

from django.core.management.base import BaseCommand

from apps.notifications.models import DeliveryStatus
from apps.notifications.services import dispatch_pending


class Command(BaseCommand):
    help = "Deliver pending notifications (run periodically to retry failures)."

    def add_arguments(self, parser):
        parser.add_argument("--limit", type=int, default=100)

    def handle(self, *args, **options):
        counts = Counter(n.delivery_status for n in dispatch_pending(limit=options["limit"]))
        self.stdout.write(
            f"sent={counts[DeliveryStatus.SENT]} "
            f"failed={counts[DeliveryStatus.FAILED]} "
            f"pending={counts[DeliveryStatus.PENDING]}"
        )
