import asyncio
from websockets.asyncio.client import connect


async def receive_messages(websocket):
    async for message in websocket:
        print("\n" + message)


async def main():
    server_ip = input("Enter server IP (leave empty for localhost): ")

    if server_ip == "":
        server_ip = "localhost"

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
