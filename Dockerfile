FROM python:3.12-slim-bookworm
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg ca-certificates \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY atp_recorder.py /app/atp_recorder.py
ENV PYTHONUNBUFFERED=1
ENTRYPOINT ["python3", "-u", "/app/atp_recorder.py"]
CMD ["watch", "--out-dir", "/recordings"]
