def log_message(message: str):
    """Simple logging helper"""
    print(f"[LOG] {message}")

def chunk_to_pcm(chunk: bytes) -> bytes:
    """
    Placeholder for future audio conversion or normalization.
    For example, if you receive raw bytes, you could normalize PCM16.
    """
    return chunk
