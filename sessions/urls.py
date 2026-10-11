from rest_framework.routers import DefaultRouter

from .views import ConsultationSessionViewSet

router = DefaultRouter()
router.register("", ConsultationSessionViewSet, basename="consultation-session")

urlpatterns = router.urls
