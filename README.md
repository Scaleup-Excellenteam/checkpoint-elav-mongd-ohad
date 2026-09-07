# WebSocket Chat Rooms

A small real-time chat application built with Python, `asyncio`, and WebSockets.
Clients can create a room or join an active room and exchange messages with the
other clients in that room.

## Features

- Async WebSocket server and client.
- Multiple clients can connect concurrently.
- Create new rooms.
- List and join active rooms.
- Messages are delivered only to other clients in the same room.
- Empty rooms are removed automatically.
- Room names are case-insensitive and surrounding whitespace is ignored.

## Project structure

```text
.
|-- client.py   # CLI client and room menu
|-- server.py   # WebSocket server and message routing
|-- rooms.py    # In-memory room management
`-- README.md
```

The `rooms.py` module provides these operations:

- `add_client(room_name, websocket)`
- `remove_client(room_name, websocket)`
- `get_clients(room_name)`
- `room_exists(room_name)`
- `get_rooms()`

## Requirements

- Python 3.11 or newer
- The `websockets` package

Install the dependency:

```powershell
python -m pip install -r requirements.txt
```

## Run locally

Start the server in one terminal:

```powershell
python server.py
```

Start each client in a separate terminal:

```powershell
python client.py
```

Leave the server IP empty when the client runs on the same computer. Each
client enters a nickname and then chooses one of the following options:

```text
1. Create a new room
2. Join an existing room
```

The first client must create a room because no active rooms exist yet. Other
clients can then select that room from the displayed list.

## Connect from another computer

Both computers should be connected to the same local network or hotspot.

On the server computer, find the active Wi-Fi IPv4 address:

```powershell
ipconfig
```

Run `client.py` on the other computer and enter that IPv4 address when prompted.
The server listens on `0.0.0.0:8765`, so Windows Firewall must allow inbound
TCP connections to Python on port `8765`.

Test network access from the client computer:

```powershell
Test-NetConnection SERVER_IP -Port 8765
```

`TcpTestSucceeded` must be `True` before the WebSocket client can connect.

## Current message flow

```text
Client connects
  -> sends nickname
  -> receives active room list
  -> creates or joins a room
  -> sends a chat message
  -> server gets the room members
  -> server sends the message to the other members
```

## Current limitations

- Rooms and memberships are stored only in memory.
- A room disappears when its last client disconnects.
- Messages aren't persisted.
- A sender doesn't receive its own message back from the server.
- There is no signup, login, authorization, DLP, or Anti-Bot protection yet.
- A client must reconnect to switch rooms.
