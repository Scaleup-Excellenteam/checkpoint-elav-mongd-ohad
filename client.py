import asyncio
import json
from websockets.asyncio.client import connect
from discovery import discover_servers


async def receive_messages(websocket):
    async for message in websocket:
        print("\n" + message)


async def choose_room(websocket):
    while True:
        rooms_message = json.loads(await websocket.recv())
        available_rooms = rooms_message["rooms"]

        print("\n1. Create a new room")
        if available_rooms:
            print("2. Join an existing room")
            for index, room_name in enumerate(available_rooms, start=1):
                print(f"   {index}. {room_name}")

        choice = input("Choose an option: ").strip()

        if choice == "1":
            room = input("Enter new room name: ").strip().casefold()
            action = "create_room"
        elif choice == "2" and available_rooms:
            try:
                room_index = int(input("Enter room number: ")) - 1
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


async def choose_server():
    while True:
        print("\n1. Find servers on this network")
        print("2. Connect to localhost")
        choice = input("Choose an option: ").strip()

        if choice == "1":
            print("Searching for chat servers...")
            servers = await asyncio.to_thread(discover_servers)

            if not servers:
                print("No chat servers found. Try again or use localhost.")
                continue

            for index, server in enumerate(servers, start=1):
                print(f"{index}. {server['name']} ({server['ip']}:{server['port']})")

            try:
                server_index = int(input("Choose a server: ")) - 1
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

        username = input("Enter your nickname: ").strip()
        await websocket.send(username)
        await choose_room(websocket)

        receiver_task = asyncio.create_task(receive_messages(websocket))

        while True:
            message = await asyncio.to_thread(input, "You: ")
            await websocket.send(message)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDisconnected")
