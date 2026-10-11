from django.urls import path

from .views import (
    AcceptSessionView,
    AssignSessionView,
    BillSessionView,
    ConsultationSessionDetailView,
    ConsultationSessionListCreateView,
    EndSessionView,
    StartSessionView,
)

urlpatterns = [
    path("", ConsultationSessionListCreateView.as_view(), name="session-list-create"),
    path("<uuid:pk>/", ConsultationSessionDetailView.as_view(), name="session-detail"),
    path("<uuid:pk>/assign/", AssignSessionView.as_view(), name="session-assign"),
    path("<uuid:pk>/accept/", AcceptSessionView.as_view(), name="session-accept"),
    path("<uuid:pk>/start/", StartSessionView.as_view(), name="session-start"),
    path("<uuid:pk>/end/", EndSessionView.as_view(), name="session-end"),
    path("<uuid:pk>/bill/", BillSessionView.as_view(), name="session-bill"),
]
