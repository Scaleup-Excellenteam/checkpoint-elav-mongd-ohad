import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock

from chat_app.database import MessageRepository


class FakeCursor:
    def __init__(self, messages):
        self.messages = messages
        self.sort_arguments = None
        self.limit_value = None

    def sort(self, field, direction):
        self.sort_arguments = (field, direction)
        return self

    def limit(self, limit):
        self.limit_value = limit
        return self

    async def to_list(self, length):
        return list(self.messages[:length])


class MessageRepositoryTests(unittest.IsolatedAsyncioTestCase):
    async def test_save_message_inserts_expected_document(self):
        collection = SimpleNamespace(
            insert_one=AsyncMock(return_value=SimpleNamespace(inserted_id="message-1"))
        )
        repository = MessageRepository(collection=collection)

        message_id, sent_at = await repository.save_message(
            room="general",
            sender="alice",
            content="hello",
        )

        self.assertEqual(message_id, "message-1")
        document = collection.insert_one.await_args.args[0]
        self.assertEqual(document["room"], "general")
        self.assertEqual(document["sender"], "alice")
        self.assertEqual(document["content"], "hello")
        self.assertEqual(document["sent_at"], sent_at)
        self.assertEqual(sent_at.tzinfo, timezone.utc)

    async def test_get_recent_messages_returns_chronological_order(self):
        newest = {"sender": "alice", "content": "second"}
        oldest = {"sender": "alice", "content": "first"}
        cursor = FakeCursor([newest, oldest])
        collection = SimpleNamespace(find=lambda query, projection: cursor)
        repository = MessageRepository(collection=collection)
        since = datetime(2026, 1, 1, tzinfo=timezone.utc)

        messages = await repository.get_recent_messages(
            sender="alice",
            room="general",
            since=since,
            limit=10,
        )

        self.assertEqual(messages, [oldest, newest])
        self.assertEqual(cursor.limit_value, 10)

    async def test_recent_messages_rejects_invalid_limit(self):
        repository = MessageRepository(collection=SimpleNamespace())

        with self.assertRaises(ValueError):
            await repository.get_recent_messages(limit=0)


if __name__ == "__main__":
    unittest.main()
