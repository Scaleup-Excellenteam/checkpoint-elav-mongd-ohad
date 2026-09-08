import os
from datetime import datetime, timezone

from pymongo import ASCENDING, DESCENDING, AsyncMongoClient


DEFAULT_MONGODB_URI = "mongodb://localhost:27017"
DEFAULT_DATABASE_NAME = "pizza_chat"
MESSAGES_COLLECTION = "messages"


class MessageRepository:
    """Store and retrieve chat messages in MongoDB."""

    def __init__(self, uri=None, database_name=None, client=None, collection=None):
        self.uri = uri or os.getenv("MONGODB_URI", DEFAULT_MONGODB_URI)
        self.database_name = database_name or os.getenv(
            "MONGODB_DATABASE", DEFAULT_DATABASE_NAME
        )
        self.client = client

        if collection is not None:
            self.collection = collection
        else:
            self.client = self.client or AsyncMongoClient(
                self.uri,
                serverSelectionTimeoutMS=3000,
            )
            database = self.client[self.database_name]
            self.collection = database[MESSAGES_COLLECTION]

    async def connect(self):
        """Verify the connection and create indexes used by DLP queries."""
        if self.client is not None:
            await self.client.admin.command("ping")

        await self.collection.create_index(
            [("room", ASCENDING), ("sent_at", DESCENDING)],
            name="room_recent_messages",
        )
        await self.collection.create_index(
            [
                ("room", ASCENDING),
                ("sender", ASCENDING),
                ("sent_at", DESCENDING),
            ],
            name="room_sender_recent_messages",
        )

    async def save_message(self, room, sender, content):
        """Save one accepted chat message and return its ID and timestamp."""
        sent_at = datetime.now(timezone.utc)
        document = {
            "room": room,
            "sender": sender,
            "content": content,
            "sent_at": sent_at,
        }
        result = await self.collection.insert_one(document)
        return str(result.inserted_id), sent_at

    async def get_recent_messages(self, *, sender=None, room=None, since=None, limit=20):
        """Return recent messages in chronological order for future DLP checks."""
        if limit < 1:
            raise ValueError("limit must be at least 1")

        query = {}
        if sender is not None:
            query["sender"] = sender
        if room is not None:
            query["room"] = room
        if since is not None:
            query["sent_at"] = {"$gte": since}

        cursor = (
            self.collection.find(query, {"_id": 0})
            .sort("sent_at", DESCENDING)
            .limit(limit)
        )
        messages = await cursor.to_list(length=limit)
        messages.reverse()
        return messages

    async def close(self):
        if self.client is not None:
            await self.client.close()
