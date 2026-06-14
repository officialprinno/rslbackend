from django.urls import include, path
from rest_framework.routers import DefaultRouter

from apps.messaging.views import BroadcastViewSet, ConversationViewSet, NotificationViewSet

router = DefaultRouter()
router.register("conversations", ConversationViewSet, basename="conversation")
router.register("broadcasts", BroadcastViewSet, basename="broadcast")
router.register("notifications", NotificationViewSet, basename="notification")

urlpatterns = [
    path("", include(router.urls)),
]
