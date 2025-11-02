import os
from typing import Optional, Dict
from app.transcriber import Transcriber
from app.llm_processor import LLMProcessor
from app.polly_synthesizer import PollySynthesizer

# Global instances - initialized once
_transcriber: Optional[Transcriber] = None
_llm_processor: Optional[LLMProcessor] = None
_polly_synthesizer: Optional[PollySynthesizer] = None
_transcription_session: Optional[Dict] = None

def _initialize_services():
    """Initialize all services once"""
    global _transcriber, _llm_processor, _polly_synthesizer
    
    if _transcriber is None:
        _transcriber = Transcriber()
        print("Transcriber initialized")
    
    if _llm_processor is None:
        _llm_processor = LLMProcessor()
        print("LLM Processor initialized")
    
    if _polly_synthesizer is None:
        _polly_synthesizer = PollySynthesizer()
        print("Polly Synthesizer initialized")

def _start_session_if_needed():
    """Start transcription session if not already started"""
    global _transcription_session, _transcriber
    
    if _transcription_session is None and _transcriber:
        _transcription_session = _transcriber.start_transcription()
        print("Transcription session started")

def process_audio(chunk: bytes) -> bytes:
    """
    Complete audio processing pipeline:
    1. Transcribe audio to text (AWS Transcribe)
    2. Process text with LLM
    3. Convert LLM response to audio (Amazon Polly)
    """
    # Initialize services
    _initialize_services()
    _start_session_if_needed()
    
    try:
        # Step 1: Transcribe audio to text
        if not _transcriber:
            return b''
        transcribed_text = _transcriber.send_audio_chunk(chunk)
        
        # If no transcription yet, return empty
        if not transcribed_text:
            return b''
        
        print(f"Transcribed: {transcribed_text}")
        
        # Step 2: Process with LLM
        if not _llm_processor:
            return b''
        llm_response = _llm_processor.process_text(transcribed_text)
        
        if not llm_response:
            return b''
        
        print(f"LLM Response: {llm_response}")
        
        # Step 3: Convert LLM response to audio
        if not _polly_synthesizer:
            return b''
        audio_output = _polly_synthesizer.synthesize_speech(llm_response)
        
        if audio_output:
            print(f"Generated audio: {len(audio_output)} bytes")
        else:
            print("Failed to generate audio from LLM response")
        
        return audio_output if audio_output else b''
    
    except Exception as e:
        print(f"Error in audio processing pipeline: {e}")
        return b''

def reset_session():
    """Reset the transcription session for a new conversation"""
    global _transcription_session
    _transcription_session = None
    if _transcriber:
        _transcriber.transcription_buffer = []
    print("Session reset")
