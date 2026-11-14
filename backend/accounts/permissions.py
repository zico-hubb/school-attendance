from rest_framework.permissions import BasePermission


class IsSchoolAdmin(BasePermission):
    message = "School administrator access is required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role == request.user.Role.SCHOOL_ADMIN
        )


class IsSchoolAdminOrAttendanceManager(BasePermission):
    message = "School configuration access is required."

    def has_permission(self, request, view):
        return bool(
            request.user
            and request.user.is_authenticated
            and request.user.role
            in {
                request.user.Role.SCHOOL_ADMIN,
                request.user.Role.ATTENDANCE_MANAGER,
            }
        )
