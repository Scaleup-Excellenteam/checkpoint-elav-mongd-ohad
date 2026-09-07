rooms = {}


def add_client(room_name, websocket):
    """
    Add a client to a room.

    If the room does not exist, create it first.
    """
    if room_name not in rooms:
        rooms[room_name] = set()

    rooms[room_name].add(websocket)


def remove_client(room_name, websocket):
    """
    Remove a client from a room.

    If the room becomes empty, remove the room completely.
    """

    if room_name not in rooms:
        return

    rooms[room_name].discard(websocket)

    if not rooms[room_name]:
        del rooms[room_name]


def get_clients(room_name):
    """
    Return all clients in a specific room.
    """

    return rooms.get(room_name, set()).copy()


def room_exists(room_name):
    """
    Return True if the room exists, otherwise False.
    """

    return room_name in rooms


def get_rooms():
    """
    Return all existing room names.
    """

    return sorted(rooms)
