from rest_framework.permissions import BasePermission


class IsAuthenticated(BasePermission):
    message = "Change the temporary password before continuing."

    def has_permission(self, request, view):
        user = request.user
        return bool(
            user
            and user.is_authenticated
            and (
                not user.must_change_password
                or getattr(view, "allow_password_change", False)
            )
        )


class IsSchoolAdmin(BasePermission):
    message = "School administrator access is required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and not request.user.must_change_password
            and request.user.role == request.user.Role.SCHOOL_ADMIN
        )


class IsSchoolAdminOrAttendanceManager(BasePermission):
    message = "School configuration access is required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and not request.user.must_change_password
            and request.user.role
            in {
                request.user.Role.SCHOOL_ADMIN,
                request.user.Role.ATTENDANCE_MANAGER,
            }
        )
