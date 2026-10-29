# ATP Live Recorder

**Automatically record [Accidental Tech Podcast](https://atp.fm/) livestreams as local MP3 files.**

No accounts, credentials, cloud storage, scheduling service, web UI, or third-party Python packages. The recorder checks ATP's live-status endpoint, records whenever ATP is live, and saves a dated MP3 on the computer running it.

> Independent community project, not affiliated with ATP. Respect applicable rights and permissions when making or sharing recordings.

## Quick start: Docker (recommended)

Requirements: Docker Engine / Docker Desktop with Docker Compose, and a computer that stays running during a livestream.

1. Download this repository and open a terminal in the extracted folder.
2. Run:

   ```sh
   docker compose up -d --build
   ```

3. That's it. Completed recordings appear in the **`recordings/`** folder alongside this README. Watch activity with:

   ```sh
   docker compose logs -f
   ```

To stop it:

```sh
docker compose down
```

It automatically restarts with the Docker service unless explicitly stopped. It does not record anything while the host machine is off. If running on Linux, make sure your user can read the files in `recordings/` (Docker-created files may be owned by root).

## Without Docker

Requires **Python 3.10 or later** and **FFmpeg** installed and available on your PATH. No `pip install` step.

```sh
python3 atp_recorder.py
```

MP3 files are saved to `./recordings/` by default. Keep this process running to monitor the stream automatically. For unattended use, run it as a background service on a computer or server that stays on.

Useful commands:

```sh
python3 atp_recorder.py check                         # See if ATP is live now
python3 atp_recorder.py record                        # Record if ATP is live now, then exit
python3 atp_recorder.py watch --out-dir /data/podcasts # Choose a folder
python3 atp_recorder.py watch --poll-seconds 90        # Adjust idle polling
```

On Windows, use `python` or `py` instead of `python3` if needed.

## How it behaves

- Checks `https://atp.fm/livestream_status` every 60 seconds while idle.
- Starts an FFmpeg recording when ATP reports a live stream.
- Outputs compressed 64 kbps MP3 files named `ATP_Live_YYYY-MM-DD_HHMMSS_UTC.mp3`.
- Polls the status every 30 seconds during a broadcast and finishes after four consecutive offline results (roughly two minutes).
- Attempts to reconnect and combine surviving segments if the audio stream briefly disconnects.
- Ends an individual recording after 315 minutes (5 hours 15 minutes) by default. If the show is still live, the watcher can begin a new file.
- Stores recordings **locally only**. It never automatically uploads, deletes completed MP3s, or sends data to a cloud account.

If a recording fails, check the logs. A power loss or unexpected crash can interrupt the current MP3; the script cannot guarantee recovery from sudden shutdown. Keep sufficient disk space available.

## Privacy and dependencies

The recorder makes requests to ATP's live-status endpoint and audio server. Docker downloads its base image and installs FFmpeg at build time. It does not use Google OAuth, Google Drive, rclone, Cloudflare, or GitHub Actions for recording. It does not collect telemetry or require an API key.

## Development

Run the included tests with:

```sh
python3 -m unittest discover -s tests -v
```

The main logic started from a personal recorder that has successfully captured a full ATP broadcast. This public, local-only packaging is separate from that deployment. Tests cover parsing, CLI options and output configuration, but the Docker build and a full live recording should be verified on your own host.

Licensed under MIT. See `LICENSE`.
