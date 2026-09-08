# WebSocket Chat Rooms

A small real-time chat application built with Python, `asyncio`, and WebSockets.
Clients can create a room or join an active room and exchange messages with the
other clients in that room.

## Features

- Async WebSocket server and client.
- Automatic discovery of chat servers on the local network.
- Localhost connection option for running everything on one computer.
- Multiple clients can connect concurrently.
- Create new rooms.
- List and join active rooms.
- Messages are delivered only to other clients in the same room.
- Empty rooms are removed automatically.
- Room names are case-insensitive and surrounding whitespace is ignored.
- Structured server logs are written to the terminal and rotating log files.
- Messages are persisted in MongoDB before they are sent to a room.
- Local DLP checks detect and block attempts to share pizza recipes.
- Per-client Anti-Bot rate limiting rejects message floods.

## Project structure

```text
.
|-- chat_app/
|   |-- __init__.py
|   |-- anti_bot.py        # Per-client message rate limiting
|   |-- client.py          # CLI client and menus
|   |-- database.py        # Async MongoDB message repository
|   |-- server.py          # WebSocket server and message routing
|   |-- discovery.py       # Local-network server discovery
|   |-- dlp_rules.py       # DLP vocabulary, weights, and patterns
|   |-- logging_config.py  # Console and rotating file logging
|   |-- moderation.py      # Rule-based filter and local Ollama DLP
|   `-- rooms.py           # In-memory room management
|-- tests/
|   |-- test_database.py
|   |-- test_logging.py
|   |-- test_moderation.py
|   |-- test_rooms.py
|   `-- test_server.py
|-- logs/                  # Created at runtime and ignored by Git
|-- compose.yaml           # Local MongoDB service
|-- .env.example           # Database configuration example
|-- requirements.txt
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
- The packages listed in `requirements.txt`
- MongoDB 8 (a Docker Compose configuration is included)
- Ollama with the `qwen3:4b` model

Install the dependency:

```powershell
python -m pip install -r requirements.txt
```

Start MongoDB locally with Docker:

```powershell
docker compose up -d mongodb
```

Make sure Ollama is running and download the local model once:

```powershell
ollama pull qwen3:4b
```

The default configuration connects to `mongodb://localhost:27017` and uses the
`pizza_chat` database. Override `MONGODB_URI` or `MONGODB_DATABASE` in the
environment when needed. The server won't accept connections if MongoDB is
unavailable, because messages must be stored before they are delivered.
The server also verifies that Ollama and the configured model are available
before accepting clients.

## DLP protection

For every new message, the server loads up to 20 messages from the same sender
and room from the last 15 minutes. A lightweight personal rule score looks for
combinations of ingredients, cooking actions, quantities, temperature, and
timing. Sensitive words such as `recipe`, `formula`, and `confidential` carry
more weight than an ingredient, while a general word such as `secret` is only a
weak signal. Other room members cannot increase this score or the sender's warning
count. Ordinary messages skip the model. When the model is needed, it receives
recent room context with sender names so it can understand conversation without
attributing another member's content as the newest sender's own message. The
local `qwen3:4b` model returns a strict JSON response, and the DLP vocabulary is
in English.

The message is stored and delivered only when the DLP decision allows it. Other
room members receive a fixed `[Message blocked by security policy]` notice when
a message is blocked, without receiving its content or length. If
Ollama fails during a required check, the message is blocked rather than sent
without inspection. Logs contain scores, categories, and decisions, but never
message content. Settings can be overridden with:

```text
OLLAMA_HOST=http://localhost:11434
OLLAMA_MODEL=qwen3:4b
OLLAMA_KEEP_ALIVE=30m
DLP_RULE_THRESHOLD=2
DLP_BLOCK_CONFIDENCE=0.65
DLP_HARD_BLOCK_SCORE=6
DLP_MAX_VIOLATIONS=3
ANTIBOT_MAX_MESSAGES=5
ANTIBOT_WINDOW_SECONDS=10
```

After a blocked attempt, the sender is watched for 15 minutes. During that
period every new message is checked by Ollama, even when its rule score is low.
The first two blocked attempts return warnings. A third blocked attempt within
the active watch period disconnects the client with WebSocket policy code 1008.
If 15 minutes pass without another blocked attempt, the warning count resets.
Blocked messages are retained only in a short-lived in-memory context so that
splitting a recipe after a block doesn't reset the DLP history. Basic fuzzy
matching also catches close misspellings such as `suger` instead of `sugar`.
It also covers common recipe-related misspellings such as `recpie` and
`peperoni`. Preparation terms include actions such as `preheat`, `ferment`,
`proof`, `divide`, and `shape`.
Clear rule violations with a score of 6 or higher are blocked even if the LLM
misclassifies them. Three different ingredients sent as short list fragments
are also blocked, so `flour`, `yeast`, and `water` cannot bypass the policy by
being split across messages. While a sender is watched, short recipe fragments
remain blocked, but complete casual sentences such as `I ate pizza with olives`
are classified by meaning instead of being blocked for the ingredient alone.

## Anti-Bot protection

Each client may send up to 5 chat messages in a rolling 10-second window. An
additional message is rejected with a retry time. A rejected message is not
checked by the DLP model, stored in MongoDB, or delivered to the room. The
limit applies only to chat messages after joining a room; connection setup and
room selection don't count. Rate-limit state is held in memory and removed
when the client disconnects. The two Anti-Bot settings above can be overridden
with environment variables.

## Run locally

Start the server in one terminal:

```powershell
python -m chat_app.server
```

Enter a short server name, for example `elav`. The server advertises this name
on the local network while it is running.

Start each client in a separate terminal:

```powershell
python -m chat_app.client
```

The client first chooses how to connect:

```text
1. Find servers on this network
2. Connect to localhost
```

The first option searches for a few seconds and displays the active chat
servers. After connecting, each client enters a nickname and chooses one of
the following room options:

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

Run the client on the other computer and choose `Find servers on this network`.
The server listens on `0.0.0.0:8765`, so Windows Firewall must allow inbound
TCP connections to Python on port `8765`. Some public or institutional networks
block the multicast traffic used by Zeroconf discovery; on those networks,
automatic discovery may not work.

Test network access from the client computer:

```powershell
Test-NetConnection SERVER_IP -Port 8765
```

`TcpTestSucceeded` must be `True` before the WebSocket client can connect.

## Logs

Server events are printed to the terminal and written to `logs/server.log`.
Each file is limited to 5 MB, and up to five backup files are retained. The log
contains connection, room, message-metadata, error, and shutdown events. Message
content is deliberately not stored in the log.

## Tests

Run all tests from the project root:

```powershell
python -m unittest discover -s tests -v
```

The tests cover room management, MongoDB repository behavior, DLP rules and
decisions, rotating log configuration, and real local WebSocket exchanges.
They use test doubles and don't require MongoDB or Ollama to be running.
Network discovery isn't tested because it depends on multicast support in the
network running the tests.

## Current message flow

```text
Client connects
  -> discovers and selects a server (or uses localhost)
  -> opens a WebSocket connection
  -> sends nickname
  -> receives active room list
  -> creates or joins a room
  -> sends a chat message
  -> server checks recent context with rules and, when needed, Ollama
  -> suspicious message is blocked
  -> allowed message continues
  -> server stores the message in MongoDB
  -> server gets the room members
  -> server sends the message to the other members
```

## Current limitations

- Rooms and memberships are stored only in memory.
- A room disappears when its last client disconnects.
- A sender doesn't receive its own message back from the server.
- There is no signup, login, authorization, or Anti-Bot protection yet.
- A client must reconnect to switch rooms.
