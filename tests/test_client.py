import asyncio
import json
import threading
import unittest
from unittest.mock import patch

from chat_app.client import choose_room


class FakeWebSocket:
    def __init__(self, incoming_messages):
        self.incoming_messages = list(incoming_messages)
        self.sent_messages = []

    async def recv(self):
        if not self.incoming_messages:
            raise AssertionError("Client waited for an unexpected server message")
        return self.incoming_messages.pop(0)

    async def send(self, message):
        self.sent_messages.append(message)


class ClientRoomMenuTests(unittest.IsolatedAsyncioTestCase):
    async def test_room_input_does_not_block_websocket_event_loop(self):
        websocket = FakeWebSocket(
            [
                json.dumps({"type": "rooms", "rooms": []}),
                json.dumps({"type": "joined", "room": "general"}),
            ]
        )
        input_started = threading.Event()
        release_input = threading.Event()
        answers = iter(["1", "general"])

        def delayed_input(_prompt):
            answer = next(answers)
            if answer == "1":
                input_started.set()
                release_input.wait(timeout=2)
            return answer

        with patch("builtins.input", side_effect=delayed_input):
            room_task = asyncio.create_task(choose_room(websocket))
            started = await asyncio.to_thread(input_started.wait, 1)

            self.assertTrue(started)
            self.assertFalse(room_task.done())

            release_input.set()
            await room_task

    async def test_invalid_option_redisplays_menu_without_waiting_for_server(self):
        websocket = FakeWebSocket(
            [
                json.dumps({"type": "rooms", "rooms": []}),
                json.dumps({"type": "joined", "room": "general"}),
            ]
        )

        with patch("builtins.input", side_effect=["invalid", "1", "general"]):
            await choose_room(websocket)

        self.assertEqual(
            [json.loads(message) for message in websocket.sent_messages],
            [{"action": "create_room", "room": "general"}],
        )


if __name__ == "__main__":
    unittest.main()
