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
    path("<int:pk>/", ConsultationSessionDetailView.as_view(), name="session-detail"),
    path("<int:pk>/assign/", AssignSessionView.as_view(), name="session-assign"),
    path("<int:pk>/accept/", AcceptSessionView.as_view(), name="session-accept"),
    path("<int:pk>/start/", StartSessionView.as_view(), name="session-start"),
    path("<int:pk>/end/", EndSessionView.as_view(), name="session-end"),
    path("<int:pk>/bill/", BillSessionView.as_view(), name="session-bill"),
]
