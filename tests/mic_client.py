#!/usr/bin/env python3
"""
Real-time microphone client - records from your Mac's microphone
and streams audio to the WebSocket server for transcription + LLM + TTS
"""
import asyncio
import sounddevice as sd
import numpy as np
import struct
from websockets.client import connect
import queue
import sys
import os
from dotenv import load_dotenv

load_dotenv()

# Audio configuration for AWS Transcribe
SAMPLE_RATE = 16000
CHANNELS = 1
CHUNK_SIZE = 4096  # 4KB chunks
DTYPE = np.int16
SAMPLE_WIDTH = 2  # 16-bit = 2 bytes

class AudioRecorder:
    """Records audio from microphone using sounddevice"""
    def __init__(self):
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.stream = None
        
    def start_recording(self):
        """Start recording from microphone"""
        self.is_recording = True
        
        # Get default input device
        default_input = sd.default.device[0]
        device_info = sd.query_devices(default_input)
        
        device_name = str(device_info) if hasattr(device_info, 'name') else f"Device {default_input}"
        print(f"Using microphone: {device_name}")
        print(f"Sample rate: {SAMPLE_RATE} Hz, Channels: {CHANNELS}, Format: 16-bit PCM")
        print("\n🎤 Recording... Speak naturally. Press Ctrl+C to stop.\n")
        
        def record_callback(indata, frames, time, status):
            """Callback for audio recording"""
            if self.is_recording:
                # Convert numpy array to bytes (PCM16)
                audio_bytes = indata.tobytes()
                self.audio_queue.put(audio_bytes)
        
        self.stream = sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=CHUNK_SIZE // SAMPLE_WIDTH,  # Number of samples
            callback=record_callback
        )
        
        self.stream.start()
        
    def stop_recording(self):
        """Stop recording"""
        self.is_recording = False
        if self.stream:
            self.stream.stop()
            self.stream.close()
        
    def get_audio_chunk(self):
        """Get next audio chunk from queue"""
        try:
            return self.audio_queue.get(timeout=0.1)
        except queue.Empty:
            return None

class AudioPlayer:
    """Plays audio responses from server using sounddevice"""
    def __init__(self):
        self.response_audio = b''
        self.is_playing = False  # Flag to prevent multiple simultaneous playback
        
    def add_audio(self, audio_bytes):
        """Add audio bytes to buffer"""
        self.response_audio += audio_bytes
        
    def play(self):
        """Play accumulated audio (only if not already playing)"""
        if len(self.response_audio) == 0:
            return
        
        if self.is_playing:
            print("⚠️  Already playing audio, skipping duplicate playback")
            return
            
        print(f"\n🔊 Playing response ({len(self.response_audio)} bytes)...")
        self.is_playing = True
        
        try:
            # Convert bytes to numpy array
            audio_array = np.frombuffer(self.response_audio, dtype=DTYPE)
            audio_array = audio_array.reshape(-1, CHANNELS)
            
            # Play audio
            sd.play(audio_array, samplerate=SAMPLE_RATE)
            sd.wait()  # Wait until playback is finished
            
            print("✅ Finished playing response\n")
            
        except Exception as e:
            print(f"Error playing audio: {e}")
        finally:
            # Always clear buffer and flag
            self.response_audio = b''
            self.is_playing = False
            
    def cleanup(self):
        """Cleanup audio resources"""
        sd.stop()

async def mic_client():
    """Real-time microphone client"""
    uri = "ws://localhost:8765"
    
    recorder = AudioRecorder()
    player = AudioPlayer()
    shutdown_requested = False  # Flag to prevent playback on shutdown
    
    try:
        recorder.start_recording()
        
        # Configure longer ping interval for audio streaming
        async with connect(
            uri,
            ping_interval=20,  # Send ping every 20 seconds
            ping_timeout=10    # Wait 10 seconds for pong
        ) as websocket:
            print("✅ Connected to server!")
            print("\n" + "="*60)
            print("Ready to record! Speak naturally into your microphone.")
            print("Server will detect pauses and respond automatically.")
            print("="*60 + "\n")
            
            # Initialize response buffer
            audio_response = b''
            
            # Task to receive responses
            async def receive_responses():
                nonlocal audio_response
                sending_complete = asyncio.Event()
                
                async def receive_loop():
                    nonlocal audio_response
                    consecutive_timeouts = 0
                    max_consecutive_timeouts = 5  # Increased to wait longer
                    last_audio_time = None
                    chunk_received = False  # Track if we've received any chunks in this response
                    
                    while not shutdown_requested:
                        try:
                            # Use longer timeout to wait for complete responses
                            timeout = 3.0 if not sending_complete.is_set() else 8.0  # Increased from 1.0/5.0
                            response = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                            
                            consecutive_timeouts = 0
                            last_audio_time = asyncio.get_event_loop().time()
                            chunk_received = True
                            
                            if isinstance(response, str):
                                response = response.encode()
                            
                            audio_response += bytes(response)
                            print(f"📥 Received {len(response)} bytes of audio response (total: {len(audio_response)} bytes)")
                            
                            # Don't play immediately - wait for complete response
                            # Only play if we've received a very large amount (>128KB) which suggests it's complete
                            if len(audio_response) > 131072:  # 128KB threshold (was 32KB)
                                print(f"📦 Large response accumulated ({len(audio_response)} bytes), waiting for completion...")
                            
                        except asyncio.TimeoutError:
                            consecutive_timeouts += 1
                            
                            # If we have audio and no new audio for 2.5 seconds, play it
                            # Increased from 1.0s to 2.5s to wait for all chunks
                            if audio_response and last_audio_time and not player.is_playing:
                                time_since_last = asyncio.get_event_loop().time() - last_audio_time
                                if time_since_last > 2.5:  # Wait 2.5 seconds after last chunk
                                    print(f"🎵 No new audio for {time_since_last:.1f}s, playing complete response ({len(audio_response)} bytes)...")
                                    if not shutdown_requested:
                                        player.add_audio(audio_response)
                                        player.play()
                                        audio_response = b''
                                        last_audio_time = None
                                        chunk_received = False
                            
                            # Also check if we stopped sending and have audio (but only if not already playing)
                            if sending_complete.is_set() and audio_response and not player.is_playing:
                                if not chunk_received or consecutive_timeouts >= 2:  # Wait 2 timeouts after sending stops
                                    print(f"🎵 Sending complete, playing final response ({len(audio_response)} bytes)...")
                                    if not shutdown_requested:
                                        player.add_audio(audio_response)
                                        player.play()
                                        audio_response = b''
                                    break
                            
                            if sending_complete.is_set() and consecutive_timeouts >= max_consecutive_timeouts:
                                break
                            continue
                        except Exception as e:
                            error_type = type(e).__name__
                            if "ConnectionClosed" in error_type or shutdown_requested:
                                if not shutdown_requested:
                                    print(f"\n⚠️  Connection closed during receive")
                                break
                            else:
                                print(f"Error receiving: {e}")
                                break
                    
                    # Play any remaining accumulated response if not shutting down and not already playing
                    # Wait a bit more in case there are final chunks arriving
                    if audio_response and not shutdown_requested and not player.is_playing:
                        # Give a final chance for any remaining chunks
                        try:
                            await asyncio.sleep(0.5)  # Brief wait for any final chunks
                            # Try to receive one more chunk quickly
                            try:
                                final_chunk = await asyncio.wait_for(websocket.recv(), timeout=0.5)
                                if isinstance(final_chunk, str):
                                    final_chunk = final_chunk.encode()
                                audio_response += bytes(final_chunk)
                                print(f"📥 Received final chunk: {len(final_chunk)} bytes")
                            except (asyncio.TimeoutError, Exception):
                                pass  # No more chunks, proceed to play
                        except Exception:
                            pass
                        
                        print(f"🎵 Playing final accumulated audio ({len(audio_response)} bytes)...")
                        player.add_audio(audio_response)
                        player.play()
                        audio_response = b''
                    elif audio_response:
                        print(f"⚠️  Discarding {len(audio_response)} bytes of audio (shutdown or already playing)")
                        audio_response = b''
                
                receive_task = asyncio.create_task(receive_loop())
                
                # Send audio chunks continuously
                chunk_count = 0
                while recorder.is_recording and not shutdown_requested:
                    try:
                        audio_chunk = recorder.get_audio_chunk()
                        if audio_chunk:
                            await websocket.send(audio_chunk)
                            chunk_count += 1
                            if chunk_count % 10 == 0:  # Print every 10 chunks
                                print(f"📤 Sent {chunk_count} chunks...", end='\r')
                        
                        await asyncio.sleep(0.01)  # Small delay to prevent busy loop
                    except Exception as send_error:
                        if shutdown_requested:
                            break
                        error_type = type(send_error).__name__
                        if "ConnectionClosed" in error_type:
                            print(f"\n⚠️  Connection closed, stopping send loop")
                            break
                        else:
                            print(f"\n⚠️  Error sending audio: {send_error}")
                            raise
                
                sending_complete.set()
                # Wait for receive task, but don't wait too long on shutdown
                try:
                    await asyncio.wait_for(receive_task, timeout=2.0 if shutdown_requested else None)
                except asyncio.TimeoutError:
                    if shutdown_requested:
                        receive_task.cancel()
                        print("\n⏹️  Cancelled receive task (shutdown)")
                
            await receive_responses()
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping recording...")
        shutdown_requested = True
    except Exception as e:
        print(f"\n❌ Error: {e}")
        shutdown_requested = True
        import traceback
        traceback.print_exc()
    finally:
        shutdown_requested = True
        recorder.stop_recording()
        player.cleanup()
        print("✅ Disconnected")

if __name__ == "__main__":
    try:
        asyncio.run(mic_client())
    except KeyboardInterrupt:
        print("\n👋 Goodbye!")

