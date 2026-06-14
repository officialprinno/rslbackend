"""WebSocket consumer for real-time messaging."""

import json
from urllib.parse import parse_qs

from asgiref.sync import async_to_sync
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncWebsocketConsumer
from channels.layers import get_channel_layer
from django.contrib.auth import get_user_model
from rest_framework_simplejwt.tokens import AccessToken

from apps.messaging.services import MessagingService

User = get_user_model()


@database_sync_to_async
def get_user_from_token(token):
    try:
        access = AccessToken(token)
        return User.objects.get(pk=access["user_id"])
    except Exception:
        return None


@database_sync_to_async
def set_user_online(user, online):
    MessagingService.set_online(user, online)


def broadcast_message_event(conversation_id, message_data):
    layer = get_channel_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        f"conversation_{conversation_id}",
        {"type": "message.new", "message": message_data},
    )


def broadcast_user_event(user_id, event_type, payload):
    layer = get_channel_layer()
    if not layer:
        return
    async_to_sync(layer.group_send)(
        f"user_{user_id}",
        {"type": event_type.replace(".", "_"), **payload},
    )


class MessagingConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        query = parse_qs(self.scope.get("query_string", b"").decode())
        token = (query.get("token") or [None])[0]
        self.user = await get_user_from_token(token)
        if not self.user:
            await self.close()
            return
        self.user_group = f"user_{self.user.id}"
        await self.channel_layer.group_add(self.user_group, self.channel_name)
        await self.accept()
        await set_user_online(self.user, True)
        await self.channel_layer.group_send(
            self.user_group,
            {"type": "user_online", "user_id": self.user.id},
        )

    async def disconnect(self, close_code):
        if hasattr(self, "user_group"):
            await self.channel_layer.group_discard(self.user_group, self.channel_name)
        if hasattr(self, "user") and self.user:
            await set_user_online(self.user, False)

    async def receive(self, text_data=None, bytes_data=None):
        if not text_data:
            return
        try:
            data = json.loads(text_data)
        except json.JSONDecodeError:
            return
        event_type = data.get("type")
        payload = data.get("payload", {})
        if event_type == "typing.start":
            await self.channel_layer.group_send(
                self.user_group,
                {
                    "type": "typing_start",
                    "user_id": self.user.id,
                    "conversation_id": payload.get("conversation_id"),
                },
            )
        elif event_type == "typing.stop":
            await self.channel_layer.group_send(
                self.user_group,
                {
                    "type": "typing_stop",
                    "user_id": self.user.id,
                    "conversation_id": payload.get("conversation_id"),
                },
            )
        elif event_type == "ping":
            await self.send(text_data=json.dumps({"type": "pong"}))

    async def message_new(self, event):
        await self.send(text_data=json.dumps({"type": "message.new", "payload": event["message"]}))

    async def typing_start(self, event):
        await self.send(text_data=json.dumps({"type": "typing.start", "payload": event}))

    async def typing_stop(self, event):
        await self.send(text_data=json.dumps({"type": "typing.stop", "payload": event}))

    async def user_online(self, event):
        await self.send(text_data=json.dumps({"type": "user.online", "payload": event}))

    async def notification_new(self, event):
        await self.send(text_data=json.dumps({"type": "notification.new", "payload": event}))
