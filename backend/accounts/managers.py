import unicodedata

from django.contrib.auth.base_user import BaseUserManager


def normalize_username(value):
    return unicodedata.normalize("NFKC", value).strip().casefold()


class UserManager(BaseUserManager):
    use_in_migrations = True

    def create_user(self, username, password=None, *, school, **extra_fields):
        if not school:
            raise ValueError("A school is required for every user.")
        user = self.model(
            username=normalize_username(username), school=school, **extra_fields
        )
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, *, school, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("role", self.model.Role.SCHOOL_ADMIN)
        if extra_fields.get("is_staff") is not True:
            raise ValueError("A superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("A superuser must have is_superuser=True.")
        return self.create_user(
            username, password, school=school, **extra_fields
        )
