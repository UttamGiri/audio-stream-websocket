#!/usr/bin/env python3
"""
Utility to play audio output from the audio processing pipeline
Usage: python play_audio.py <audio_file.wav> or read from stdin
"""
import sys
import wave
import struct

def save_pcm_to_wav(pcm_bytes, output_file="output.wav", sample_rate=16000, channels=1):
    """Save PCM16 bytes to WAV file"""
    with wave.open(output_file, 'wb') as wav_file:
        wav_file.setnchannels(channels)
        wav_file.setsampwidth(2)  # 16-bit = 2 bytes
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm_bytes)
    print(f"Saved audio to {output_file}")
    return output_file

def play_wav(file_path):
    """Play WAV file using system audio player"""
    import platform
    import subprocess
    
    system = platform.system()
    if system == "Darwin":  # macOS
        subprocess.run(["afplay", file_path])
    elif system == "Linux":
        subprocess.run(["aplay", file_path], check=False) or subprocess.run(["paplay", file_path], check=False)
    elif system == "Windows":
        subprocess.run(["start", file_path], shell=True)
    else:
        print(f"Unknown system: {system}. Please play {file_path} manually.")

if __name__ == "__main__":
    if len(sys.argv) > 1:
        # Play existing file
        wav_file = sys.argv[1]
        print(f"Playing {wav_file}...")
        play_wav(wav_file)
    else:
        # Read PCM bytes from stdin and save/play
        print("Reading PCM16 audio from stdin...")
        pcm_bytes = sys.stdin.buffer.read()
        
        if len(pcm_bytes) > 0:
            output_file = "output.wav"
            save_pcm_to_wav(pcm_bytes, output_file)
            print(f"Playing {output_file}...")
            play_wav(output_file)
        else:
            print("No audio data received. Pipe PCM bytes to this script.")

