import asyncio
import os
import time
from websockets.server import serve
from websockets.exceptions import ConnectionClosedOK
from app.audio_processor import process_audio_async, reset_session
from app.utils import log_message
from app.silence_detector import detect_silence_pcm16
from dotenv import load_dotenv

# Load environment variables from .env
load_dotenv()

# Enable debugpy for remote debugging if DEBUG env var is set
if os.getenv("DEBUG", "").lower() in ("true", "1", "yes"):
    import debugpy
    debug_port = int(os.getenv("DEBUG_PORT", "5678"))
    debugpy.listen(("0.0.0.0", debug_port))
    print(f"Debugger listening on port {debug_port}...")
    # Only wait for debugger if WAIT_FOR_DEBUGGER is set
    if os.getenv("WAIT_FOR_DEBUGGER", "").lower() in ("true", "1", "yes"):
        debugpy.wait_for_client()
        print("Debugger attached! Starting server...")
    else:
        print("Debugger ready (not waiting). Server starting...")

WEBSOCKET_HOST = os.getenv("WEBSOCKET_HOST", "0.0.0.0")
WEBSOCKET_PORT = int(os.getenv("WEBSOCKET_PORT", 8765))

async def connect_handler(websocket, path):
    """Handles each WebSocket connection with pause detection"""
    print("New WebSocket session started")
    
    # Reset session for new connection
    reset_session()
    
    # Audio buffer to accumulate chunks
    audio_buffer = b''
    last_chunk_time = None
    pause_detection_threshold = 1.5  # seconds
    sample_rate = 16000
    process_task = None

    async def process_on_pause():
        """Process accumulated audio after pause"""
        nonlocal audio_buffer
        await asyncio.sleep(pause_detection_threshold)
        
        # Check if enough time has passed and we have audio
        if len(audio_buffer) > 0:
            print(f"Time-based pause detected (1.5s), processing accumulated audio...")
            accumulated_audio = audio_buffer
            audio_buffer = b''  # Clear buffer immediately
            
            # Process audio through Transcribe -> LLM -> Polly pipeline
            processed_chunk = await process_audio_async(accumulated_audio)
            
            # Send processed chunk back
            if processed_chunk and len(processed_chunk) > 0:
                await websocket.send(processed_chunk)
                print(f"Sent complete response: {len(processed_chunk)} bytes")

    try:
        async for message in websocket:
            log_message(f"Received audio chunk of size: {len(message)} bytes")
            
            # Cancel any pending pause processing
            if process_task and not process_task.done():
                process_task.cancel()
                try:
                    await process_task
                except asyncio.CancelledError:
                    pass
            
            # Add chunk to buffer
            audio_buffer += message
            last_chunk_time = time.time()
            
            # Check for silence/pause in the current chunk
            is_silent, silence_samples = detect_silence_pcm16(
                message, 
                sample_rate=sample_rate,
                silence_threshold=1000,  # Amplitude threshold
                min_silence_duration=pause_detection_threshold
            )
            
            # Process immediately if silence detected in chunk
            if is_silent and len(audio_buffer) > 0:
                print(f"Silence detected in chunk ({silence_samples} samples), processing accumulated audio...")
                
                accumulated_audio = audio_buffer
                audio_buffer = b''
                
                # Process audio through Transcribe -> LLM -> Polly pipeline
                processed_chunk = await process_audio_async(accumulated_audio)
                
                # Send processed chunk back
                if processed_chunk and len(processed_chunk) > 0:
                    await websocket.send(processed_chunk)
                    print(f"Sent complete response: {len(processed_chunk)} bytes")
            else:
                # Start timeout task to process after pause
                process_task = asyncio.create_task(process_on_pause())
        
        # Process any remaining audio when connection closes
        if len(audio_buffer) > 0:
            print(f"Processing final {len(audio_buffer)} bytes of audio...")
            processed_chunk = await process_audio_async(audio_buffer)
            if processed_chunk and len(processed_chunk) > 0:
                await websocket.send(processed_chunk)

    except ConnectionClosedOK:
        print("WebSocket session ended")
    except Exception as e:
        print("Error:", e)
        import traceback
        traceback.print_exc()

async def main():
    """Start the WebSocket server"""
    server = await serve(connect_handler, WEBSOCKET_HOST, WEBSOCKET_PORT)
    print(f"WebSocket server listening on {WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
