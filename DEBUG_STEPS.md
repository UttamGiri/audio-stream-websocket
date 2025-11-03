# How to Debug Docker Container

## Step-by-Step Instructions

### Step 1: Start Docker Container
```bash
docker run -it -p 8765:8765 -p 5678:5678 \
  -e DEBUG=true \
  -e DEBUG_PORT=5678 \
  audio-stream-websocket
```

**Wait for this message:**
```
Debugger listening on port 5678. Waiting for debugger to attach...
WebSocket server listening on 0.0.0.0:8765
```

### Step 2: Set Breakpoints in Your Code
- Open any file (e.g., `app/server.py`, `app/audio_processor.py`)
- Click in the left margin to set a red breakpoint

### Step 3: Attach Debugger to Docker
1. Press `F5` or go to **Run and Debug** (`Cmd+Shift+D`)
2. **Select "Python: Attach (Docker)" from dropdown**
3. Press `F5` again

You should see "Debugger attached" or similar message.

### Step 4: Trigger Breakpoints
Run your test client in a separate terminal:
```bash
python3 tests/test_client.py
```

Your breakpoints in Docker code will now trigger!

## Troubleshooting

**Breakpoints not hitting?**
1. ✅ Make sure Docker shows "Debugger listening on port 5678"
2. ✅ Use "Python: Attach (Docker)" configuration (not "Test Client")
3. ✅ Wait for Docker to start before attaching
4. ✅ Check breakpoints are red (not gray)

**Still not working?**
- Try uncommenting `debugpy.wait_for_client()` in `server.py` line 19
- This makes Docker wait until debugger attaches

