import unittest

from chat_app.anti_bot import AntiBotService


class AntiBotServiceTests(unittest.TestCase):
    def test_sixth_message_in_ten_seconds_is_rejected(self):
        service = AntiBotService(max_messages=5, window_seconds=10)

        decisions = [
            service.check_message("alice", now=second)
            for second in (0, 1, 2, 3, 4, 5)
        ]

        self.assertTrue(all(decision.allowed for decision in decisions[:5]))
        self.assertFalse(decisions[5].allowed)
        self.assertEqual(decisions[5].retry_after_seconds, 5)

    def test_client_can_send_again_after_window_expires(self):
        service = AntiBotService(max_messages=2, window_seconds=10)
        service.check_message("alice", now=0)
        service.check_message("alice", now=1)

        blocked = service.check_message("alice", now=2)
        allowed = service.check_message("alice", now=10)

        self.assertFalse(blocked.allowed)
        self.assertTrue(allowed.allowed)

    def test_clients_have_independent_limits(self):
        service = AntiBotService(max_messages=1, window_seconds=10)

        self.assertTrue(service.check_message("alice", now=0).allowed)
        self.assertFalse(service.check_message("alice", now=1).allowed)
        self.assertTrue(service.check_message("bob", now=1).allowed)

    def test_removing_client_clears_rate_limit_state(self):
        service = AntiBotService(max_messages=1, window_seconds=10)
        service.check_message("alice", now=0)
        service.remove_client("alice")

        self.assertTrue(service.check_message("alice", now=1).allowed)


if __name__ == "__main__":
    unittest.main()
