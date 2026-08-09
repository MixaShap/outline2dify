FROM python:3.12-slim

WORKDIR /app

COPY sync.py .
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN mkdir -p /data

ENV STATE_FILE=/data/outline_dify_state.json

CMD ["python", "-u", "sync.py"]

