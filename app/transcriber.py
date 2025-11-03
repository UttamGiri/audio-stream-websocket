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
                asyncio.create_task(self._process_stream_results())
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
            print(f"Error processing stream results: {e}")
    
    async def send_audio_chunk_async(self, audio_chunk: bytes) -> Optional[str]:
        """
        Send audio chunk to AWS Transcribe Streaming (async)
        Continuously polls the results queue to return partial/final transcripts
        """
        try:
            if not self.is_streaming:
                print(f"Starting transcribe stream for audio chunk of {len(audio_chunk)} bytes")
                await self._start_stream_async()

            if not self.stream or not self.is_streaming:
                print("Stream not available - cannot send to AWS Transcribe")
                return None

            if self.stream.input_stream:
                # AWS Transcribe has frame size limits - chunk large audio into smaller pieces
                max_frame_size = 8192  # 8KB max per frame (AWS limit is typically 10KB)
                
                # Start collecting transcripts in background
                transcripts = []
                partial_transcript = None  # Track current partial result (accessible outside function)
                collection_done = asyncio.Event()
                
                async def collect_transcripts():
                    """Collect transcripts while sending audio - handles partial vs final correctly"""
                    nonlocal transcripts, partial_transcript
                    max_wait_time = 15.0  # Increased wait time for finalization
                    start_time = asyncio.get_event_loop().time()
                    last_transcript_time = start_time
                    
                    print(f"Starting transcript collection (waiting up to {max_wait_time}s)...")
                    
                    while True:
                        remaining_time = max_wait_time - (asyncio.get_event_loop().time() - start_time)
                        if remaining_time <= 0:
                            break
                        
                        # If no transcripts for 3 seconds after getting final ones, assume done
                        # Or if we have partial but no final for 5 seconds, use partial
                        current_time = asyncio.get_event_loop().time()
                        if transcripts and (current_time - last_transcript_time > 3.0):
                            print("No new final transcripts for 3s, assuming complete")
                            break
                        elif partial_transcript and not transcripts and (current_time - start_time > 5.0):
                            print("No final transcripts after 5s, will use partial")
                            break
                        
                        try:
                            result = await asyncio.wait_for(
                                self.results_queue.get(),
                                timeout=min(0.5, remaining_time)
                            )
                            
                            # Result is now a tuple: (transcript, is_partial)
                            transcript, is_partial = result
                            
                            if transcript:
                                if is_partial:
                                    # Partial result - replace current partial (don't append)
                                    partial_transcript = transcript
                                    print(f"Partial transcript: {transcript}")
                                else:
                                    # Final result - append to final transcripts
                                    transcripts.append(transcript)
                                    partial_transcript = None  # Clear partial after final
                                    last_transcript_time = asyncio.get_event_loop().time()
                                    print(f"Final transcript: {transcript}")
                                    # Reset timer when we get final results
                                    start_time = asyncio.get_event_loop().time()
                        except asyncio.TimeoutError:
                            # Keep waiting if we haven't gotten any final transcripts yet
                            if not transcripts:
                                continue
                            # Got some final transcripts, wait a bit more
                            await asyncio.sleep(0.2)
                    
                    collection_done.set()
                
                # Start collection task
                collection_task = asyncio.create_task(collect_transcripts())
                
                # Send audio frames
                if len(audio_chunk) > max_frame_size:
                    print(f"Large audio chunk ({len(audio_chunk)} bytes), splitting into frames of {max_frame_size} bytes")
                    frame_count = (len(audio_chunk) + max_frame_size - 1) // max_frame_size
                    for i in range(0, len(audio_chunk), max_frame_size):
                        chunk_frame = audio_chunk[i:i+max_frame_size]
                        frame_num = i // max_frame_size + 1
                        print(f"Sending frame {frame_num}/{frame_count} ({len(chunk_frame)} bytes)")
                        await self.stream.input_stream.send_audio_event(audio_chunk=chunk_frame)
                        # Small delay between frames to keep stream alive and avoid overwhelming
                        await asyncio.sleep(0.05)
                    print(f"All {len(audio_chunk)} bytes sent successfully to AWS Transcribe")
                else:
                    print(f"Sending {len(audio_chunk)} bytes to AWS Transcribe Streaming")
                    await self.stream.input_stream.send_audio_event(audio_chunk=audio_chunk)
                    print(f"Audio chunk sent successfully to AWS Transcribe")
                
                # Wait for collection to complete (with longer timeout for finalization)
                await collection_task
                
                if transcripts:
                    combined_transcript = " ".join(transcripts)
                    print(f"Final transcription: {combined_transcript}")
                    return combined_transcript
                elif partial_transcript:
                    # If we didn't get final transcripts but have a partial, use it as fallback
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

