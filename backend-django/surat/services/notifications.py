import logging

from django.db import transaction

from ..models import Notification

logger = logging.getLogger(__name__)


def notify_user(user, notification_type, title, body, surat_request=None):
    if not user:
        return None

    def create():
        return Notification.objects.create(
            user=user,
            type=notification_type,
            title=title,
            body=body,
            surat_request=surat_request,
        )

    if transaction.get_connection().in_atomic_block:
        transaction.on_commit(create)
        return None
    try:
        return create()
    except Exception:
        logger.exception("Gagal membuat notifikasi ASURA untuk user=%s", user.pk)
        return None
