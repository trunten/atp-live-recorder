#!/usr/bin/env python3
"""Record ATP livestreams to local MP3 files. No cloud accounts required."""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import shutil
import signal
import subprocess
import sys
import time
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

STATUS_URL = "https://atp.fm/livestream_status"
USER_AGENT = "ATP-Live-Recorder/1.0"


class StreamError(RuntimeError):
    """ATP status or recording could not be trusted."""


@dataclass(frozen=True)
class LiveStatus:
    live: bool
    stream_url: str | None = None


class _AudioParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.in_audio = False
        self.audio_url: str | None = None
        self.source_url: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        props = dict(attrs)
        if tag.lower() == "audio":
            self.in_audio = True
            if props.get("src") and self.audio_url is None:
                self.audio_url = props["src"]
        elif tag.lower() == "source" and self.in_audio:
            if props.get("src") and self.source_url is None:
                self.source_url = props["src"]

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() == "audio":
            self.in_audio = False


def _valid_stream_url(value: str | None) -> str | None:
    if not value:
        return None
    url = value.strip()
    parsed = urlparse(url)
    return url if parsed.scheme in ("http", "https") and parsed.netloc else None


def stream_url_from_player(player: str) -> str | None:
    """Extract an HTTP(S) audio URL from ATP's embedded player."""
    if _valid_stream_url(player):
        return player.strip()
    parser = _AudioParser()
    parser.feed(player)
    for candidate in (parser.source_url, parser.audio_url):
        valid = _valid_stream_url(candidate)
        if valid:
            return valid
    for candidate in re.findall(r"https?://[^\s\"'<>]+", player):
        valid = _valid_stream_url(candidate.rstrip(")];,"))
        if valid:
            return valid
    return None


def parse_status(body: bytes) -> LiveStatus:
    try:
        data = json.loads(body)
    except (ValueError, UnicodeDecodeError) as exc:
        raise StreamError("ATP status endpoint did not return valid JSON") from exc
    if not isinstance(data, dict) or not isinstance(data.get("live"), bool):
        raise StreamError("ATP status response is missing boolean live field")
    if not data["live"]:
        return LiveStatus(live=False)
    player = data.get("player")
    if not isinstance(player, str):
        raise StreamError("ATP says LIVE but player field is not a string")
    url = stream_url_from_player(player)
    if not url:
        raise StreamError("ATP says LIVE but no audio URL could be extracted")
    return LiveStatus(live=True, stream_url=url)


def get_status(status_url: str = STATUS_URL, timeout: float = 12) -> LiveStatus:
    request = Request(
        status_url,
        headers={"User-Agent": USER_AGENT, "Cache-Control": "no-cache", "Accept": "application/json"},
    )
    try:
        with urlopen(request, timeout=timeout) as response:
            return parse_status(response.read(500_000))
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise StreamError(f"ATP status request failed: {exc.__class__.__name__}") from exc


def _ffmpeg_command(stream_url: str, destination: Path) -> list[str]:
    return [
        "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
        "-rw_timeout", "15000000", "-reconnect", "1",
        "-reconnect_streamed", "1", "-reconnect_delay_max", "15",
        "-i", stream_url, "-map", "0:a:0", "-vn", "-c:a", "libmp3lame",
        "-b:a", "64k", "-f", "mp3", str(destination),
    ]


def _stop_ffmpeg(proc: subprocess.Popen[bytes] | None) -> None:
    if proc is None or proc.poll() is not None:
        return
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(timeout=15)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


def _combine_segments(parts: list[Path], destination: Path) -> Path:
    if len(parts) == 1:
        shutil.move(str(parts[0]), str(destination))
        return destination
    manifest = destination.parent / ".ffmpeg-concat.txt"

    def quote(p: Path) -> str:
        return str(p.absolute()).replace("'", "'\\''")

    manifest.write_text("".join(f"file '{quote(p)}'\n" for p in parts), encoding="utf-8")
    try:
        subprocess.run(
            ["ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error", "-y",
             "-f", "concat", "-safe", "0", "-i", str(manifest), "-c", "copy", str(destination)],
            check=True, timeout=240,
        )
    finally:
        manifest.unlink(missing_ok=True)
    if not destination.exists() or destination.stat().st_size < 8192:
        raise StreamError("FFmpeg produced an empty or unusable merged recording")
    return destination


def capture(
    output_dir: Path,
    status_url: str = STATUS_URL,
    *,
    poll_seconds: float = 30,
    offline_checks: int = 4,
    max_seconds: float = 315 * 60,
    status_reader: Callable[[str], LiveStatus] | None = None,
) -> Path | None:
    """Capture a live stream; finish after four offline checks or the time limit."""
    if status_reader is None:
        status_reader = get_status
    current_status = status_reader(status_url)
    if not current_status.live:
        return None
    if shutil.which("ffmpeg") is None:
        raise StreamError("FFmpeg is required to record audio")
    output_dir.mkdir(parents=True, exist_ok=True)
    started_at = datetime.now(timezone.utc)
    output_path = output_dir / f"ATP_Live_{started_at:%Y-%m-%d_%H%M%S}_UTC.mp3"
    part_dir = output_dir / ".parts"
    part_dir.mkdir(exist_ok=True)
    parts: list[Path] = []
    proc: subprocess.Popen[bytes] | None = None
    active_part: Path | None = None
    consecutive_offline = 0
    consecutive_status_errors = 0
    restarted = 0
    stop_requested = False
    caught: BaseException | None = None
    started = time.monotonic()

    def request_stop(signum: int, _frame: object) -> None:
        nonlocal stop_requested
        stop_requested = True
        print(f"Received signal {signum}; finalizing any captured audio", flush=True)

    old_term = signal.getsignal(signal.SIGTERM)
    old_int = signal.getsignal(signal.SIGINT)
    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    def consume_part() -> None:
        nonlocal active_part
        if active_part and active_part.exists():
            size = active_part.stat().st_size
            if size >= 8192:
                parts.append(active_part)
                print(f"Saved audio segment {len(parts)}, {size:,} bytes", flush=True)
            else:
                active_part.unlink(missing_ok=True)
        active_part = None

    try:
        while not stop_requested and time.monotonic() - started < max_seconds:
            if current_status.live and proc is None:
                active_part = part_dir / f"part-{len(parts) + restarted + 1:03d}.mp3"
                cmd = _ffmpeg_command(current_status.stream_url or "", active_part)
                print("Starting FFmpeg capture", flush=True)
                proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                        stderr=subprocess.DEVNULL)

            remaining = max_seconds - (time.monotonic() - started)
            time.sleep(max(0, min(poll_seconds, remaining)))
            if proc and proc.poll() is not None:
                exit_code = proc.returncode
                proc = None
                consume_part()
                restarted += 1
                print(f"Audio connection ended ({exit_code}); checking broadcast before restart", flush=True)
                if restarted > 8:
                    raise StreamError("Audio stream repeatedly disconnected; ending recording")

            try:
                current_status = status_reader(status_url)
                consecutive_status_errors = 0
            except StreamError as exc:
                consecutive_status_errors += 1
                print(f"Status check unavailable ({consecutive_status_errors}): {exc}", flush=True)
                if consecutive_status_errors >= 20:
                    raise StreamError("Status endpoint unavailable for too long") from exc
                continue

            if not current_status.live:
                consecutive_offline += 1
                print(f"Stream reports OFFLINE ({consecutive_offline}/{offline_checks})", flush=True)
                if consecutive_offline >= offline_checks:
                    print("Broadcast ended; finalizing recording", flush=True)
                    break
            else:
                consecutive_offline = 0
        else:
            print("Recording time limit reached; finalizing this part", flush=True)
    except BaseException as exc:
        caught = exc
    finally:
        try:
            _stop_ffmpeg(proc)
            consume_part()
            if parts:
                _combine_segments(parts, output_path)
                print(f"Recording saved: {output_path.name} ({output_path.stat().st_size:,} bytes)", flush=True)
            else:
                print("No usable audio segments captured", flush=True)
        except BaseException as finish_exc:
            caught = caught or finish_exc
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)
            if output_path.exists():
                shutil.rmtree(part_dir, ignore_errors=True)

    if caught:
        raise caught
    if not output_path.exists():
        raise StreamError("ATP was live, but no recording was produced")
    return output_path


def watch(
    output_dir: Path,
    status_url: str = STATUS_URL,
    *,
    poll_seconds: float = 60,
    max_seconds: float = 315 * 60,
) -> None:
    """Wait for ATP to go live, record locally, repeat."""
    if shutil.which("ffmpeg") is None:
        raise StreamError("FFmpeg is not installed. See README or use Docker Compose.")
    output_dir.mkdir(parents=True, exist_ok=True)
    print(f"ATP recorder watching; MP3s are saved in {output_dir.resolve()}", flush=True)
    while True:
        try:
            status = get_status(status_url)
            if status.live:
                print("ATP LIVE - starting recording", flush=True)
                recorded = capture(output_dir, status_url, max_seconds=max_seconds)
                if recorded is not None:
                    print(f"Recording complete: {recorded}", flush=True)
            else:
                print("ATP offline", flush=True)
        except (StreamError, OSError, subprocess.SubprocessError) as exc:
            print(f"Recorder warning: {exc}", file=sys.stderr, flush=True)
        time.sleep(poll_seconds)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Automatically record ATP livestreams as local MP3 files")
    parser.add_argument("mode", nargs="?", choices=("watch", "check", "record"), default="watch")
    parser.add_argument("--status-url", default=STATUS_URL, help=argparse.SUPPRESS)
    parser.add_argument("--out-dir", type=Path, default=Path("recordings"))
    parser.add_argument("--poll-seconds", type=int, default=60, help="Seconds between checks (default: 60)")
    parser.add_argument("--max-minutes", type=int, default=315, help="Maximum minutes per recording (default: 315)")
    args = parser.parse_args(argv)
    if args.poll_seconds < 10:
        parser.error("--poll-seconds must be at least 10")
    if args.max_minutes < 1:
        parser.error("--max-minutes must be at least 1")
    try:
        if args.mode == "check":
            status = get_status(args.status_url)
            print("ATP LIVE" if status.live else "ATP offline", flush=True)
        elif args.mode == "record":
            capture(args.out_dir, args.status_url, max_seconds=args.max_minutes * 60)
        else:
            watch(args.out_dir, args.status_url, poll_seconds=args.poll_seconds,
                  max_seconds=args.max_minutes * 60)
        return 0
    except KeyboardInterrupt:
        print("\nStopped.", flush=True)
        return 0
    except (StreamError, OSError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr, flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
