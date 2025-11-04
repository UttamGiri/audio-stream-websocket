import os
from typing import Optional
from openai import OpenAI
from dotenv import load_dotenv

# Load environment variables
load_dotenv()
print("LLM: Module llm_processor.py imported")

class LLMProcessor:
    """Handles LLM text processing using OpenAI"""
    
    def __init__(self):
        print("LLM: Initializing LLMProcessor...")
        # Try to load .env file (for local development)
        # In Docker, env vars are already set via --env-file
        load_dotenv(override=False)
        
        # Clear proxy settings that might cause issues with OpenAI client
        proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy', 'ALL_PROXY', 'all_proxy']
        for proxy_var in proxy_vars:
            if proxy_var in os.environ:
                del os.environ[proxy_var]
                print(f"LLM: Removed {proxy_var} from environment")
        
        # Get API key from environment (works in both local and Docker)
        api_key = os.environ.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
        
        print(f"LLM: API key check - found: {bool(api_key)}, length: {len(api_key) if api_key else 0}")
        
        if not api_key:
            print("Warning: OPENAI_API_KEY not found in environment")
            print(f"Debug: Checking env vars...")
            # Show all env vars (masked) for debugging
            env_keys = list(os.environ.keys())
            openai_keys = [k for k in env_keys if 'OPENAI' in k.upper() or 'OPEN' in k.upper()]
            print(f"Debug: Total env vars: {len(env_keys)}")
            if openai_keys:
                print(f"Debug: Found env vars containing 'OPEN': {openai_keys}")
                for key in openai_keys:
                    val = os.environ.get(key, '')
                    print(f"Debug: {key} = {'SET' if val else 'EMPTY'} (length: {len(val)})")
            else:
                print("Debug: No environment variables found with 'OPEN' in name")
                # Show first 20 env var names for debugging
                print(f"Debug: Sample env vars: {list(env_keys)[:20]}")
            self.client = None
        else:
            try:
                # Explicitly disable proxies by passing http_client without proxy config
                import httpx
                http_client = httpx.Client(timeout=60.0)
                self.client = OpenAI(api_key=api_key, http_client=http_client)
                print(f"LLM: OpenAI client initialized successfully (key: {api_key[:10]}...)")
            except Exception as e:
                print(f"LLM: Error initializing OpenAI client: {e}")
                # Fallback: try without explicit http_client
                try:
                    print("LLM: Trying without explicit http_client...")
                    self.client = OpenAI(api_key=api_key)
                    print(f"LLM: OpenAI client initialized (fallback method)")
                except Exception as e2:
                    print(f"LLM: Fallback also failed: {e2}")
                    import traceback
                    traceback.print_exc()
                    self.client = None
    
    def _load_resume(self) -> str:
        """Load resume content from file"""
        try:
            import os
            resume_path = os.path.join(os.path.dirname(__file__), 'resume.txt')
            if os.path.exists(resume_path):
                with open(resume_path, 'r', encoding='utf-8') as f:
                    return f.read()
        except Exception as e:
            print(f"LLM: Warning - Could not load resume: {e}")
        return ""
    
    def process_text(self, text: str, system_prompt: Optional[str] = None) -> Optional[str]:
        """
        Send text to LLM and get response
        Returns LLM's response or None if error
        """
        # Load resume if not provided with system prompt
        if system_prompt is None:
            resume_content = self._load_resume()
            if resume_content:
                system_prompt = f"""You are a helpful assistant representing Uttam Giri, an IT Specialist / Developer / AI & Cloud Architect.

Here is Uttam's professional background:

{resume_content}

IMPORTANT INSTRUCTIONS:
- When asked about Uttam, his experience, skills, background, qualifications, or any questions about him personally or professionally, scan and use the resume information above to provide accurate and helpful responses.
- For all other questions (general questions, current events, news, technology, etc.), provide normal helpful assistance using your knowledge. Answer general questions naturally without referencing the resume unless specifically asked about Uttam."""
            else:
                system_prompt = "You are a helpful assistant that can answer questions about current events, news, technology, and general topics."
        # If client is None, try to reinitialize one more time
        if not self.client:
            print("LLM: Client is None, attempting to reinitialize...")
            # Clear proxy vars again
            proxy_vars = ['HTTP_PROXY', 'HTTPS_PROXY', 'http_proxy', 'https_proxy', 'NO_PROXY', 'no_proxy', 'ALL_PROXY', 'all_proxy']
            for proxy_var in proxy_vars:
                if proxy_var in os.environ:
                    del os.environ[proxy_var]
            
            # Try to get API key and create client
            api_key = os.environ.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
            if api_key:
                try:
                    # Explicitly disable proxies by passing http_client without proxy config
                    import httpx
                    http_client = httpx.Client(timeout=60.0)
                    self.client = OpenAI(api_key=api_key, http_client=http_client)
                    print(f"LLM: Client reinitialized successfully in process_text")
                except Exception as e:
                    print(f"LLM: Failed to reinitialize client: {e}")
                    import traceback
                    traceback.print_exc()
            
            if not self.client:
                error_msg = "Error: LLM not configured. Please set OPENAI_API_KEY."
                print(f"LLM: {error_msg}")
                return error_msg
        
        try:
            response = self.client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": text}
                ],
                temperature=0.7,
                max_tokens=50  # Reduced for very short, concise responses
            )
            if response.choices and len(response.choices) > 0:
                result = response.choices[0].message.content
                return result
            else:
                return None
        except Exception as e:
            print(f"LLM: Error processing text with LLM: {type(e).__name__}: {e}")
            import traceback
            traceback.print_exc()
            return None

