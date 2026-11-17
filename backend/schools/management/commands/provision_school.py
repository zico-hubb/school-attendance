from getpass import getpass

from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import IntegrityError, transaction

from accounts.managers import normalize_username
from accounts.models import User
from audit.models import AuditLog
from schools.models import School


def format_validation_error(error, field_name=None):
    if hasattr(error, "message_dict"):
        return "; ".join(
            f"{field}: {message}"
            for field, messages in error.message_dict.items()
            for message in messages
        )
    return "; ".join(
        f"{field_name}: {message}" if field_name else message
        for message in error.messages
    )


class Command(BaseCommand):
    help = "Provision a school and its initial school administrator."

    def handle(self, *args, **options):
        name = input("School name: ").strip()
        school_code = input("School code: ").strip()
        username = normalize_username(input("Initial administrator username: "))

        school = School(name=name, school_code=school_code)
        try:
            school.full_clean()
        except ValidationError as error:
            raise CommandError(format_validation_error(error)) from error

        if School.objects.filter(school_code=school_code).exists():
            raise CommandError("A school with this code already exists.")

        password = getpass("Initial administrator password: ")
        password_confirmation = getpass("Confirm administrator password: ")
        if password != password_confirmation:
            raise CommandError("The password confirmation does not match.")

        administrator = User(
            username=username,
            school=school,
            role=User.Role.SCHOOL_ADMIN,
        )
        try:
            validate_password(password, user=administrator)
        except ValidationError as error:
            raise CommandError(format_validation_error(error, "password")) from error

        try:
            with transaction.atomic():
                school.save()
                administrator = User.objects.create_user(
                    username=username,
                    password=password,
                    school=school,
                    role=User.Role.SCHOOL_ADMIN,
                )
                AuditLog.objects.create(
                    school=school,
                    action="SCHOOL_PROVISIONED",
                    entity_type="School",
                    entity_id=school.pk,
                    after_data={
                        "school_code": school.school_code,
                        "administrator_username": administrator.username,
                    },
                    reason=(
                        "Provisioned using the provision_school management command. "
                        "The platform operator identity is not captured."
                    ),
                )
        except ValidationError as error:
            raise CommandError(format_validation_error(error)) from error
        except IntegrityError as error:
            raise CommandError(
                "Provisioning failed because the school code or administrator "
                "username is already in use."
            ) from error

        self.stdout.write(
            self.style.SUCCESS(
                f"School {school.school_code} and administrator "
                f"{administrator.username} provisioned successfully."
            )
        )
