import asyncio
from websockets.asyncio.client import connect


async def receive_messages(websocket):
    async for message in websocket:
        print("\nOther:", message)


async def main():
    async with connect("ws://192.168.159.26:8765") as websocket:
        print("Connected")
        
        
        username = input("Enter your name: ")
        room = input("Enter Room Name: ")
        await websocket.send(username)
        await websocket.send(room)
        
        asyncio.create_task(receive_messages(websocket))

        while True:
            message = await asyncio.to_thread(input, "You: ")
            await websocket.send(message)


asyncio.run(main())