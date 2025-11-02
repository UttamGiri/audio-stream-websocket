import os
from typing import Optional
from openai import OpenAI

class LLMProcessor:
    """Handles LLM text processing using OpenAI"""
    
    def __init__(self):
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("Warning: OPENAI_API_KEY not found in environment")
            self.client = None
        else:
            self.client = OpenAI(api_key=api_key)
    
    def process_text(self, text: str, system_prompt: str = "You are a helpful assistant.") -> Optional[str]:
        """
        Send text to LLM and get response
        Returns LLM's response or None if error
        """
        if not self.client:
            return "Error: LLM not configured. Please set OPENAI_API_KEY."
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.7,
                max_tokens=500
            )
            return response.choices[0].message.content
        except Exception as e:
            print(f"Error processing text with LLM: {e}")
            return None

