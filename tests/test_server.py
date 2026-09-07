import asyncio
import io
import json
import logging
import unittest
from datetime import datetime, timezone
from functools import partial
from unittest.mock import patch

from websockets.asyncio.client import connect
from websockets.asyncio.server import serve
from websockets.exceptions import ConnectionClosed

from chat_app import rooms
from chat_app import server as server_module
from chat_app.moderation import ModerationResult


class FakeMessageRepository:
    def __init__(self):
        self.messages = []

    async def save_message(self, room, sender, content):
        self.messages.append({"room": room, "sender": sender, "content": content})
        return "message-1", datetime.now(timezone.utc)


class FakeModerationService:
    def __init__(self, allowed=True, disconnect_on_violation=None):
        self.allowed = allowed
        self.disconnect_on_violation = disconnect_on_violation
        self.max_violations = 3
        self.checked_messages = []

    async def check_message(self, **message):
        self.checked_messages.append(message)
        violation_count = len(self.checked_messages) if not self.allowed else 0
        return ModerationResult(
            allowed=self.allowed,
            checked_by_llm=True,
            rule_score=7,
            categories=("ingredients", "quantity"),
            confidence=0.95,
            reason_code="LLM_SAFE" if self.allowed else "RECIPE_RISK",
            violation_count=violation_count,
            should_disconnect=(
                self.disconnect_on_violation == violation_count
            ),
        )


class ServerIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        rooms.rooms.clear()
        self.log_output = io.StringIO()
        self.test_logger = logging.getLogger(f"server_test_{id(self)}")
        self.test_logger.setLevel(logging.INFO)
        self.test_logger.propagate = False
        self.test_logger.handlers.clear()
        self.test_logger.addHandler(logging.StreamHandler(self.log_output))
        self.logger_patch = patch.object(server_module, "logger", self.test_logger)
        self.logger_patch.start()

    async def asyncTearDown(self):
        self.logger_patch.stop()
        for handler in self.test_logger.handlers[:]:
            handler.close()
            self.test_logger.removeHandler(handler)
        rooms.rooms.clear()

    async def test_two_clients_can_join_and_exchange_message(self):
        repository = FakeMessageRepository()
        moderation_service = FakeModerationService(allowed=True)
        handler = partial(
            server_module.handle_client,
            message_repository=repository,
            moderation_service=moderation_service,
        )

        async with serve(handler, "127.0.0.1", 0) as chat_server:
            port = chat_server.sockets[0].getsockname()[1]
            uri = f"ws://127.0.0.1:{port}"

            async with connect(uri) as alice:
                await alice.send("alice")
                rooms_event = json.loads(await alice.recv())
                self.assertEqual(rooms_event, {"type": "rooms", "rooms": []})

                await alice.send(json.dumps({"action": "create_room", "room": "general"}))
                joined_event = json.loads(await alice.recv())
                self.assertEqual(joined_event, {"type": "joined", "room": "general"})

                async with connect(uri) as bob:
                    await bob.send("bob")
                    rooms_event = json.loads(await bob.recv())
                    self.assertEqual(rooms_event["rooms"], ["general"])

                    await bob.send(json.dumps({"action": "join_room", "room": "general"}))
                    joined_event = json.loads(await bob.recv())
                    self.assertEqual(joined_event, {"type": "joined", "room": "general"})

                    secret_message = "SECRET_RECIPE_TEST_MESSAGE"
                    await alice.send(secret_message)
                    self.assertEqual(await bob.recv(), f"alice: {secret_message}")
                    await asyncio.sleep(0)

        self.assertEqual(
            repository.messages,
            [
                {
                    "room": "general",
                    "sender": "alice",
                    "content": "SECRET_RECIPE_TEST_MESSAGE",
                }
            ],
        )
        self.assertEqual(len(moderation_service.checked_messages), 1)

        log_text = self.log_output.getvalue()
        self.assertIn("MESSAGE_STORED", log_text)
        self.assertIn("MESSAGE_RECEIVED", log_text)
        self.assertIn('"recipient_count": 1', log_text)
        self.assertNotIn("SECRET_RECIPE_TEST_MESSAGE", log_text)

    async def test_dlp_blocks_message_before_database_write(self):
        repository = FakeMessageRepository()
        moderation_service = FakeModerationService(allowed=False)
        handler = partial(
            server_module.handle_client,
            message_repository=repository,
            moderation_service=moderation_service,
        )

        async with serve(handler, "127.0.0.1", 0) as chat_server:
            port = chat_server.sockets[0].getsockname()[1]

            async with connect(f"ws://127.0.0.1:{port}") as client:
                await client.send("alice")
                await client.recv()
                await client.send(
                    json.dumps({"action": "create_room", "room": "general"})
                )
                await client.recv()
                await client.send("Add 500 grams of flour and yeast")

                error = json.loads(await client.recv())

        self.assertEqual(error["code"], "DLP_BLOCKED")
        self.assertEqual(error["warningNumber"], 1)
        self.assertEqual(repository.messages, [])
        self.assertNotIn("Add 500 grams of flour and yeast", self.log_output.getvalue())

    async def test_third_dlp_violation_disconnects_client(self):
        repository = FakeMessageRepository()
        moderation_service = FakeModerationService(
            allowed=False,
            disconnect_on_violation=3,
        )
        handler = partial(
            server_module.handle_client,
            message_repository=repository,
            moderation_service=moderation_service,
        )

        async with serve(handler, "127.0.0.1", 0) as chat_server:
            port = chat_server.sockets[0].getsockname()[1]

            async with connect(f"ws://127.0.0.1:{port}") as client:
                await client.send("alice")
                await client.recv()
                await client.send(
                    json.dumps({"action": "create_room", "room": "general"})
                )
                await client.recv()

                for expected_warning in (1, 2):
                    await client.send("add flour")
                    warning = json.loads(await client.recv())
                    self.assertEqual(warning["code"], "DLP_BLOCKED")
                    self.assertEqual(warning["warningNumber"], expected_warning)

                await client.send("add flour")
                disconnected = json.loads(await client.recv())
                self.assertEqual(
                    disconnected["code"],
                    "DLP_TOO_MANY_VIOLATIONS",
                )

                with self.assertRaises(ConnectionClosed) as closed:
                    await client.recv()
                self.assertIsNotNone(closed.exception.rcvd)
                self.assertEqual(closed.exception.rcvd.code, 1008)

        self.assertEqual(repository.messages, [])
        self.assertIn("DLP_CLIENT_DISCONNECTED", self.log_output.getvalue())


if __name__ == "__main__":
    unittest.main()
