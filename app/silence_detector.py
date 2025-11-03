"""Silence detection for PCM16 audio streams"""
import struct
from typing import Tuple

def detect_silence_pcm16(audio_bytes: bytes, sample_rate: int = 16000, 
                        silence_threshold: int = 1000, min_silence_duration: float = 1.5) -> Tuple[bool, int]:
    """
    Detect silence in PCM16 audio stream
    
    Args:
        audio_bytes: PCM16 audio bytes (16-bit signed integers, little-endian)
        sample_rate: Sample rate in Hz (default 16000)
        silence_threshold: Amplitude threshold for silence (default 1000)
        min_silence_duration: Minimum duration of silence in seconds (default 1.5)
    
    Returns:
        Tuple[bool, int]: (is_silent, silence_samples_count)
        - is_silent: True if silence detected for min_silence_duration
        - silence_samples_count: Number of consecutive silent samples found
    """
    if len(audio_bytes) < 2:
        return False, 0
    
    # Convert bytes to 16-bit signed integers
    samples = []
    for i in range(0, len(audio_bytes) - 1, 2):
        try:
            sample = struct.unpack('<h', audio_bytes[i:i+2])[0]
            samples.append(abs(sample))
        except:
            continue
    
    if not samples:
        return False, 0
    
    # Count silent samples (amplitude below threshold)
    silent_samples = sum(1 for amp in samples if amp < silence_threshold)
    total_samples = len(samples)
    silence_ratio = silent_samples / total_samples if total_samples > 0 else 0
    
    # Check if this chunk is mostly silent
    is_silent_chunk = silence_ratio > 0.8  # 80% of samples are silent
    
    # Calculate silence duration in samples
    samples_per_second = sample_rate
    min_silence_samples = int(min_silence_duration * samples_per_second)
    
    # If chunk is silent and we have enough samples, consider it a pause
    if is_silent_chunk and total_samples >= min_silence_samples:
        return True, total_samples
    
    return False, silent_samples

