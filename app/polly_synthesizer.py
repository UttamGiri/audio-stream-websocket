import boto3
import os
from typing import Optional

class PollySynthesizer:
    """Handles Amazon Polly text-to-speech synthesis"""
    
    def __init__(self):
        # Get AWS credentials from environment or use default boto3 credentials chain
        aws_access_key = os.getenv('AWS_ACCESS_KEY_ID')
        aws_secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        region = os.getenv('AWS_REGION', 'us-east-1')
        
        # Debug: Check if credentials are loaded
        if aws_access_key:
            print(f"Polly: AWS credentials found (key: {aws_access_key[:8]}...)")
        else:
            print("Polly: AWS_ACCESS_KEY_ID not found, using default boto3 credential chain")
        
        # Create client with explicit credentials if provided, otherwise use default chain
        if aws_access_key and aws_secret_key:
            self.polly_client = boto3.client(
                'polly',
                region_name=region,
                aws_access_key_id=aws_access_key,
                aws_secret_access_key=aws_secret_key
            )
        else:
            # Use default credential chain (env vars, ~/.aws/credentials, IAM role)
            self.polly_client = boto3.client('polly', region_name=region)
        
        self.voice_id = 'Joanna'  # Default voice
        self.output_format = 'pcm'  # PCM format for streaming

    def synthesize_speech(self, text: str, voice_id: str = '') -> Optional[bytes]:
        """
        Convert text to speech using Amazon Polly
        Returns audio bytes or None if error
        """
        try:
            voice = voice_id if voice_id else self.voice_id
            
            response = self.polly_client.synthesize_speech(
                Text=text,
                OutputFormat='pcm',
                VoiceId=voice,
                SampleRate='16000',
                Engine='neural' if voice_id else 'standard'
            )
            
            return response['AudioStream'].read()
        except Exception as e:
            print(f"Error synthesizing speech: {e}")
            return None
    
    def get_available_voices(self) -> list:
        """Get list of available voices"""
        try:
            response = self.polly_client.describe_voices()
            return [voice['Name'] for voice in response['Voices']]
        except Exception as e:
            print(f"Error getting voices: {e}")
            return []

