import asyncio
import json
from websockets.asyncio.server import serve
from rooms import add_client, get_clients, get_rooms, remove_client, room_exists


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
            print(f"Received message in room {room}: {message}")
            
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
    async with serve(handle_client, "0.0.0.0", 8765):
        print("Server running")
        await asyncio.Future()


asyncio.run(main())
