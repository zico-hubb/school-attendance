from django.contrib.auth import get_user_model
from django.contrib.auth.backends import BaseBackend

from .managers import normalize_username


class SchoolCodeAuthenticationBackend(BaseBackend):
    def authenticate(
        self, request, school_code=None, username=None, password=None, **kwargs
    ):
        if not school_code or not username or password is None:
            return None
        user_model = get_user_model()
        try:
            user = user_model.objects.get(
                school__school_code=school_code,
                username=normalize_username(username),
            )
        except user_model.DoesNotExist:
            user_model().set_password(password)
            return None
        if user.check_password(password) and self.user_can_authenticate(user):
            return user
        return None

    @staticmethod
    def user_can_authenticate(user):
        return getattr(user, "is_active", True)

    def get_user(self, user_id):
        user_model = get_user_model()
        try:
            user = user_model.objects.get(pk=user_id)
        except user_model.DoesNotExist:
            return None
        return user if self.user_can_authenticate(user) else None
