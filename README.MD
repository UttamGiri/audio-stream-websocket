# Audio Stream WebSocket

Real-time audio processing pipeline using WebSocket, AWS Transcribe, LLM, and Amazon Polly.

## Features

- **Streaming Audio**: Real-time audio chunk processing over WebSocket
- **Speech-to-Text**: AWS Transcribe Streaming for audio transcription
- **LLM Processing**: OpenAI GPT for intelligent text processing
- **Text-to-Speech**: Amazon Polly for audio synthesis
- **Docker Support**: Containerized deployment
- **Kubernetes Ready**: k8s manifests included for EKS

## Architecture

```
Audio Chunks → AWS Transcribe → LLM (OpenAI) → Amazon Polly → Audio Response
```

## Prerequisites

- Python 3.11+
- Docker (optional, for containerized deployment)
- AWS Account with:
  - Transcribe permissions
  - Polly permissions
- OpenAI API Key

## Setup

### 1. Install Dependencies

```bash
pip install -r app/requirements.txt
```

### 2. Configure Environment Variables

Create a `.env` file:

```env
WEBSOCKET_HOST=0.0.0.0
WEBSOCKET_PORT=8765
AWS_ACCESS_KEY_ID=your_access_key
AWS_SECRET_ACCESS_KEY=your_secret_key
AWS_REGION=us-east-1
OPENAI_API_KEY=your_openai_key
```

### 3. Run Locally

**Start the server:**
```bash
python app/server.py
```

**Run test client:**
```bash
python tests/test_client.py
```

## Docker Deployment

### Build Image
```bash
docker build -t audio-stream-websocket .
```

### Run Container
```bash
docker run -it -p 8765:8765 \
  -e AWS_ACCESS_KEY_ID=your_key \
  -e AWS_SECRET_ACCESS_KEY=your_secret \
  -e OPENAI_API_KEY=your_key \
  audio-stream-websocket
```

## Kubernetes Deployment

### Deploy to EKS
```bash
kubectl apply -f k8s/deployment.yaml
kubectl apply -f k8s/service.yaml
```

### Check Status
```bash
kubectl get pods
kubectl get svc audio-stream-websocket
```

## Project Structure

```
.
├── app/
│   ├── server.py              # WebSocket server
│   ├── audio_processor.py     # Main processing pipeline
│   ├── transcriber.py         # AWS Transcribe integration
│   ├── llm_processor.py       # OpenAI LLM integration
│   ├── polly_synthesizer.py   # Amazon Polly integration
│   ├── utils.py               # Utility functions
│   └── requirements.txt       # Python dependencies
├── tests/
│   └── test_client.py         # Test client
├── k8s/
│   ├── deployment.yaml        # Kubernetes deployment
│   └── service.yaml           # Kubernetes service
├── Dockerfile                 # Docker configuration
└── README.MD                  # This file
```

## API

### WebSocket Connection
```
ws://localhost:8765
```

### Message Format
- **Input**: Audio chunks (bytes)
- **Output**: Processed audio chunks (bytes)

### Example Usage

```python
import asyncio
from websockets.client import connect

async def test_client():
    uri = "ws://localhost:8765"
    async with connect(uri) as websocket:
        # Send audio chunk
        await websocket.send(audio_chunk)
        
        # Receive processed audio
        response = await websocket.recv()
```

## Development

### Testing
```bash
python tests/test_client.py
```

### Linting
```bash
# Check for errors
python -m pylint app/
```

## Notes

- AWS Transcribe streaming implementation is currently a placeholder
- For production, implement full WebSocket connection to AWS Transcribe
- Ensure proper IAM permissions for AWS services
- Set up rate limiting for OpenAI API

## License

MIT
