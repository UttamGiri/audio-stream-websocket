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
    
    # Initialize services (stream will be started when needed)
    from app.audio_processor import _initialize_services
    _initialize_services()
    
    # Audio buffer to accumulate chunks
    audio_buffer = b''
    silence_buffer = b''  # Buffer to accumulate silent chunks
    last_sound_time = None
    pause_detection_threshold = 1.5  # seconds of silence before processing
    sample_rate = 16000
    silence_threshold = 2000  # Amplitude threshold (higher = filters more background noise)
    min_audio_duration = 0.5  # Minimum audio duration to process (seconds)
    process_task = None
    is_processing = False  # Flag to prevent multiple simultaneous processing

    async def process_on_pause():
        """Process accumulated audio after continuous silence"""
        nonlocal audio_buffer, silence_buffer, last_sound_time, is_processing
        
        # Wait for pause threshold
        await asyncio.sleep(pause_detection_threshold)
        
        # Double-check: if no new audio arrived and we're not already processing, process
        current_time = time.time()
        if last_sound_time and (current_time - last_sound_time) >= pause_detection_threshold:
            # Check if already processing to avoid duplicate processing
            if is_processing:
                print("Already processing, skipping duplicate pause detection")
                return
            
            # Check minimum audio duration
            audio_duration = len(audio_buffer) / (sample_rate * 2)  # 2 bytes per sample
            
            if len(audio_buffer) > 0 and audio_duration >= min_audio_duration:
                is_processing = True  # Set flag to prevent duplicate processing
                print(f"Pause detected (1.5s silence), processing {len(audio_buffer)} bytes ({audio_duration:.2f}s)...")
                accumulated_audio = audio_buffer
                audio_buffer = b''  # Clear buffer
                silence_buffer = b''
                
                try:
                    # Process audio through Transcribe -> LLM -> Polly pipeline
                    processed_chunk = await process_audio_async(accumulated_audio)
                    
                    # Send processed chunk back (chunk if large)
                    if processed_chunk and len(processed_chunk) > 0:
                        max_chunk_size = 512 * 1024  # 512KB chunks
                        if len(processed_chunk) > max_chunk_size:
                            print(f"Large response ({len(processed_chunk)} bytes), splitting into chunks...")
                            total_chunks = (len(processed_chunk) + max_chunk_size - 1) // max_chunk_size
                            for i in range(0, len(processed_chunk), max_chunk_size):
                                chunk = processed_chunk[i:i + max_chunk_size]
                                await websocket.send(chunk)
                                print(f"Sent chunk {i // max_chunk_size + 1}/{total_chunks}: {len(chunk)} bytes")
                        else:
                            await websocket.send(processed_chunk)
                            print(f"Sent complete response: {len(processed_chunk)} bytes")
                finally:
                    is_processing = False  # Clear flag after processing completes
            elif len(audio_buffer) > 0:
                print(f"Audio too short ({audio_duration:.2f}s < {min_audio_duration}s), ignoring...")
                audio_buffer = b''

    try:
        chunk_count = 0
        async for message in websocket:
            try:
                chunk_count += 1
                # Only log every 20th chunk to reduce noise
                if chunk_count % 20 == 0:
                    log_message(f"Received {chunk_count} audio chunks ({len(message)} bytes each)")
                
                # Check if this chunk contains actual sound
                try:
                    is_silent_chunk, _ = detect_silence_pcm16(
                        message, 
                        sample_rate=sample_rate,
                        silence_threshold=silence_threshold,
                        min_silence_duration=0.1  # Just check if chunk is silent
                    )
                except Exception as detect_error:
                    print(f"Error in silence detection: {detect_error}")
                    # Assume non-silent if detection fails
                    is_silent_chunk = False
                
                if is_silent_chunk:
                    # Silent chunk - accumulate to silence buffer
                    silence_buffer += message
                    silence_duration = len(silence_buffer) / (sample_rate * 2)
                    
                    # If we have audio accumulated and silence is long enough, process it
                    if len(audio_buffer) > 0 and silence_duration >= pause_detection_threshold:
                        audio_duration = len(audio_buffer) / (sample_rate * 2)
                        
                        # Check if already processing to avoid duplicate processing
                        if is_processing:
                            print("Already processing, skipping duplicate silence detection")
                            # Continue accumulating silence, cancel any pending timeout
                            if process_task and not process_task.done():
                                process_task.cancel()
                                try:
                                    await process_task
                                except asyncio.CancelledError:
                                    pass
                            continue
                        
                        if audio_duration >= min_audio_duration:
                            is_processing = True  # Set flag to prevent duplicate processing
                            print(f"Silence detected ({silence_duration:.2f}s), processing {len(audio_buffer)} bytes...")
                            
                            accumulated_audio = audio_buffer
                            audio_buffer = b''
                            silence_buffer = b''
                            
                            # Cancel pending timeout task
                            if process_task and not process_task.done():
                                process_task.cancel()
                                try:
                                    await process_task
                                except asyncio.CancelledError:
                                    pass
                            
                            # Process audio
                            try:
                                processed_chunk = await process_audio_async(accumulated_audio)
                                if processed_chunk and len(processed_chunk) > 0:
                                    # Split large responses into chunks to avoid WebSocket message size limits (typically 1MB)
                                    max_chunk_size = 512 * 1024  # 512KB chunks
                                    if len(processed_chunk) > max_chunk_size:
                                        print(f"Large response ({len(processed_chunk)} bytes), splitting into chunks...")
                                        total_chunks = (len(processed_chunk) + max_chunk_size - 1) // max_chunk_size
                                        for i in range(0, len(processed_chunk), max_chunk_size):
                                            chunk = processed_chunk[i:i + max_chunk_size]
                                            await websocket.send(chunk)
                                            print(f"Sent chunk {i // max_chunk_size + 1}/{total_chunks}: {len(chunk)} bytes")
                                    else:
                                        await websocket.send(processed_chunk)
                                        print(f"Sent complete response: {len(processed_chunk)} bytes")
                            except Exception as process_error:
                                error_type = type(process_error).__name__
                                if "ConnectionClosed" in error_type:
                                    print(f"Connection closed while sending response: {process_error}")
                                    raise  # Re-raise to exit the loop
                                else:
                                    print(f"Error processing audio: {process_error}")
                                    import traceback
                                    traceback.print_exc()
                                    # Continue - don't close connection on processing errors
                            finally:
                                is_processing = False  # Clear flag after processing completes
                        else:
                            print(f"Audio too short ({audio_duration:.2f}s), continuing to accumulate...")
                    else:
                        # Continue accumulating silence, cancel any pending timeout
                        if process_task and not process_task.done():
                            process_task.cancel()
                            try:
                                await process_task
                            except asyncio.CancelledError:
                                pass
                else:
                    # Sound detected - add to audio buffer and reset silence
                    audio_buffer += silence_buffer  # Include any leading silence
                    audio_buffer += message
                    silence_buffer = b''
                    last_sound_time = time.time()
                    
                    # Cancel any pending pause processing
                    if process_task and not process_task.done():
                        process_task.cancel()
                        try:
                            await process_task
                        except asyncio.CancelledError:
                            pass
                    
                    # Start new timeout task for pause detection
                    process_task = asyncio.create_task(process_on_pause())
            except Exception as message_error:
                error_type = type(message_error).__name__
                if "ConnectionClosed" in error_type:
                    raise  # Re-raise connection closed errors to exit loop
                else:
                    print(f"Error processing message: {message_error}")
                    import traceback
                    traceback.print_exc()
                    # Continue processing other messages
                    continue
        
        # Process any remaining audio when connection closes
        if len(audio_buffer) > 0:
            print(f"Processing final {len(audio_buffer)} bytes of audio...")
            try:
                processed_chunk = await process_audio_async(audio_buffer)
                if processed_chunk and len(processed_chunk) > 0:
                    # Split large responses into chunks
                    max_chunk_size = 512 * 1024  # 512KB chunks
                    if len(processed_chunk) > max_chunk_size:
                        print(f"Large final response ({len(processed_chunk)} bytes), splitting into chunks...")
                        total_chunks = (len(processed_chunk) + max_chunk_size - 1) // max_chunk_size
                        for i in range(0, len(processed_chunk), max_chunk_size):
                            chunk = processed_chunk[i:i + max_chunk_size]
                            await websocket.send(chunk)
                            print(f"Sent final chunk {i // max_chunk_size + 1}/{total_chunks}: {len(chunk)} bytes")
                    else:
                        await websocket.send(processed_chunk)
                        print(f"Sent final response: {len(processed_chunk)} bytes")
            except Exception as final_error:
                error_type = type(final_error).__name__
                if "ConnectionClosed" not in error_type:
                    print(f"Error processing final audio: {final_error}")

    except ConnectionClosedOK:
        print("WebSocket session ended normally")
    except Exception as e:
        error_type = type(e).__name__
        if "ConnectionClosed" in error_type or "ConnectionClosedError" in error_type:
            print(f"WebSocket connection closed: {e}")
        else:
            print(f"Error in connection handler: {e}")
            import traceback
            traceback.print_exc()
            # Don't re-raise - let connection close gracefully
    finally:
        # Cleanup: Close transcription stream when WebSocket session ends
        from app.audio_processor import _transcriber
        if _transcriber and _transcriber.is_streaming:
            print("Closing transcription stream for this session...")
            _transcriber.is_streaming = False
            _transcriber.stream = None
            if _transcriber._result_processor_task and not _transcriber._result_processor_task.done():
                _transcriber._result_processor_task.cancel()
                _transcriber._result_processor_task = None

async def main():
    """Start the WebSocket server"""
    # Configure longer ping interval and timeout for audio streaming
    # This prevents timeout during long pauses in speech
    server = await serve(
        connect_handler, 
        WEBSOCKET_HOST, 
        WEBSOCKET_PORT,
        ping_interval=30,  # Send ping every 30 seconds
        ping_timeout=60,   # Wait 60 seconds for pong response
        close_timeout=10,  # Close timeout
        max_size=None,     # Disable message size limit (we'll chunk manually)
        max_queue=32       # Queue size for messages
    )
    print(f"WebSocket server listening on {WEBSOCKET_HOST}:{WEBSOCKET_PORT}")
    await server.wait_closed()

if __name__ == "__main__":
    asyncio.run(main())
