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
        print(f"Transcriber initialized: {_transcriber is not None}")
    
    if _llm_processor is None:
        print("About to create LLMProcessor instance...")
        _llm_processor = LLMProcessor()
        print(f"LLM Processor initialized: {_llm_processor is not None}, client: {_llm_processor.client is not None if _llm_processor else 'N/A'}")
    
    # If LLMProcessor exists but client is None, try to reinitialize (in case env vars weren't loaded before)
    if _llm_processor and _llm_processor.client is None:
        print("WARNING: LLMProcessor.client is None - trying to reinitialize with current environment...")
        _llm_processor = LLMProcessor()  # Reinitialize - maybe env vars are available now
        print(f"LLM Processor reinitialized: client={_llm_processor.client is not None if _llm_processor else 'N/A'}")
    
    if _polly_synthesizer is None:
        _polly_synthesizer = PollySynthesizer()
        print(f"Polly Synthesizer initialized: {_polly_synthesizer is not None}")

def _start_session_if_needed():
    """Start transcription session if not already started"""
    global _transcription_session, _transcriber
    
    if _transcription_session is None and _transcriber:
        _transcription_session = _transcriber.start_transcription()
        print("Transcription session started")

async def process_audio_async(chunk: bytes) -> bytes:
    """
    Complete audio processing pipeline (async version):
    1. Transcribe audio to text (AWS Transcribe)
    2. Process text with LLM
    3. Convert LLM response to audio (Amazon Polly)
    """
    import time
    pipeline_start = time.time()
    
    # Initialize services
    _initialize_services()
    _start_session_if_needed()
    
    try:
        # Step 1: Transcribe audio to text
        if not _transcriber:
            print("Error: Transcriber is None!")
            return b''
        
        transcribe_start = time.time()
        try:
            transcribed_text = await _transcriber.send_audio_chunk_async(chunk)
            transcribe_time = time.time() - transcribe_start
            print(f"⏱️  Transcription took {transcribe_time:.2f}s - Result: {transcribed_text}")
        except Exception as e:
            print(f"Error in transcription (continuing): {e}")
            transcribed_text = None
        
        # If no transcription yet, check if we should skip or use test mode
        if not transcribed_text:
            # Test mode: bypass transcription for testing LLM/Polly
            test_mode = os.getenv("TEST_MODE", "").lower() in ("true", "1", "yes")
            if test_mode:
                print("TEST_MODE: Using placeholder text instead of transcription")
                transcribed_text = "Hello, this is a test message."
            else:
                print("No transcription available, skipping LLM and Polly steps")
                return b''
        
        # Step 2: Process with LLM
        if not _llm_processor:
            print("Error: LLM Processor is None!")
            return b''
        
        llm_start = time.time()
        print(f"🤖 Calling LLM with text: {transcribed_text[:50]}...")
        llm_response = _llm_processor.process_text(transcribed_text)
        llm_time = time.time() - llm_start
        print(f"⏱️  LLM processing took {llm_time:.2f}s - Response: {llm_response[:100] if llm_response else 'None'}...")
        
        if not llm_response:
            return b''
        
        # Step 3: Convert LLM response to audio
        if not _polly_synthesizer:
            return b''
        
        polly_start = time.time()
        audio_output = _polly_synthesizer.synthesize_speech(llm_response)
        polly_time = time.time() - polly_start
        total_time = time.time() - pipeline_start
        
        if audio_output:
            print(f"⏱️  Polly synthesis took {polly_time:.2f}s - Generated {len(audio_output)} bytes")
            print(f"✅ Total pipeline time: {total_time:.2f}s (Transcribe: {transcribe_time:.2f}s, LLM: {llm_time:.2f}s, Polly: {polly_time:.2f}s)")
        else:
            print("Failed to generate audio from LLM response")
        
        return audio_output if audio_output else b''
    
    except Exception as e:
        total_time = time.time() - pipeline_start
        print(f"❌ Error in audio processing pipeline after {total_time:.2f}s: {e}")
        import traceback
        traceback.print_exc()
        return b''

def process_audio(chunk: bytes) -> bytes:
    """
    Sync wrapper for process_audio_async
    This is kept for backward compatibility but should use async version
    """
    import asyncio
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If loop is running, we need to handle this differently
            # For now, return empty - should use async version
            print("Warning: process_audio called from async context. Use process_audio_async instead.")
            return b''
        else:
            return loop.run_until_complete(process_audio_async(chunk))
    except RuntimeError:
        return asyncio.run(process_audio_async(chunk))

def reset_session():
    """Reset the transcription session for a new conversation"""
    global _transcription_session
    _transcription_session = None
    if _transcriber:
        _transcriber.transcription_buffer = []
    print("Session reset")
