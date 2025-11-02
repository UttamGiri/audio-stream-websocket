import boto3
import os
from typing import Optional

class PollySynthesizer:
    """Handles Amazon Polly text-to-speech synthesis"""
    
    def __init__(self):
        self.polly_client = boto3.client('polly', region_name='us-east-1')
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

