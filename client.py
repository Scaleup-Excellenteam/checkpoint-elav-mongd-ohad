import asyncio
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
        room = input("Enter Room Name: ").strip().casefold()

        await websocket.send(username)
        await websocket.send(room)

        receiver_task = asyncio.create_task(receive_messages(websocket))

        while True:
            message = await asyncio.to_thread(input, "You: ")
            await websocket.send(message)


asyncio.run(main())
