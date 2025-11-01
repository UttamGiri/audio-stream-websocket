import asyncio
import os
from websockets.server import serve
from websockets.exceptions import ConnectionClosedOK
from app.audio_processor import process_audio
from app.utils import log_message
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

WEBSOCKET_HOST = os.getenv("WEBSOCKET_HOST", "0.0.0.0")
WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", 8765))

async def connect_handler(websocket, path):
    """Handles each WebSocket connection"""
    print("✅ New WebSocket session started")

    try:
        async for message in websocket:
            log_message(f"Received audio chunk of size: {len(message)} bytes")

            # Process audio (placeholder for future integration with Transcribe/LLM/Polly)
            processed_chunk = process_audio(message)

            # Send processed chunk back (currently empty for testing)
            await websocket.send(processed_chunk)

    except ConnectionClosedOK:
        print("WebSocket session ended")
    except Exception as e:
        print("Error:", e)

async def main():
    """Start the WebSocket server"""
    server = await serve(connect_handler, WEBSOCKET_HOST, WEBSOCKET_PORT)
    print(f"🟢 WebSocket server listening on {WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
