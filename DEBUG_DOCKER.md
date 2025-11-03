# Debugging Docker Container

## Quick Start

### 1. Rebuild Docker Image (with debugpy)
```bash
docker build -t audio-stream-websocket .
```

### 2. Run Docker with Debugging Enabled
```bash
docker run -it -p 8765:8765 -p 5678:5678 \
  -e DEBUG=true \
  -e DEBUG_PORT=5678 \
  audio-stream-websocket
```

### 3. Attach Debugger from VS Code/Cursor
1. Set breakpoints in any file (`app/server.py`, `app/audio_processor.py`, etc.)
2. Press `F5` or go to Run and Debug
3. Select **"Python: Attach (Docker)"**
4. Press `F5` again

The debugger will connect to the Docker container and your breakpoints will trigger!

## Complete Example

```bash
# Terminal 1: Run Docker with debugging
docker run -it -p 8765:8765 -p 5678:5678 \
  -e DEBUG=true \
  -e DEBUG_PORT=5678 \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  -e OPENAI_API_KEY=your_key \
  audio-stream-websocket

# Terminal 2: Run test client
python3 tests/test_client.py
```

## Optional: Wait for Debugger

If you want the container to wait until debugger attaches before starting:

Edit `app/server.py` and uncomment:
```python
debugpy.wait_for_client()
```

## Troubleshooting

- **Breakpoints not triggering?** Make sure:
  - Docker container shows "Debugger listening on port 5678"
  - You're using "Python: Attach (Docker)" configuration
  - Port 5678 is mapped correctly

- **Connection refused?** Check:
  - Port 5678 is exposed in Docker
  - DEBUG=true is set
  - Container is running

