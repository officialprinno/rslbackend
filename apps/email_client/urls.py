from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.email_client.views import EmailAccountViewSet, EmailLabelViewSet, EmailMessageViewSet

router = DefaultRouter()
router.register("account", EmailAccountViewSet, basename="email-account")
router.register("messages", EmailMessageViewSet, basename="email-message")
router.register("labels", EmailLabelViewSet, basename="email-label")

urlpatterns = [
    path("", include(router.urls)),
]
