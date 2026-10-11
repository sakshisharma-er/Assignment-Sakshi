from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import ConsultationSession
from .serializers import AssignSessionSerializer, ConsultationSessionSerializer
from .services import (
    accept_session,
    assign_session,
    bill_session,
    end_session,
    start_session,
)


def visible_sessions(user):
    queryset = ConsultationSession.objects.select_related(
        "user", "provider"
    ).prefetch_related("charges")
    if user.is_staff:
        return queryset
    return queryset.filter(Q(user=user) | Q(provider=user)).distinct()


class SessionAccessMixin:
    def get_session(self, request, pk):
        return get_object_or_404(visible_sessions(request.user), pk=pk)


class ConsultationSessionListCreateView(APIView):
    def get(self, request):
        serializer = ConsultationSessionSerializer(
            visible_sessions(request.user), many=True
        )
        return Response(serializer.data)

    def post(self, request):
        serializer = ConsultationSessionSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class ConsultationSessionDetailView(SessionAccessMixin, APIView):
    def get(self, request, pk):
        session = self.get_session(request, pk)
        return Response(ConsultationSessionSerializer(session).data)


class AssignSessionView(SessionAccessMixin, APIView):
    def post(self, request, pk):
        session = self.get_session(request, pk)
        serializer = AssignSessionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        session = assign_session(
            session.pk, request.user, serializer.validated_data["provider"]
        )
        return Response(ConsultationSessionSerializer(session).data)


class AcceptSessionView(SessionAccessMixin, APIView):
    def post(self, request, pk):
        session = self.get_session(request, pk)
        session = accept_session(session.pk, request.user)
        return Response(ConsultationSessionSerializer(session).data)


class StartSessionView(SessionAccessMixin, APIView):
    def post(self, request, pk):
        session = self.get_session(request, pk)
        session = start_session(session.pk, request.user)
        return Response(ConsultationSessionSerializer(session).data)


class EndSessionView(SessionAccessMixin, APIView):
    def post(self, request, pk):
        session = self.get_session(request, pk)
        session = end_session(session.pk, request.user)
        return Response(ConsultationSessionSerializer(session).data)


class BillSessionView(SessionAccessMixin, APIView):
    def post(self, request, pk):
        session = self.get_session(request, pk)
        session = bill_session(session.pk)
        return Response(ConsultationSessionSerializer(session).data)
