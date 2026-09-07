import asyncio
import socket
from websockets.asyncio.client import connect


async def receive_messages(websocket):
    async for message in websocket:
        print("\n" + message)


async def main():
    hostname = input("Enter server hostname (leave empty for localhost): ").strip()

    if hostname == "":
        hostname = "localhost"

    try:
        server_ip = socket.gethostbyname(hostname)
    except socket.gaierror:
        print(f"Could not resolve hostname: {hostname}")
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
