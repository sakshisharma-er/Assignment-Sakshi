from django.db.models import Q
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from .models import ConsultationSession
from .serializers import AssignSessionSerializer, ConsultationSessionSerializer
from .services import (
    accept_session,
    assign_session,
    bill_session,
    end_session,
    start_session,
)


class ConsultationSessionViewSet(viewsets.ModelViewSet):
    serializer_class = ConsultationSessionSerializer
    http_method_names = ("get", "post", "head", "options")

    def get_queryset(self):
        queryset = ConsultationSession.objects.select_related(
            "user", "provider"
        ).prefetch_related("charges")
        if self.request.user.is_staff:
            return queryset
        return queryset.filter(
            Q(user=self.request.user) | Q(provider=self.request.user)
        ).distinct()

    @action(detail=True, methods=("post",))
    def assign(self, request, pk=None):
        session = self.get_object()
        serializer = AssignSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = assign_session(
            session.pk, request.user, serializer.validated_data["provider"]
        )
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=("post",))
    def accept(self, request, pk=None):
        session = self.get_object()
        session = accept_session(session.pk, request.user)
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=("post",))
    def start(self, request, pk=None):
        session = self.get_object()
        session = start_session(session.pk, request.user)
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=("post",))
    def end(self, request, pk=None):
        session = self.get_object()
        session = end_session(session.pk, request.user)
        return Response(self.get_serializer(session).data)

    @action(detail=True, methods=("post",))
    def bill(self, request, pk=None):
        session = self.get_object()
        session = bill_session(session.pk)
        return Response(self.get_serializer(session).data, status=status.HTTP_200_OK)
