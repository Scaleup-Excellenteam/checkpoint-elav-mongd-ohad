import asyncio
from websockets.asyncio.server import serve

rooms = {}



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
    async with serve(handle_client, "0.0.0.0", 8765):
        print("Server running")
        await asyncio.Future()


asyncio.run(main())
