import asyncio
import json
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed
from .discovery import discover_servers


def format_server_event(event):
    """Format a structured server event for the CLI."""
    code = event.get("code", "")
    message = event.get("message", "Unknown server event")

    if code == "DLP_BLOCKED":
        warning_number = event.get("warningNumber", "?")
        max_warnings = event.get("maxWarnings", "?")
        remaining = event.get("warningsRemaining")
        preview = _message_preview(event.get("blockedContent", ""))
        next_step = (
            "The next blocked message will disconnect you."
            if remaining == 0
            else f"{remaining} warning remains before disconnection."
        )
        return (
            f"SECURITY WARNING {warning_number}/{max_warnings}\n"
            f"Your message was blocked: \"{preview}\"\n"
            f"{next_step}"
        )

    if code == "DLP_TOO_MANY_VIOLATIONS":
        preview = _message_preview(event.get("blockedContent", ""))
        return (
            "SECURITY DISCONNECT\n"
            f"Your message was blocked: \"{preview}\"\n"
            f"{message}"
        )

    if code == "RATE_LIMITED":
        retry_after = event.get("retryAfterSeconds", "?")
        return (
            "RATE LIMIT\n"
            f"{message}. Try again in {retry_after} seconds."
        )

    label = "Security" if code.startswith("DLP_") else "Error"
    return f"{label}: {message}"


def _message_preview(content, limit=80):
    preview = " ".join(str(content).split())
    if len(preview) <= limit:
        return preview
    return preview[: limit - 3] + "..."


async def receive_messages(websocket):
    policy_disconnect_received = False
    try:
        async for message in websocket:
            try:
                event = json.loads(message)
            except json.JSONDecodeError:
                print("\n" + message)
                continue

            if event.get("type") == "error":
                print("\n" + format_server_event(event))
                if event.get("code") == "DLP_TOO_MANY_VIOLATIONS":
                    policy_disconnect_received = True
            else:
                print("\n" + message)
    except ConnectionClosed as error:
        if not policy_disconnect_received:
            print(f"\nDisconnected by server ({error.code}): {error.reason}")


async def choose_room(websocket):
    rooms_message = json.loads(await websocket.recv())
    available_rooms = rooms_message["rooms"]

    while True:
        print("\n1. Create a new room")
        if available_rooms:
            print("2. Join an existing room")
            for index, room_name in enumerate(available_rooms, start=1):
                print(f"   {index}. {room_name}")

        choice = (await asyncio.to_thread(input, "Choose an option: ")).strip()

        if choice == "1":
            room = (
                await asyncio.to_thread(input, "Enter new room name: ")
            ).strip().casefold()
            action = "create_room"
        elif choice == "2" and available_rooms:
            try:
                room_index = int(
                    await asyncio.to_thread(input, "Enter room number: ")
                ) - 1
                if not 0 <= room_index < len(available_rooms):
                    raise IndexError
                room = available_rooms[room_index]
            except (ValueError, IndexError):
                print("Invalid room number")
                continue
            action = "join_room"
        else:
            print("Invalid option")
            continue

        await websocket.send(json.dumps({"action": action, "room": room}))
        response = json.loads(await websocket.recv())

        if response["type"] == "joined":
            print(f"Joined room: {response['room']}")
            return

        print(f"Error: {response['message']}")
        rooms_message = json.loads(await websocket.recv())
        available_rooms = rooms_message["rooms"]


async def choose_server():
    while True:
        print("\n1. Find servers on this network")
        print("2. Connect to localhost")
        choice = (await asyncio.to_thread(input, "Choose an option: ")).strip()

        if choice == "1":
            print("Searching for chat servers...")
            servers = await asyncio.to_thread(discover_servers)

            if not servers:
                print("No chat servers found. Try again or use localhost.")
                continue

            for index, server in enumerate(servers, start=1):
                print(f"{index}. {server['name']} ({server['ip']}:{server['port']})")

            try:
                server_index = int(
                    await asyncio.to_thread(input, "Choose a server: ")
                ) - 1
                if not 0 <= server_index < len(servers):
                    raise IndexError
            except (ValueError, IndexError):
                print("Invalid server number")
                continue

            server = servers[server_index]
            return server["ip"], server["port"]

        if choice == "2":
            return "localhost", 8765

        print("Invalid option")


async def main():
    server_ip, server_port = await choose_server()

    async with connect(f"ws://{server_ip}:{server_port}") as websocket:
        print("Connected")

        username = (
            await asyncio.to_thread(input, "Enter your nickname: ")
        ).strip()
        await websocket.send(username)
        await choose_room(websocket)

        receiver_task = asyncio.create_task(receive_messages(websocket))

        while not receiver_task.done():
            message = await asyncio.to_thread(input, "You: ")
            if receiver_task.done():
                break
            await websocket.send(message)

        await receiver_task


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, EOFError):
        print("\nDisconnected")
    except ConnectionClosed as error:
        print(f"\nConnection closed ({error.code}): {error.reason}")
