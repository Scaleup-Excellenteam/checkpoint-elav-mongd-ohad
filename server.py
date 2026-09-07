import asyncio
import socket
from websockets.asyncio.server import serve
from zeroconf import Zeroconf, ServiceInfo

rooms = {}
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



async def handle_client(websocket):
    username = (await websocket.recv()).strip()
    room = (await websocket.recv()).strip().casefold()

    if room not in rooms:
        rooms[room] = set()
    rooms[room].add(websocket)
    print(f"Client joined room: {room}")

    try:
        async for message in websocket:
            print(f"Received message in room {room}: {message}")
            
            full_message = f"{username}: {message}"

            for client in list(rooms[room]):
                if client != websocket:
                    await client.send(full_message)
    except Exception as e:
        print(f"Error: {e}")
    finally:
        rooms[room].discard(websocket)
        if not rooms[room]:
            del rooms[room]
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
