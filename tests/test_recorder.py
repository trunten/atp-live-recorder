import json
import unittest
from pathlib import Path
from unittest.mock import patch

import atp_recorder as r


class StatusTests(unittest.TestCase):
    def test_offline(self):
        self.assertEqual(r.parse_status(b'{"live":false}'), r.LiveStatus(False))

    def test_live_audio_source(self):
        payload = {"live": True, "player": '<audio><source src="https://example.org/live.mp3" type="audio/mpeg"></audio>'}
        self.assertEqual(r.parse_status(json.dumps(payload).encode()).stream_url, "https://example.org/live.mp3")

    def test_live_audio_src(self):
        payload = {"live": True, "player": '<audio src="https://example.org/live.mp3"></audio>'}
        self.assertTrue(r.parse_status(json.dumps(payload).encode()).live)

    def test_reject_missing_live(self):
        with self.assertRaises(r.StreamError):
            r.parse_status(b'{}')

    def test_reject_missing_audio(self):
        with self.assertRaises(r.StreamError):
            r.parse_status(b'{"live":true,"player":"no media"}')

    def test_reject_bad_json(self):
        with self.assertRaises(r.StreamError):
            r.parse_status(b'{bad json}')

    def test_does_not_accept_non_http(self):
        self.assertIsNone(r.stream_url_from_player('<audio src="file:///tmp/not-media.mp3"></audio>'))


class CLIAndCaptureTests(unittest.TestCase):
    def test_check_offline_exit_code(self):
        with patch.object(r, "get_status", return_value=r.LiveStatus(False)):
            self.assertEqual(r.main(["check"]), 0)

    def test_check_live_exit_code(self):
        with patch.object(r, "get_status", return_value=r.LiveStatus(True, "https://example.org/live")):
            self.assertEqual(r.main(["check"]), 0)

    def test_record_offline_creates_no_file(self):
        with patch.object(r, "get_status", return_value=r.LiveStatus(False)):
            self.assertIsNone(r.capture(Path("/tmp/atp-not-recording")))

    def test_ffmpeg_codec(self):
        cmd = r._ffmpeg_command("https://example.org/live", Path("/tmp/file.mp3"))
        self.assertIn("libmp3lame", cmd)
        self.assertIn("64k", cmd)
        self.assertEqual(cmd[-1], "/tmp/file.mp3")

    def test_watch_requires_ffmpeg(self):
        with patch.object(r.shutil, "which", return_value=None):
            with self.assertRaises(r.StreamError):
                r.watch(Path("/tmp/test-atp"))


if __name__ == "__main__":
    unittest.main()
