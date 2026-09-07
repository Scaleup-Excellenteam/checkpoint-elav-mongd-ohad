import asyncio
import json
import socket
from websockets.asyncio.client import connect
from zeroconf import Zeroconf

SERVICE_TYPE = "_chatid._tcp.local."


async def receive_messages(websocket):
    async for message in websocket:
        print("\n" + message)


def resolve_id(service_id, timeout=3.0):
    zeroconf = Zeroconf()
    try:
        info = zeroconf.get_service_info(SERVICE_TYPE, f"{service_id}.{SERVICE_TYPE}", timeout=timeout * 1000)
        if info is None or not info.addresses:
            return None
        return socket.inet_ntoa(info.addresses[0])
    finally:
        zeroconf.close()


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


async def main():
    service_id = input("Enter server ID (leave empty for localhost): ").strip()

    if service_id == "":
        server_ip = "localhost"
    else:
        server_ip = await asyncio.to_thread(resolve_id, service_id)
        if server_ip is None:
            print(f"Could not find server with ID: {service_id}")
            return

    async with connect(f"ws://{server_ip}:8765") as websocket:
        print("Connected")

        username = input("Enter your nickname: ").strip()
        await websocket.send(username)
        await choose_room(websocket)

        receiver_task = asyncio.create_task(receive_messages(websocket))

        while True:
            message = await asyncio.to_thread(input, "You: ")
            await websocket.send(message)


asyncio.run(main())
