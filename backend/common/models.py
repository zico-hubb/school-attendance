import uuid

from django.core.exceptions import ValidationError
from django.db import models


class UUIDModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    class Meta:
        abstract = True


class CreatedModel(UUIDModel):
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TimestampedModel(CreatedModel):
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SchoolOwnedModel(TimestampedModel):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_records",
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.pk and self.school_id:
            previous_school = (
                type(self).objects.filter(pk=self.pk)
                .values_list("school_id", flat=True)
                .first()
            )
            if previous_school is not None and previous_school != self.school_id:
                raise ValidationError({"school": "A record cannot change schools."})


class SchoolOwnedCreatedModel(CreatedModel):
    school = models.ForeignKey(
        "schools.School",
        on_delete=models.PROTECT,
        related_name="%(app_label)s_%(class)s_records",
    )

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        if self.pk and self.school_id:
            previous_school = (
                type(self).objects.filter(pk=self.pk)
                .values_list("school_id", flat=True)
                .first()
            )
            if previous_school is not None and previous_school != self.school_id:
                raise ValidationError({"school": "A record cannot change schools."})


class AppendOnlyModel(SchoolOwnedCreatedModel):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        if self.pk and type(self).objects.filter(pk=self.pk).exists():
            raise ValidationError("This record is append-only.")
        return super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise ValidationError("This record is append-only.")


def validate_same_school(instance, *related_objects):
    for related_object in related_objects:
        if (
            related_object is not None
            and related_object.school_id != instance.school_id
        ):
            raise ValidationError(
                {"school": "Related records must belong to the same school."}
            )


def validate_date_range(start, end, field_name="effective_to"):
    if end is not None and end < start:
        raise ValidationError({field_name: "The end date must not precede the start date."})
