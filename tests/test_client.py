import asyncio
from websockets.client import connect

async def test_client():
    uri = "ws://localhost:8765"
    
    # Read audio file in chunks
    audio_file = "data/audio-sample.m4a"
    chunk_size = 4096  # 4KB chunks
    
    async with connect(uri) as websocket:
        print("Connected to server!")

        # Send audio file in chunks
        try:
            with open(audio_file, 'rb') as f:
                chunk_num = 0
                while True:
                    chunk = f.read(chunk_size)
                    if not chunk:
                        break
                    
                    await websocket.send(chunk)
                    chunk_num += 1
                    print(f"Sent chunk {chunk_num} ({len(chunk)} bytes)")

                    # Receive response from server
                    response = await websocket.recv()
                    print(f"Received response for chunk {chunk_num}: {len(response)} bytes")
            
            print(f"Finished sending {chunk_num} audio chunks.")
        except FileNotFoundError:
            print(f" Error: {audio_file} not found")
        except Exception as e:
            print(f" Error: {e}")

asyncio.run(test_client())
