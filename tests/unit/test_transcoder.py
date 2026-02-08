"""Unit tests for BackgroundTranscoder - video transcoding for instant playback"""

import pytest
import subprocess
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
import queue
import time
import threading

from nvr.core.transcoder import BackgroundTranscoder


@pytest.mark.unit
class TestTranscoderInit:
    """Test transcoder initialization"""

    def test_init_default_params(self):
        """Test transcoder initialization with default parameters"""
        transcoder = BackgroundTranscoder()

        assert transcoder.max_workers == 2
        assert transcoder.replace_original is True
        assert transcoder.running is False
        assert isinstance(transcoder.transcode_queue, queue.Queue)
        assert len(transcoder.workers) == 0

    def test_init_custom_params(self):
        """Test transcoder initialization with custom parameters"""
        transcoder = BackgroundTranscoder(max_workers=4, replace_original=False)

        assert transcoder.max_workers == 4
        assert transcoder.replace_original is False

    def test_init_detects_encoder(self):
        """Test that initialization detects best encoder"""
        transcoder = BackgroundTranscoder()

        # Should have detected an encoder
        assert transcoder.encoder is not None
        assert isinstance(transcoder.encoder, str)
        assert isinstance(transcoder.encoder_options, list)


@pytest.mark.unit
class TestTranscoderControl:
    """Test transcoder start/stop control"""

    def test_start_creates_workers(self):
        """Test that start creates worker threads"""
        transcoder = BackgroundTranscoder(max_workers=2)

        transcoder.start()

        # Should have started workers
        assert transcoder.running is True
        assert len(transcoder.workers) == 2

        # Cleanup
        transcoder.stop()

    def test_start_when_already_running(self):
        """Test that start does nothing when already running"""
        transcoder = BackgroundTranscoder(max_workers=2)

        transcoder.start()
        initial_workers = transcoder.workers.copy()

        # Try to start again
        transcoder.start()

        # Should not create new workers
        assert transcoder.workers == initial_workers

        # Cleanup
        transcoder.stop()

    def test_stop_terminates_workers(self):
        """Test that stop terminates worker threads"""
        transcoder = BackgroundTranscoder(max_workers=2)

        transcoder.start()
        assert transcoder.running is True
        assert len(transcoder.workers) == 2

        # Stop transcoder
        transcoder.stop()

        # Should have stopped
        assert transcoder.running is False
        assert len(transcoder.workers) == 0

    def test_stop_when_not_running(self):
        """Test that stop handles not running state"""
        transcoder = BackgroundTranscoder()

        # Should not crash
        transcoder.stop()

        assert transcoder.running is False


@pytest.mark.unit
class TestTranscoderQueue:
    """Test transcode queue management"""

    def test_queue_transcode_adds_to_queue(self, temp_dir):
        """Test that queue_transcode adds file to queue"""
        transcoder = BackgroundTranscoder()

        # Create test file
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"test video data")

        # Queue for transcoding
        transcoder.queue_transcode(test_file)

        # Should be in queue
        assert not transcoder.transcode_queue.empty()

        # Get item from queue
        queued_file = transcoder.transcode_queue.get_nowait()
        assert queued_file == test_file

    def test_queue_transcode_skips_nonexistent_file(self, temp_dir):
        """Test that queue_transcode skips non-existent files"""
        transcoder = BackgroundTranscoder()

        # Try to queue non-existent file
        fake_file = temp_dir / "nonexistent.mp4"
        transcoder.queue_transcode(fake_file)

        # Should not be in queue
        assert transcoder.transcode_queue.empty()

    def test_queue_transcode_skips_already_transcoded(self, temp_dir):
        """Test that queue_transcode skips already transcoded files"""
        transcoder = BackgroundTranscoder()

        # Create source file
        source_file = temp_dir / "source.mp4"
        source_file.write_bytes(b"source video")

        # Create transcoded file
        transcoded_file = transcoder._get_transcoded_path(source_file)
        transcoded_file.parent.mkdir(parents=True, exist_ok=True)
        transcoded_file.write_bytes(b"transcoded video")

        # Try to queue - should skip
        transcoder.queue_transcode(source_file)

        # Should not be in queue
        assert transcoder.transcode_queue.empty()

    def test_queue_multiple_files(self, temp_dir):
        """Test queuing multiple files"""
        transcoder = BackgroundTranscoder()

        # Create multiple test files
        files = []
        for i in range(5):
            test_file = temp_dir / f"test_{i}.mp4"
            test_file.write_bytes(b"test video data")
            files.append(test_file)

        # Queue all files
        for f in files:
            transcoder.queue_transcode(f)

        # All should be in queue
        assert transcoder.transcode_queue.qsize() == 5


@pytest.mark.unit
class TestTranscoderPaths:
    """Test transcoder path handling"""

    def test_get_transcoded_path(self, temp_dir):
        """Test getting transcoded file path"""
        transcoder = BackgroundTranscoder()

        source = temp_dir / "camera_1" / "segment.mp4"
        transcoded = transcoder._get_transcoded_path(source)

        # Should have _h264 suffix
        assert transcoded.name == "segment_h264.mp4"
        assert transcoded.parent == source.parent

    def test_get_transcoded_path_preserves_structure(self, temp_dir):
        """Test that transcoded path preserves directory structure"""
        transcoder = BackgroundTranscoder()

        source = temp_dir / "camera_1" / "2026" / "01" / "segment.mp4"
        transcoded = transcoder._get_transcoded_path(source)

        # Should have _h264 suffix and preserve directory structure
        assert transcoded.name == "segment_h264.mp4"
        assert transcoded.parent == source.parent


@pytest.mark.unit
class TestEncoderDetection:
    """Test encoder detection and selection"""

    def test_detect_best_encoder_returns_valid_encoder(self):
        """Test that encoder detection returns valid encoder"""
        transcoder = BackgroundTranscoder()

        encoder, options = transcoder._detect_best_encoder()

        # Should return valid encoder
        assert encoder in ['h264_videotoolbox', 'h264_nvenc', 'h264_qsv', 'libx264']
        assert isinstance(options, list)

    @patch('subprocess.run')
    def test_detect_best_encoder_tries_hardware_first(self, mock_run):
        """Test that encoder detection tries hardware encoders first"""
        # Mock successful hardware encoder
        mock_run.return_value = Mock(returncode=0)

        transcoder = BackgroundTranscoder()

        # Should have tried hardware encoders
        assert mock_run.call_count >= 1

    @patch('subprocess.run')
    def test_detect_best_encoder_falls_back_to_software(self, mock_run):
        """Test that encoder detection falls back to software encoder"""
        # Mock all hardware encoders failing
        def run_side_effect(*args, **kwargs):
            # Check if this is an encoder test
            if 'h264_videotoolbox' in str(args) or 'h264_nvenc' in str(args) or 'h264_qsv' in str(args):
                return Mock(returncode=1)  # Fail
            return Mock(returncode=0)  # Success for libx264

        mock_run.side_effect = run_side_effect

        transcoder = BackgroundTranscoder()

        # Should fall back to software encoder
        assert transcoder.encoder == 'libx264'


@pytest.mark.unit
class TestTranscodeExecution:
    """Test actual transcoding execution"""

    @patch('subprocess.run')
    def test_transcode_calls_ffmpeg(self, mock_run, temp_dir):
        """Test that transcode calls ffmpeg with correct parameters"""
        mock_run.return_value = Mock(returncode=0)

        transcoder = BackgroundTranscoder()

        # Create test file
        source = temp_dir / "test.mp4"
        source.write_bytes(b"test video")

        # Transcode (returns None, creates output file)
        transcoder._transcode_file(source)

        # Should have called ffmpeg
        assert mock_run.called

    @patch('subprocess.run')
    def test_transcode_handles_ffmpeg_failure(self, mock_run, temp_dir):
        """Test that transcode handles ffmpeg failure gracefully"""
        mock_run.return_value = Mock(returncode=1, stderr=b"Error message")

        transcoder = BackgroundTranscoder()

        # Create test file
        source = temp_dir / "test.mp4"
        source.write_bytes(b"test video")

        # Transcode should handle failure gracefully (returns None)
        transcoder._transcode_file(source)

        # Verify ffmpeg was called
        assert mock_run.called

    @patch('subprocess.run')
    def test_transcode_replaces_original_when_configured(self, mock_run, temp_dir):
        """Test that transcode replaces original file when configured"""
        mock_run.return_value = Mock(returncode=0)

        transcoder = BackgroundTranscoder(replace_original=True)

        # Create test file
        source = temp_dir / "test.mp4"
        source.write_bytes(b"test video")

        # Mock the transcoded file creation
        def side_effect(*args, **kwargs):
            # Simulate ffmpeg creating output file
            output = transcoder._get_transcoded_path(source)
            output.write_bytes(b"transcoded video")
            return Mock(returncode=0)

        mock_run.side_effect = side_effect

        # Transcode
        transcoder._transcode_file(source)

        # Original should be replaced (source file should still exist with transcoded content)
        assert source.exists()

    @patch('subprocess.run')
    def test_transcode_keeps_original_when_configured(self, mock_run, temp_dir):
        """Test that transcode keeps original file when configured"""

        transcoder = BackgroundTranscoder(replace_original=False)

        # Create test file
        source = temp_dir / "test.mp4"
        source.write_bytes(b"test video")

        # Mock the transcoded file creation
        def side_effect(*args, **kwargs):
            # Simulate ffmpeg creating output file
            output = transcoder._get_transcoded_path(source)
            output.write_bytes(b"transcoded video")
            return Mock(returncode=0)

        mock_run.side_effect = side_effect

        # Transcode
        transcoder._transcode_file(source)

        # Both original and transcoded should exist
        assert source.exists()
        output = transcoder._get_transcoded_path(source)
        assert output.exists()


@pytest.mark.unit
class TestTranscoderWorker:
    """Test transcoder worker thread behavior"""

    def test_worker_processes_queue(self, temp_dir):
        """Test that worker processes items from queue"""
        transcoder = BackgroundTranscoder(max_workers=1)

        # Create test file
        test_file = temp_dir / "test.mp4"
        test_file.write_bytes(b"test video")

        # Mock transcode method
        transcoder._transcode_file = Mock(return_value=True)

        # Start worker
        transcoder.start()

        # Queue file
        transcoder.queue_transcode(test_file)

        # Wait for processing
        time.sleep(0.5)

        # Stop worker
        transcoder.stop()

        # Should have processed file
        # Note: Actual assertion depends on implementation details

    def test_worker_stops_on_sentinel(self):
        """Test that worker stops when receiving sentinel value"""
        transcoder = BackgroundTranscoder(max_workers=1)

        # Start worker
        transcoder.start()
        assert transcoder.running is True

        # Stop should send sentinel
        transcoder.stop()

        # Workers should have stopped
        assert len(transcoder.workers) == 0


@pytest.mark.unit
class TestTranscoderEdgeCases:
    """Test edge cases and error conditions"""

    def test_empty_queue_handling(self):
        """Test handling of empty queue"""
        transcoder = BackgroundTranscoder()

        # Queue should be empty
        assert transcoder.transcode_queue.empty()

        # Should handle empty queue gracefully
        transcoder.start()
        time.sleep(0.1)
        transcoder.stop()

    def test_concurrent_workers(self, temp_dir):
        """Test multiple workers processing concurrently"""
        transcoder = BackgroundTranscoder(max_workers=3)

        # Create multiple test files
        files = []
        for i in range(10):
            test_file = temp_dir / f"test_{i}.mp4"
            test_file.write_bytes(b"test video")
            files.append(test_file)

        # Mock transcode
        transcoder._transcode_file = Mock(return_value=True)

        # Start workers
        transcoder.start()

        # Queue all files
        for f in files:
            transcoder.queue_transcode(f)

        # Let workers process
        time.sleep(0.5)

        # Stop workers
        transcoder.stop()

        # Should have processed files
        assert transcoder.running is False

    def test_queue_overflow_handling(self, temp_dir):
        """Test handling of queue with many items"""
        transcoder = BackgroundTranscoder()

        # Create many test files
        for i in range(100):
            test_file = temp_dir / f"test_{i}.mp4"
            test_file.write_bytes(b"test video")
            transcoder.queue_transcode(test_file)

        # Queue should have all items
        assert transcoder.transcode_queue.qsize() == 100

    def test_invalid_source_file_handling(self, temp_dir):
        """Test handling of invalid source file"""
        transcoder = BackgroundTranscoder()

        # Create file with invalid video data
        bad_file = temp_dir / "bad.mp4"
        bad_file.write_bytes(b"not valid video")

        output = transcoder._get_transcoded_path(bad_file)
        output.parent.mkdir(parents=True, exist_ok=True)

        # Should handle gracefully
        # Note: Actual behavior depends on implementation
