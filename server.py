import asyncio
import json
import socket
from websockets.asyncio.server import serve
from zeroconf import Zeroconf, ServiceInfo
from rooms import add_client, get_clients, get_rooms, remove_client, room_exists

SERVICE_TYPE = "_chatid._tcp.local."
PORT = 8765


def get_lan_ip():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]


def register_mdns_name(service_id):
    local_ip = get_lan_ip()
    info = ServiceInfo(
        SERVICE_TYPE,
        f"{service_id}.{SERVICE_TYPE}",
        addresses=[socket.inet_aton(local_ip)],
        port=PORT,
        server=f"{service_id}.local.",
    )
    zeroconf = Zeroconf()
    zeroconf.register_service(info)
    print(f"Registered as '{service_id}' on the local network ({local_ip})")
    return zeroconf


async def choose_room(websocket):
    while True:
        await websocket.send(json.dumps({"type": "rooms", "rooms": get_rooms()}))
        request = json.loads(await websocket.recv())

        action = request.get("action")
        room = str(request.get("room", "")).strip().casefold()

        if not room:
            await websocket.send(json.dumps({"type": "error", "message": "Room name is required"}))
        elif action == "create_room" and room_exists(room):
            await websocket.send(json.dumps({"type": "error", "message": "Room already exists"}))
        elif action == "join_room" and not room_exists(room):
            await websocket.send(json.dumps({"type": "error", "message": "Room does not exist"}))
        elif action not in {"create_room", "join_room"}:
            await websocket.send(json.dumps({"type": "error", "message": "Invalid room action"}))
        else:
            add_client(room, websocket)
            await websocket.send(json.dumps({"type": "joined", "room": room}))
            return room


async def handle_client(websocket):
    username = (await websocket.recv()).strip()
    room = await choose_room(websocket)
    print(f"Client joined room: {room}")

    try:
        async for message in websocket:
            print(f"{username} in room {room}: {message}")

            full_message = f"{username}: {message}"

            for client in get_clients(room):
                if client != websocket:
                    await client.send(full_message)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        remove_client(room, websocket)
        print(f"Client left room: {room}")


async def main():
    service_id = input("Choose an ID for friends to connect to (e.g. elav): ").strip()
    zeroconf = await asyncio.to_thread(register_mdns_name, service_id)

    try:
        async with serve(handle_client, "0.0.0.0", PORT):
            print("Server running")
            await asyncio.Future()
    finally:
        zeroconf.close()


asyncio.run(main())
