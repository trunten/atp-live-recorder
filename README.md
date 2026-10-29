# ATP Live Recorder

Automatically record livestreams from [Accidental Tech Podcast](https://atp.fm/) and save them as MP3 files.

The recorder checks when ATP is broadcasting, starts recording when the stream goes live, and saves the finished audio to a `recordings` folder. It can run quietly in the background on a computer or home server.

## Quick start (Docker)

**You'll need:** Docker with Docker Compose, and a computer that can stay on during the broadcast.

1. [Download this repository](https://github.com/trunten/atp-live-recorder/archive/refs/heads/main.zip) and extract it.
2. Open a terminal in the extracted project folder.
3. Run:

   ```sh
   docker compose up -d --build
   ```

That's it! The recorder will watch for the next livestream. Completed recordings appear in the **`recordings/`** folder in the project directory.

To see what it's doing:

```sh
docker compose logs -f
```

To stop it:

```sh
docker compose down
```

With Docker running, the recorder restarts automatically after a reboot. On Linux, files created in the recordings folder may be owned by root depending on your Docker setup.

## Run directly with Python

**You'll need:** Python 3.10 or newer and [FFmpeg](https://ffmpeg.org/download.html) installed and available on your PATH.

From the project folder:

```sh
python3 atp_recorder.py
```

Leave the program running to watch for livestreams. Recordings are saved in `./recordings/`. Press **Ctrl+C** to stop.

Other useful commands:

```sh
# Check whether ATP is live right now
python3 atp_recorder.py check

# Record the current stream if ATP is live, then exit
python3 atp_recorder.py record

# Save recordings to a different folder
python3 atp_recorder.py watch --out-dir /path/to/recordings

# Change how often ATP is checked between broadcasts
python3 atp_recorder.py watch --poll-seconds 90
```

On Windows, you might need to use `python` or `py` instead of `python3`.

## How recording works

- **Automatic detection:** Checks ATP's livestream status every 60 seconds while idle.
- **Audio format:** Saves 64 kbps MP3 files, suitable for speech and convenient playback.
- **File naming:** `ATP_Live_YYYY-MM-DD_HHMMSS_UTC.mp3` (using the recording's start time).
- **End detection:** Finishes after four consecutive offline checks, roughly two minutes.
- **Connection recovery:** Attempts to reconnect after interruptions and combine usable audio segments into one recording.
- **Long broadcasts:** Each recording has a default limit of 5 hours 15 minutes. If ATP is still live, the watcher can start another recording.

A typical filename looks like:

```text
recordings/ATP_Live_2026-10-28_190000_UTC.mp3
```

The computer running the recorder needs to remain powered on and connected to the internet during a broadcast. Make sure there's sufficient free disk space for recordings.

## Troubleshooting

If a recording doesn't appear, check the terminal output or Docker logs:

```sh
docker compose logs -f
```

For a direct Python installation, you can test stream detection with `python3 atp_recorder.py check` and verify FFmpeg is available with `ffmpeg -version`.

## Contributing

Issues and pull requests are welcome.

To run the Python tests:

```sh
python3 -m unittest discover -s tests -v
```

## Licence

[MIT](LICENSE). This is an independent community project and is not affiliated with Accidental Tech Podcast. Please respect applicable rights and permissions when recording or sharing audio.
