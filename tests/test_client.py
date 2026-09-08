import asyncio
import json
import threading
import unittest
from unittest.mock import patch

from chat_app.client import choose_room, format_server_event


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


class ClientEventFormattingTests(unittest.TestCase):
    def test_rate_limit_shows_retry_time(self):
        output = format_server_event(
            {
                "type": "error",
                "code": "RATE_LIMITED",
                "message": "You are sending messages too quickly",
                "retryAfterSeconds": 6,
            }
        )

        self.assertEqual(
            output,
            "RATE LIMIT\n"
            "You are sending messages too quickly. Try again in 6 seconds.",
        )

    def test_first_warning_explains_what_was_blocked(self):
        output = format_server_event(
            {
                "type": "error",
                "code": "DLP_BLOCKED",
                "message": "Message blocked",
                "blockedContent": "add flour",
                "warningNumber": 1,
                "maxWarnings": 2,
                "warningsRemaining": 1,
            }
        )

        self.assertEqual(
            output,
            "SECURITY WARNING 1/2\n"
            'Your message was blocked: "add flour"\n'
            "1 warning remains before disconnection.",
        )

    def test_final_warning_explains_next_violation_disconnects(self):
        output = format_server_event(
            {
                "type": "error",
                "code": "DLP_BLOCKED",
                "message": "Message blocked",
                "blockedContent": "add yeast",
                "warningNumber": 2,
                "maxWarnings": 2,
                "warningsRemaining": 0,
            }
        )

        self.assertIn("SECURITY WARNING 2/2", output)
        self.assertIn("The next blocked message will disconnect you.", output)

    def test_policy_disconnect_is_distinct_from_a_warning(self):
        output = format_server_event(
            {
                "type": "error",
                "code": "DLP_TOO_MANY_VIOLATIONS",
                "message": "Too many security policy violations. You have been disconnected.",
                "blockedContent": "add cheese",
            }
        )

        self.assertIn("SECURITY DISCONNECT", output)
        self.assertIn('Your message was blocked: "add cheese"', output)


if __name__ == "__main__":
    unittest.main()
