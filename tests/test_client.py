import asyncio
from websockets.client import connect

async def test_client():
    uri = "ws://localhost:8765"
    async with connect(uri) as websocket:
        print("✅ Connected to server!")

        # Send 5 dummy audio chunks
        for i in range(5):
            await websocket.send(b'\x00' * 320)
            print(f"Sent chunk {i+1}")

            # Receive response from server
            response = await websocket.recv()
            print(f"Received chunk {i+1} of size {len(response)}")

        print("Finished sending audio chunks.")

asyncio.run(test_client())
