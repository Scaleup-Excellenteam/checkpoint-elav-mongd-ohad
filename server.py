import asyncio
from websockets.asyncio.server import serve

clients = set()


async def handle_client(websocket):
    clients.add(websocket)

    try:
        async for message in websocket:
            for client in clients:
                if client != websocket:
                    await client.send(message)
    finally:
        clients.remove(websocket)


async def main():
    async with serve(handle_client, "0.0.0.0", 8765):
        print("Server running")
        await asyncio.Future()


asyncio.run(main())