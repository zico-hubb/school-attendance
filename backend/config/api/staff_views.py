from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.permissions import IsSchoolAdmin
from staff.models import StaffProfile
from staff.serializers import (
    StaffCreateSerializer,
    StaffSerializer,
    StaffUpdateSerializer,
)


def translate_model_validation(error):
    detail = error.message_dict if hasattr(error, "message_dict") else error.messages
    raise serializers.ValidationError(detail) from error


def save_serializer(serializer):
    try:
        return serializer.save()
    except DjangoValidationError as error:
        translate_model_validation(error)
    except IntegrityError as error:
        raise serializers.ValidationError(
            {"detail": "A username or employee number already exists in this school."}
        ) from error


class StaffListCreateView(APIView):
    permission_classes = [IsSchoolAdmin]

    def get_queryset(self, request):
        return StaffProfile.objects.filter(school=request.user.school).select_related(
            "user", "department"
        )

    def get(self, request, version):
        profiles = self.get_queryset(request)
        return Response(StaffSerializer(profiles, many=True).data)

    def post(self, request, version):
        serializer = StaffCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        profile = save_serializer(serializer)
        return Response(
            StaffSerializer(profile).data,
            status=status.HTTP_201_CREATED,
        )


class StaffDetailView(APIView):
    permission_classes = [IsSchoolAdmin]

    def get_queryset(self, request):
        return StaffProfile.objects.filter(school=request.user.school).select_related(
            "user", "department"
        )

    def get_object(self, request, staff_id):
        return get_object_or_404(self.get_queryset(request), pk=staff_id)

    def get(self, request, version, staff_id):
        return Response(StaffSerializer(self.get_object(request, staff_id)).data)

    def patch(self, request, version, staff_id):
        profile = self.get_object(request, staff_id)
        serializer = StaffUpdateSerializer(
            profile,
            data=request.data,
            partial=True,
            context={"request": request},
        )
        serializer.is_valid(raise_exception=True)
        profile = save_serializer(serializer)
        return Response(StaffSerializer(profile).data)
