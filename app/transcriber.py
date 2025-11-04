import boto3
import json
import asyncio
from typing import Optional
import os
from amazon_transcribe.client import TranscribeStreamingClient
from amazon_transcribe.handlers import TranscriptResultStreamHandler
from amazon_transcribe.model import TranscriptEvent

class Transcriber:
    """Handles AWS Transcribe Streaming for real-time audio transcription"""
    
    def __init__(self):
        self.region = os.getenv('AWS_REGION', 'us-east-1')
        
        # Get AWS credentials from environment
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        aws_session_token = os.getenv('AWS_SESSION_TOKEN')
        
        # Debug: Check if credentials are loaded
        if aws_access_key:
            print(f"Transcriber: AWS credentials found (key: {aws_access_key[:8]}...)")
        else:
            print("Transcriber: AWS_ACCESS_KEY_ID not found, using default boto3 credential chain")
        
        # Create boto3 session with credentials to ensure they're available
        if aws_access_key and aws_secret_key:
            session = boto3.Session(
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key,
                region_name=self.region
            )
            # Set credentials in environment for amazon-transcribe library
            os.environ['AWS_ACCESS_KEY_ID'] = aws_access_key
            os.environ['AWS_SECRET_ACCESS_KEY'] = aws_secret_key
            if aws_session_token:
                os.environ['AWS_SESSION_TOKEN'] = aws_session_token
            os.environ['AWS_REGION'] = self.region
        
        # Initialize Transcribe Streaming Client
        # Clear any proxy settings that might cause issues with amazon-transcribe
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy', 'ALL_PROXY', 'all_proxy']
        for proxy_var in proxy_vars:
            if proxy_var in os.environ:
                del os.environ[proxy_var]
                print(f"Removed {proxy_var} from environment")
        
        # amazon-transcribe uses boto3 credential chain from environment variables
        try:
            self.transcribe_client = TranscribeStreamingClient(region=self.region)
            print("TranscribeStreamingClient initialized successfully")
        except (TypeError, ValueError) as e:
            if 'proxies' in str(e).lower():
                print(f"Warning: amazon-transcribe library proxies error (even after clearing). Disabling transcription.")
                self.transcribe_client = None
            else:
                raise
        except Exception as e:
            print(f"Error initializing TranscribeStreamingClient: {e}")
            print("Note: amazon-transcribe library will use boto3 credential chain from environment")
            # Fallback: will use default credential chain
            self.transcribe_client = None
        
        self.transcription_buffer = []
        self.language_code = 'en-US'
        self.stream = None
        self.stream_handler = None
        self.results_queue = asyncio.Queue()
        self.audio_buffer = []
        self.is_streaming = False
        self._result_processor_task = None  # Track the background task
    
    def start_transcription(self, language_code: str = 'en-US') -> Optional[dict]:
        """Start a new transcription session"""
        try:
            print("Starting transcription session")
            self.language_code = language_code
            self.audio_buffer = []
            self.transcription_buffer = []
            self.is_streaming = False
            return {"status": "ready"}
        except Exception as e:
            print(f"Error starting transcription: {e}")
            return None
    
    async def _start_stream_async(self):
        """Start the async transcription stream"""
        try:
            # If stream is already running, don't start a new one
            if self.is_streaming and self.stream:
                print("Stream already running, skipping start")
                return
            
            # Clean up any existing stream first
            if self.stream:
                print("Closing existing stream before starting new one...")
                self.is_streaming = False
                self.stream = None
            
            if self._result_processor_task and not self._result_processor_task.done():
                print("Cancelling old result processor task...")
                self._result_processor_task.cancel()
                try:
                    # Wait a bit for task to cancel, but don't wait too long
                    await asyncio.wait_for(self._result_processor_task, timeout=1.0)
                except (asyncio.CancelledError, asyncio.TimeoutError):
                    pass
                self._result_processor_task = None
            
            # Clear results queue to remove any stale results
            while not self.results_queue.empty():
                try:
                    self.results_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            
            if not self.transcribe_client:
                print("Transcribe client not initialized, cannot start stream")
                return
                
            try:
                print(f"Calling AWS Transcribe Streaming API to start stream...")
                print(f"  Language: {self.language_code}, Sample Rate: 16000, Encoding: pcm")
                self.stream = await self.transcribe_client.start_stream_transcription(
                    language_code=self.language_code,
                    media_sample_rate_hz=16000,
                    media_encoding='pcm'
                )
                print("AWS Transcribe stream connection established!")
                
                # Start background task to process results
                self._result_processor_task = asyncio.create_task(self._process_stream_results())
                print("Started background task to receive transcription results")
                
                self.is_streaming = True
                print("Transcribe stream started successfully - ready to receive audio")
            except TypeError as e:
                if 'proxies' in str(e):
                    print(f"Warning: amazon-transcribe library version issue (proxies error). Stream may not work.")
                    print("This is a known compatibility issue. Transcription will be disabled.")
                    self.stream = None
                    self.is_streaming = False
                else:
                    raise
        except Exception as e:
            print(f"Error starting transcribe stream: {e}")
            self.is_streaming = False
            self.stream = None
    
    async def _process_stream_results(self):
        """Process transcription results from stream"""
        try:
            if not self.stream:
                return
            async for event in self.stream.output_stream:
                if isinstance(event, TranscriptEvent):
                    results = event.transcript.results
                    for result in results:
                        if result.alternatives:
                            transcript = result.alternatives[0].transcript
                            if transcript:  # Only send non-empty transcripts
                                # Send tuple: (transcript, is_partial)
                                await self.results_queue.put((transcript, result.is_partial))
                                if not result.is_partial:
                                    # Final result - also add to buffer
                                    self.transcription_buffer.append(transcript)
        except Exception as e:
            error_msg = str(e).lower()
            if "timeout" in error_msg or "no new audio" in error_msg:
                # Timeout is expected between batches - keep stream open for next batch
                # Don't reset stream state - it will be reused
                # Just restart the result processor task
                self._result_processor_task = None
                # Stream stays open, we'll restart the processor task when new audio arrives
            else:
                print(f"Error processing stream results: {e}")
                # Reset stream state on actual errors only
                self.is_streaming = False
                self.stream = None
                self._result_processor_task = None
    
    async def send_audio_chunk_async(self, audio_chunk: bytes) -> Optional[str]:
        """
        Send audio chunk to AWS Transcribe Streaming and get transcription results
        """
        try:
            # Start stream if not already running
            if not self.is_streaming or not self.stream:
                print(f"Starting transcribe stream for audio chunk of {len(audio_chunk)} bytes")
                await self._start_stream_async()

            if not self.stream:
                print("Stream not available - cannot send to AWS Transcribe")
                return None
            
            # Restart result processor task if it was stopped (e.g., after timeout)
            if not self._result_processor_task or self._result_processor_task.done():
                self._result_processor_task = asyncio.create_task(self._process_stream_results())
                self.is_streaming = True

            if self.stream.input_stream:
                # AWS Transcribe has frame size limits - chunk large audio into smaller pieces
                max_frame_size = 8192  # 8KB max per frame
                
                # Start collecting transcripts in background
                transcripts = []
                partial_transcript = None
                
                async def collect_transcripts():
                    """Collect transcripts while sending audio"""
                    nonlocal transcripts, partial_transcript
                    max_wait_time = 8.0
                    start_time = asyncio.get_event_loop().time()
                    last_transcript_time = start_time
                    no_final_timeout = 2.0
                    
                    # Removed verbose logging
                    while True:
                        remaining_time = max_wait_time - (asyncio.get_event_loop().time() - start_time)
                        if remaining_time <= 0:
                            break
                        
                        current_time = asyncio.get_event_loop().time()
                        
                        # If we have final transcripts, wait 0.5s more
                        if transcripts and (current_time - last_transcript_time > 0.5):
                            await asyncio.sleep(0.5)
                            break
                        elif partial_transcript and not transcripts and (current_time - start_time > no_final_timeout):
                            break
                        
                        try:
                            result = await asyncio.wait_for(
                                self.results_queue.get(),
                                timeout=min(0.3, remaining_time)
                            )
                            
                            transcript, is_partial = result
                            
                            if transcript:
                                if is_partial:
                                    partial_transcript = transcript
                                    # Don't log partial transcripts to reduce noise
                                else:
                                    transcripts.append(transcript)
                                    partial_transcript = None
                                    last_transcript_time = asyncio.get_event_loop().time()
                                    # Final transcripts will be logged at the end
                        except asyncio.TimeoutError:
                            if transcripts:
                                if (asyncio.get_event_loop().time() - last_transcript_time) > 0.5:
                                    break
                                continue
                            if not transcripts and not partial_transcript:
                                continue
                            if partial_transcript:
                                if (asyncio.get_event_loop().time() - start_time) > no_final_timeout:
                                    break
                                continue
                
                # Start collection task
                collection_task = asyncio.create_task(collect_transcripts())
                
                # Send audio frames
                try:
                    if len(audio_chunk) > max_frame_size:
                        # Split large chunks silently
                        for i in range(0, len(audio_chunk), max_frame_size):
                            chunk_frame = audio_chunk[i:i+max_frame_size]
                            await self.stream.input_stream.send_audio_event(audio_chunk=chunk_frame)
                            await asyncio.sleep(0.05)  # Small delay between frames
                    else:
                        await self.stream.input_stream.send_audio_event(audio_chunk=audio_chunk)
                except Exception as send_error:
                    error_msg = str(send_error).lower()
                    if "timeout" in error_msg or "no new audio" in error_msg:
                        print(f"⚠️  Transcribe stream timed out - resetting")
                        self.is_streaming = False
                        self.stream = None
                        if self._result_processor_task:
                            self._result_processor_task.cancel()
                            self._result_processor_task = None
                        if not collection_task.done():
                            collection_task.cancel()
                        return None
                    else:
                        raise
                
                # Wait for collection to complete
                try:
                    await collection_task
                except asyncio.CancelledError:
                    print("Collection task cancelled")
                    return None
                
                # Return collected transcripts
                if transcripts:
                    combined_transcript = " ".join(transcripts)
                    print(f"Final transcription: {combined_transcript}")
                    return combined_transcript
                elif partial_transcript:
                    print(f"No final transcripts, using last partial: {partial_transcript}")
                    return partial_transcript
                else:
                    print("No transcription results received")
                    return None
            else:
                print("Stream input_stream not available")
                return None
        except Exception as e:
            print(f"Error processing audio chunk in async method: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None
    
    def send_audio_chunk(self, audio_chunk: bytes) -> Optional[str]:
        """
        Send audio chunk to AWS Transcribe Streaming (sync wrapper)
        Creates event loop if needed to call async method
        """
        try:
            # Try to get existing event loop
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    # Loop is running, need to use run_until_complete in thread
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as executor:
                        future = executor.submit(
                            asyncio.run,
                            self.send_audio_chunk_async(audio_chunk)
                        )
                        return future.result()
                else:
                    return loop.run_until_complete(self.send_audio_chunk_async(audio_chunk))
            except RuntimeError:
                # No event loop, create one
                return asyncio.run(self.send_audio_chunk_async(audio_chunk))
        except Exception as e:
            print(f"Error processing audio chunk: {e}")
            return None
    
    def get_transcription(self) -> Optional[str]:
        """Get the final transcription result"""
        if self.transcription_buffer:
            return ' '.join(self.transcription_buffer)
        return None

