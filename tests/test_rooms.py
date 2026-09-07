import unittest

from chat_app import rooms


class RoomTests(unittest.TestCase):
    def setUp(self):
        rooms.rooms.clear()

    def tearDown(self):
        rooms.rooms.clear()

    def test_add_client_creates_room(self):
        client = object()

        rooms.add_client("general", client)

        self.assertTrue(rooms.room_exists("general"))
        self.assertEqual(rooms.get_clients("general"), {client})

    def test_remove_last_client_deletes_room(self):
        client = object()
        rooms.add_client("general", client)

        rooms.remove_client("general", client)

        self.assertFalse(rooms.room_exists("general"))

    def test_get_clients_returns_copy(self):
        client = object()
        rooms.add_client("general", client)

        returned_clients = rooms.get_clients("general")
        returned_clients.clear()

        self.assertEqual(rooms.get_clients("general"), {client})

    def test_get_rooms_returns_sorted_names(self):
        rooms.add_client("support", object())
        rooms.add_client("general", object())

        self.assertEqual(rooms.get_rooms(), ["general", "support"])


if __name__ == "__main__":
    unittest.main()
