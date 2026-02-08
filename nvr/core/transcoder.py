"""Background video transcoder for instant playback"""

import subprocess
import threading
import queue
import logging
from pathlib import Path
from typing import Optional, Tuple, List

logger = logging.getLogger(__name__)


class BackgroundTranscoder:
    """Transcodes recorded segments to H.264 in background for instant playback"""

    def __init__(self, max_workers: int = 2, replace_original: bool = True, preferred_encoder: str = 'auto'):
        """
        Initialize background transcoder

        Args:
            max_workers: Maximum number of concurrent transcode operations
            replace_original: If True, delete original file after successful transcode (saves disk space)
            preferred_encoder: Preferred encoder ('auto', 'nvenc', 'qsv', 'videotoolbox', 'amf', or 'x264')
        """
        self.transcode_queue = queue.Queue()
        self.max_workers = max_workers
        self.replace_original = replace_original
        self.workers = []
        self.running = False
        self.preferred_encoder = preferred_encoder

        # Detect best available encoder on startup (respecting preference)
        self.encoder, self.encoder_options = self._detect_best_encoder()
        logger.info(f"Using encoder: {self.encoder} with options: {self.encoder_options}")

    def start(self):
        """Start transcoder worker threads"""
        if self.running:
            return

        self.running = True
        for i in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"Transcoder-{i}",
                daemon=True
            )
            worker.start()
            self.workers.append(worker)

        logger.info(f"Started {self.max_workers} transcoder workers")

    def stop(self):
        """Stop transcoder workers"""
        self.running = False

        # Add sentinel values to wake up workers
        for _ in range(self.max_workers):
            self.transcode_queue.put(None)

        # Wait for workers to finish
        for worker in self.workers:
            worker.join(timeout=5)

        self.workers.clear()
        logger.info("Stopped transcoder workers")

    def queue_transcode(self, source_path: Path, priority: bool = False):
        """
        Queue a video file for transcoding

        Args:
            source_path: Path to the source video file
            priority: If True, add to front of queue
        """
        if not source_path.exists():
            logger.warning(f"Cannot transcode non-existent file: {source_path}")
            return

        # Check if already transcoded
        transcoded_path = self._get_transcoded_path(source_path)
        if transcoded_path.exists():
            logger.debug(f"Already transcoded: {source_path.name}")
            return

        # Queue for transcoding
        if priority:
            # For priority items, we'd need a PriorityQueue - for now just log
            logger.info(f"Priority transcode queued: {source_path.name}")
        else:
            logger.info(f"Transcode queued: {source_path.name}")

        self.transcode_queue.put(source_path)

    def _detect_best_encoder(self) -> Tuple[str, List[str]]:
        """
        Detect the best available H.264 encoder (GPU or CPU)
        Respects preferred_encoder configuration

        Returns:
            Tuple of (encoder_name, encoder_options)
        """
        # Encoder preference mapping
        encoder_map = {
            'nvenc': 'h264_nvenc',
            'qsv': 'h264_qsv',
            'videotoolbox': 'h264_videotoolbox',
            'amf': 'h264_amf',
            'x264': 'libx264'
        }

        encoders = [
            # NVIDIA NVENC (fastest, excellent quality)
            ('h264_nvenc', ['-preset', 'fast', '-rc', 'vbr', '-cq', '23', '-b:v', '2M', '-maxrate', '4M']),
            # Intel QuickSync (very fast, good quality)
            ('h264_qsv', ['-preset', 'fast', '-global_quality', '23']),
            # Apple VideoToolbox (fast on Mac, good quality)
            ('h264_videotoolbox', ['-b:v', '2M', '-maxrate', '4M']),
            # AMD AMF (fast, good quality - less common)
            ('h264_amf', ['-quality', 'balanced', '-rc', 'vbr_peak', '-qmin', '18', '-qmax', '28']),
            # CPU fallback (slowest but universally available)
            ('libx264', ['-preset', 'veryfast', '-crf', '23'])
        ]

        # If user specified a preference, try it first
        if self.preferred_encoder != 'auto' and self.preferred_encoder in encoder_map:
            preferred = encoder_map[self.preferred_encoder]
            logger.info(f"User prefers {preferred} encoder, testing availability...")

            # Find the encoder configuration
            for encoder, options in encoders:
                if encoder == preferred and self._test_encoder(encoder):
                    logger.info(f"Using preferred encoder: {encoder}")
                    return encoder, options

            logger.warning(f"Preferred encoder {preferred} not available, falling back to auto-detection")

        # Auto-detection: try encoders in order of preference
        for encoder, options in encoders:
            if self._test_encoder(encoder):
                return encoder, options

        # Should never reach here since libx264 is always available
        logger.warning("No encoder found, using libx264 as last resort")
        return 'libx264', ['-preset', 'veryfast', '-crf', '23']

    def _test_encoder(self, encoder: str) -> bool:
        """
        Test if an encoder is available and functional in ffmpeg

        Args:
            encoder: Encoder name to test (e.g., 'h264_nvenc')

        Returns:
            True if encoder is available and can actually encode
        """
        try:
            # First check if encoder exists in ffmpeg
            result = subprocess.run(
                ['ffmpeg', '-hide_banner', '-encoders'],
                capture_output=True,
                timeout=2,
                text=True
            )

            if encoder not in result.stdout:
                logger.debug(f"Encoder {encoder} not found in ffmpeg build")
                return False

            # Test actual encoding with a tiny test (1 frame, 64x64)
            # This catches cases where encoder is listed but hardware unavailable
            test_result = subprocess.run(
                [
                    'ffmpeg', '-hide_banner', '-loglevel', 'error',
                    '-f', 'lavfi', '-i', 'color=c=black:s=64x64:d=0.1',  # Tiny black frame
                    '-c:v', encoder,
                    '-f', 'null', '-'  # Don't write output
                ],
                capture_output=True,
                timeout=3,
                text=True
            )

            if test_result.returncode == 0:
                logger.info(f"Encoder {encoder} is available and functional")
                return True
            else:
                logger.debug(f"Encoder {encoder} failed test encode: {test_result.stderr[:200]}")
                return False

        except (subprocess.TimeoutExpired, FileNotFoundError, Exception) as e:
            logger.debug(f"Failed to test encoder {encoder}: {e}")
            return False

    def _worker_loop(self):
        """Worker thread that processes transcode queue"""
        while self.running:
            try:
                # Get next file to transcode (with timeout to check running flag)
                source_path = self.transcode_queue.get(timeout=1)

                # Sentinel value to stop worker
                if source_path is None:
                    break

                # Perform transcode
                self._transcode_file(source_path)

                self.transcode_queue.task_done()

            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Error in transcoder worker: {e}")

    def _transcode_file(self, source_path: Path):
        """
        Transcode a single file to H.264

        Args:
            source_path: Path to source video file
        """
        transcoded_path = self._get_transcoded_path(source_path)

        # Skip if already exists
        if transcoded_path.exists():
            logger.debug(f"Skipping already transcoded: {source_path.name}")
            return

        logger.info(f"Transcoding: {source_path.name} using {self.encoder}")

        try:
            # Build ffmpeg command with detected encoder
            cmd = [
                'ffmpeg',
                '-i', str(source_path),
                '-c:v', self.encoder,   # Use detected encoder (GPU or CPU)
                *self.encoder_options,  # Encoder-specific options
                '-c:a', 'aac',          # AAC audio codec (if any audio)
                '-movflags', '+faststart',  # Enable progressive streaming
                '-y',                   # Overwrite if exists
                str(transcoded_path)
            ]

            result = subprocess.run(
                cmd,
                capture_output=True,
                timeout=300  # 5 minute timeout per file
            )

            if result.returncode == 0:
                logger.info(f"Transcoded successfully: {source_path.name} -> {transcoded_path.name}")

                # Replace original with transcoded version to save disk space
                if self.replace_original:
                    try:
                        # Get file sizes for logging
                        original_size = source_path.stat().st_size / (1024 * 1024)  # MB
                        transcoded_size = transcoded_path.stat().st_size / (1024 * 1024)  # MB
                        savings = original_size - transcoded_size

                        # Delete original file
                        source_path.unlink()

                        # Rename transcoded file to original name
                        transcoded_path.rename(source_path)

                        logger.info(f"Replaced original with transcoded version. Saved {savings:.1f}MB ({original_size:.1f}MB -> {transcoded_size:.1f}MB)")
                    except Exception as e:
                        logger.error(f"Failed to replace original file {source_path.name}: {e}")
            else:
                error_msg = result.stderr.decode('utf-8', errors='ignore')[-500:]
                logger.error(f"Transcode failed for {source_path.name}: {error_msg}")

                # Remove partial file if exists
                if transcoded_path.exists():
                    transcoded_path.unlink()

        except subprocess.TimeoutExpired:
            logger.error(f"Transcode timeout for {source_path.name}")
            if transcoded_path.exists():
                transcoded_path.unlink()
        except Exception as e:
            logger.error(f"Transcode error for {source_path.name}: {e}")
            if transcoded_path.exists():
                transcoded_path.unlink()

    def _get_transcoded_path(self, source_path: Path) -> Path:
        """
        Get path for transcoded version of file

        Args:
            source_path: Path to original file

        Returns:
            Path where transcoded file should be stored
        """
        # Store transcoded files in same directory with _h264 suffix
        return source_path.parent / f"{source_path.stem}_h264{source_path.suffix}"


# Global transcoder instance
_transcoder: Optional[BackgroundTranscoder] = None


def get_transcoder() -> BackgroundTranscoder:
    """Get or create global transcoder instance with config-based settings"""
    global _transcoder
    if _transcoder is None:
        # Import config here to avoid circular imports
        from nvr.core.config import config

        # Read transcoder configuration
        max_workers = config.get('transcoder.max_workers', 2)
        replace_original = config.get('transcoder.replace_original', True)
        preferred_encoder = config.get('transcoder.preferred_encoder', 'auto')

        _transcoder = BackgroundTranscoder(
            max_workers=max_workers,
            replace_original=replace_original,
            preferred_encoder=preferred_encoder
        )
        _transcoder.start()
        logger.info(f"Transcoder started with {max_workers} workers, preferred encoder: {preferred_encoder}")
    return _transcoder


def shutdown_transcoder():
    """Shutdown global transcoder instance"""
    global _transcoder
    if _transcoder is not None:
        _transcoder.stop()
        _transcoder = None
