import asyncio
import struct
import os
import sys
from websockets.client import connect
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add parent directory to path to import app modules
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

def generate_speech_pcm16(text="whats your name?", sample_rate=16000):
    """
    Generate PCM16 speech audio using Amazon Polly
    Returns PCM16 bytes ready for AWS Transcribe
    """
    try:
        from app.polly_synthesizer import PollySynthesizer
        synthesizer = PollySynthesizer()
        print(f"Generating speech: '{text}'")
        pcm_bytes = synthesizer.synthesize_speech(text)
        if pcm_bytes:
            print(f"Generated {len(pcm_bytes)} bytes of speech audio")
            return pcm_bytes
        else:
            print("Warning: Polly returned no audio, falling back to tone")
            return None
    except Exception as e:
        print(f"Error generating speech with Polly: {e}")
        print("Falling back to tone generation")
        return None

def save_pcm16_to_wav(pcm_bytes, filename, sample_rate=16000, channels=1):
    """
    Save PCM16 bytes to a WAV file so you can play and hear it
    """
    import wave
    
    with wave.open(filename, 'wb') as wav_file:
        wav_file.setnchannels(channels)  # Mono
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    print(f"Saved audio to {filename} - you can play it to hear the tone!")

def generate_pcm16_tone(duration_seconds=2, sample_rate=16000, frequency=440):
    """
    Generate PCM16 audio (16-bit, mono, 16kHz) - a simple tone for testing
    No external dependencies needed!
    """
    import math
    num_samples = int(sample_rate * duration_seconds)
    audio_bytes = bytearray()
    
    for i in range(num_samples):
        # Generate sine wave: sin(2π * frequency * time)
        time = i / sample_rate
        sample_float = math.sin(2 * math.pi * frequency * time)
        # Convert to 16-bit signed integer (scale to avoid clipping)
        sample_value = int(32767 * 0.3 * sample_float)
        # Pack as 16-bit signed integer (little-endian)
        audio_bytes.extend(struct.pack('<h', sample_value))
    
    return bytes(audio_bytes)

async def test_client():
    uri = "ws://localhost:8765"
    
    # Option 1: Generate speech using Amazon Polly
    speech_text = "Hello, My name is Hari, i am a software developer, who are you"
    pcm_bytes = generate_speech_pcm16(speech_text, sample_rate=16000)
    
    # Option 2: Fallback to tone if Polly fails
    if not pcm_bytes:
        print("Generating PCM16 test tone (440Hz tone, 2 seconds)...")
        pcm_bytes = generate_pcm16_tone(duration_seconds=2, sample_rate=16000, frequency=440)
        save_pcm16_to_wav(pcm_bytes, "test_tone.wav", sample_rate=16000)
    else:
        # Save speech audio to WAV so you can hear it
        save_pcm16_to_wav(pcm_bytes, "test_speech.wav", sample_rate=16000)
        print(f"Generated {len(pcm_bytes)} bytes of PCM16 speech audio (16-bit, mono, 16kHz)")
    
    # Option 2: Use M4A file (requires ffmpeg + pydub)
    # Uncomment below when ffmpeg is installed:
    # from pydub import AudioSegment
    # audio_file = "data/audio-sample.m4a"
    # audio = AudioSegment.from_file(audio_file, format="m4a")
    # audio = audio.set_channels(1).set_frame_rate(16000)  # Mono, 16 kHz
    # pcm_bytes = audio.raw_data
    
    chunk_size = 4096  # 4KB chunks
    
    async with connect(uri) as websocket:
        print("Connected to server!")

        # Initialize audio response buffer
        audio_response = b''

        # Send chunks and receive responses in streaming mode
        total_chunks = len(pcm_bytes) // chunk_size + (1 if len(pcm_bytes) % chunk_size else 0)
        
        # Create a flag to track when sending is complete
        sending_complete = asyncio.Event()
        
        # Create a task to receive responses while sending
        async def receive_responses():
            response_count = 0
            nonlocal audio_response
            max_wait_after_send = 15.0  # Wait up to 15 seconds after sending completes
            consecutive_timeouts = 0
            max_consecutive_timeouts = 3  # Stop after 3 consecutive timeouts
            
            while True:
                try:
                    # Use shorter timeout while sending, longer after sending completes
                    if sending_complete.is_set():
                        timeout = 5.0  # Longer timeout after sending is done
                    else:
                        timeout = 1.0  # Short timeout while still sending
                    
                    response = await asyncio.wait_for(websocket.recv(), timeout=timeout)
                    
                    # Reset timeout counter on successful receive
                    consecutive_timeouts = 0
                    
                    # Ensure response is bytes
                    if isinstance(response, str):
                        response = response.encode()
                    
                    response_count += 1
                    print(f"Received response #{response_count}: {len(response)} bytes")
                    
                    # Save audio response from server
                    if response and len(response) > 0:
                        audio_response += bytes(response)
                        
                except asyncio.TimeoutError:
                    consecutive_timeouts += 1
                    
                    # If sending is complete, wait longer before giving up
                    if sending_complete.is_set():
                        if consecutive_timeouts >= max_consecutive_timeouts:
                            print(f"No more responses after {max_consecutive_timeouts} timeouts")
                            break
                        print(f"Waiting for more responses... (timeout {consecutive_timeouts}/{max_consecutive_timeouts})")
                    else:
                        # Still sending, just continue waiting
                        continue
                except Exception as e:
                    print(f"Error receiving response: {e}")
                    break
            
            print(f"Total responses received: {response_count}, Total audio: {len(audio_response)} bytes")
            return response_count
        
        # Start receiving responses in background
        receive_task = asyncio.create_task(receive_responses())
        
        # Send all audio chunks
        for i in range(total_chunks):
            start = i * chunk_size
            end = start + chunk_size
            chunk = pcm_bytes[start:end]
            await websocket.send(chunk)
            print(f"Sent chunk {i+1}/{total_chunks} ({len(chunk)} bytes)")
        
        print(f"Finished sending {total_chunks} audio chunks. Waiting for server responses...")
        
        # Signal that sending is complete
        sending_complete.set()
        
        # Wait for all responses
        await receive_task
        
        # Save and play the complete audio response
        if audio_response and len(audio_response) > 0:
            output_file = "server_response.wav"
            save_pcm16_to_wav(audio_response, output_file, sample_rate=16000)
            print(f"\n✅ Audio response saved to {output_file}")
            print("Playing audio response...")
            
            # Play audio (macOS)
            import platform
            import subprocess
            if platform.system() == "Darwin":
                subprocess.run(["afplay", output_file])
            else:
                print(f"Please play {output_file} manually")

if __name__ == "__main__":
    asyncio.run(test_client())
