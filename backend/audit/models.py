from django.db import models
from django.core.exceptions import ValidationError

from common.models import AppendOnlyModel


class AuditLog(AppendOnlyModel):
    actor_user = models.ForeignKey(
        "accounts.User",
        on_delete=models.PROTECT,
        related_name="audit_logs",
        null=True,
        blank=True,
    )
    action = models.CharField(max_length=80)
    entity_type = models.CharField(max_length=120)
    entity_id = models.UUIDField()
    before_data = models.JSONField(null=True, blank=True)
    after_data = models.JSONField(null=True, blank=True)
    reason = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def clean(self):
        super().clean()
        if self.actor_user_id and self.actor_user.school_id != self.school_id:
            raise ValidationError(
                {"actor_user": "The actor must belong to this school."}
            )
