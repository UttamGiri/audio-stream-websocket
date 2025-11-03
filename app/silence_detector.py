"""Silence detection for PCM16 audio streams"""
import struct
from typing import Tuple

def detect_silence_pcm16(audio_bytes: bytes, sample_rate: int = 16000, 
                        silence_threshold: int = 2000, min_silence_duration: float = 0.1) -> Tuple[bool, int]:
    """
    Detect silence in PCM16 audio stream
    
    Args:
        audio_bytes: PCM16 audio bytes (16-bit signed integers, little-endian)
        sample_rate: Sample rate in Hz (default 16000)
        silence_threshold: Amplitude threshold for silence (default 2000)
                           Higher values filter more background noise
        min_silence_duration: Minimum duration of silence in seconds (default 0.1)
                              Used for per-chunk detection, actual pause detection
                              happens at server level
    
    Returns:
        Tuple[bool, int]: (is_silent, silence_samples_count)
        - is_silent: True if chunk is mostly silent
        - silence_samples_count: Number of silent samples found
    """
    if len(audio_bytes) < 2:
        return True, 0  # Empty or too small = consider silent
    
    # Convert bytes to 16-bit signed integers
    samples = []
    for i in range(0, len(audio_bytes) - 1, 2):
        try:
            sample = struct.unpack('<h', audio_bytes[i:i+2])[0]
            samples.append(abs(sample))
        except:
            continue
    
    if not samples:
        return True, 0
    
    # Calculate RMS (Root Mean Square) amplitude for better noise filtering
    if samples:
        rms = (sum(s * s for s in samples) / len(samples)) ** 0.5
    else:
        rms = 0
    
    # Use RMS for more robust silence detection
    is_silent_chunk = rms < silence_threshold
    
    # Count silent samples
    silent_samples = sum(1 for amp in samples if amp < silence_threshold)
    
    return is_silent_chunk, silent_samples

