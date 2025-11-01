docker build -t audio-stream-websocket .

docker images

docker run -it -p 8765:8765 audio-stream-websocket

docker ps or docker ps -a # audio-stream-websocket
