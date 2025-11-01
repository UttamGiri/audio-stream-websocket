FROM python:3.11-slim

WORKDIR /app

# Copy requirements
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy app folder contents directly into WORKDIR
COPY app/ ./app/

# Expose port
EXPOSE 8765

# Set PYTHONPATH so 'app' package is visible
ENV PYTHONPATH=/app

# Run server
CMD ["python", "app/server.py"]
