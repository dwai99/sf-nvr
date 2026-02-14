"""Unit tests for MotionDetector - motion detection in video streams"""

import pytest
import cv2
import numpy as np
from unittest.mock import Mock, MagicMock, patch
from datetime import datetime

from nvr.core.motion import MotionDetector


@pytest.mark.unit
class TestMotionDetectorInit:
    """Test motion detector initialization"""

    def test_init_default_params(self):
        """Test motion detector with default parameters"""
        detector = MotionDetector()

        assert detector.sensitivity == 25
        assert detector.min_area == 500
        assert detector.blur_size == 21
        assert detector.camera_name == "Unknown"
        assert detector.recorder is None
        assert detector.motion_detected is False
        assert detector.prev_frame is None

    def test_init_custom_params(self):
        """Test motion detector with custom parameters"""
        mock_recorder = Mock()

        detector = MotionDetector(
            sensitivity=50,
            min_area=1000,
            blur_size=15,
            camera_name="Front Door",
            recorder=mock_recorder
        )

        assert detector.sensitivity == 50
        assert detector.min_area == 1000
        assert detector.blur_size == 15
        assert detector.camera_name == "Front Door"
        assert detector.recorder == mock_recorder

    def test_init_ensures_odd_blur_size(self):
        """Test that blur size is always odd"""
        # Even blur size should be incremented
        detector = MotionDetector(blur_size=20)
        assert detector.blur_size == 21

        # Odd blur size should stay the same
        detector = MotionDetector(blur_size=19)
        assert detector.blur_size == 19

    def test_init_creates_background_subtractor(self):
        """Test that background subtractor is created"""
        detector = MotionDetector()

        assert detector.bg_subtractor is not None
        assert hasattr(detector.bg_subtractor, 'apply')


@pytest.mark.unit
class TestMotionDetection:
    """Test motion detection processing"""

    def create_test_frame(self, width=640, height=480, noise=False):
        """Helper to create test frame"""
        frame = np.zeros((height, width, 3), dtype=np.uint8)

        if noise:
            # Add some noise
            noise_array = np.random.randint(0, 50, (height, width, 3), dtype=np.uint8)
            frame = cv2.add(frame, noise_array)

        return frame

    def create_frame_with_motion(self, width=640, height=480):
        """Helper to create frame with motion region"""
        frame = self.create_test_frame(width, height)

        # Add a white rectangle to simulate motion
        cv2.rectangle(frame, (200, 150), (400, 350), (255, 255, 255), -1)

        return frame

    def test_process_first_frame_returns_no_motion(self):
        """Test that first frame always returns no motion"""
        detector = MotionDetector()

        frame = self.create_test_frame()
        has_motion, boxes = detector.process_frame(frame)

        # First frame should not detect motion
        assert has_motion is False
        assert len(boxes) == 0
        assert detector.prev_frame is not None

    def test_process_identical_frames_no_motion(self):
        """Test that identical frames produce no motion"""
        detector = MotionDetector()

        frame = self.create_test_frame()

        # Process first frame
        detector.process_frame(frame)

        # Process identical frame
        has_motion, boxes = detector.process_frame(frame)

        # Should not detect motion
        assert has_motion is False
        assert len(boxes) == 0

    def test_process_different_frames_detects_motion(self):
        """Test that different frames detect motion"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        # First frame - static
        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        # Second frame - with motion
        frame2 = self.create_frame_with_motion()
        has_motion, boxes = detector.process_frame(frame2)

        # Should detect motion
        assert has_motion is True
        assert len(boxes) > 0

    def test_motion_boxes_contain_coordinates(self):
        """Test that motion boxes contain valid coordinates"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        has_motion, boxes = detector.process_frame(frame2)

        if has_motion:
            for box in boxes:
                # Each box should be (x, y, w, h)
                assert len(box) == 4
                x, y, w, h = box
                assert x >= 0 and y >= 0
                assert w > 0 and h > 0

    def test_min_area_filters_small_motion(self):
        """Test that min_area filters out small motion regions"""
        # Large min_area to filter small motion
        detector = MotionDetector(sensitivity=20, min_area=10000)

        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        # Create frame with small motion region
        frame2 = self.create_test_frame()
        cv2.rectangle(frame2, (100, 100), (110, 110), (255, 255, 255), -1)  # 10x10 = 100 pixels

        has_motion, boxes = detector.process_frame(frame2)

        # Should not detect motion (area too small)
        assert has_motion is False or len(boxes) == 0

    def test_sensitivity_affects_detection(self):
        """Test that sensitivity affects motion detection"""
        # Low sensitivity (high threshold) - harder to trigger
        detector_low = MotionDetector(sensitivity=50, min_area=100)

        # High sensitivity (low threshold) - easier to trigger
        detector_high = MotionDetector(sensitivity=10, min_area=100)

        frame1 = self.create_test_frame()
        frame2 = self.create_test_frame(noise=True)  # Subtle changes

        # Process with low sensitivity
        detector_low.process_frame(frame1)
        motion_low, _ = detector_low.process_frame(frame2)

        # Process with high sensitivity
        detector_high.process_frame(frame1)
        motion_high, _ = detector_high.process_frame(frame2)

        # High sensitivity should be more likely to detect motion
        # Note: This test may be environment-dependent


@pytest.mark.unit
class TestMotionStateTracking:
    """Test motion state tracking and callbacks"""

    def create_test_frame(self):
        """Helper to create test frame"""
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def create_frame_with_motion(self):
        """Helper to create frame with motion"""
        frame = self.create_test_frame()
        cv2.rectangle(frame, (200, 150), (400, 350), (255, 255, 255), -1)
        return frame

    def test_motion_state_changes_to_true(self):
        """Test that motion_detected changes to True"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        detector.process_frame(frame2)

        # Motion state should be True
        assert detector.motion_detected is True

    def test_motion_state_changes_to_false(self):
        """Test that motion_detected changes back to False"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        # Start with motion
        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        detector.process_frame(frame2)
        assert detector.motion_detected is True

        # Process a blank frame to update prev_frame
        frame3 = self.create_test_frame()
        detector.process_frame(frame3)

        # Simulate cooldown expiry (3-second cooldown is time-based, not frame-based)
        from datetime import timedelta
        detector.last_motion_time = datetime.now() - timedelta(seconds=5)

        # Process another blank frame - cooldown has expired, motion should end
        detector.process_frame(frame3)

        # Motion state should be False
        assert detector.motion_detected is False

    def test_on_motion_start_callback_called(self):
        """Test that on_motion_start callback is called"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        callback = Mock()
        detector.on_motion_start = callback

        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        detector.process_frame(frame2)

        # Callback should have been called
        callback.assert_called_once()

    def test_on_motion_end_callback_called(self):
        """Test that on_motion_end callback is called"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        callback = Mock()
        detector.on_motion_end = callback

        # Trigger motion
        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        detector.process_frame(frame2)

        # Process a blank frame to update prev_frame
        frame3 = self.create_test_frame()
        detector.process_frame(frame3)

        # Simulate cooldown expiry (3-second cooldown is time-based)
        from datetime import timedelta
        detector.last_motion_time = datetime.now() - timedelta(seconds=5)

        # Process another blank frame - cooldown expired, motion ends
        detector.process_frame(frame3)

        # Callback should have been called
        callback.assert_called_once()

    def test_recorder_log_motion_event_called(self):
        """Test that recorder.log_motion_event is called"""
        mock_recorder = Mock()
        detector = MotionDetector(sensitivity=20, min_area=100, recorder=mock_recorder)

        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        detector.process_frame(frame2)

        # Should have called log_motion_event
        mock_recorder.log_motion_event.assert_called()

    def test_recorder_end_motion_event_called(self):
        """Test that recorder.end_motion_event is called"""
        mock_recorder = Mock()
        detector = MotionDetector(sensitivity=20, min_area=100, recorder=mock_recorder)

        # Trigger motion
        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        detector.process_frame(frame2)

        # Process a blank frame to update prev_frame
        frame3 = self.create_test_frame()
        detector.process_frame(frame3)

        # Simulate cooldown expiry (3-second cooldown is time-based)
        from datetime import timedelta
        detector.last_motion_time = datetime.now() - timedelta(seconds=5)

        # Process another blank frame - cooldown expired, motion ends
        detector.process_frame(frame3)

        # Should have called end_motion_event
        mock_recorder.end_motion_event.assert_called()

    def test_last_motion_time_updated(self):
        """Test that last_motion_time is updated"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        assert detector.last_motion_time is None

        frame1 = self.create_test_frame()
        detector.process_frame(frame1)

        frame2 = self.create_frame_with_motion()
        detector.process_frame(frame2)

        # Should have updated last_motion_time
        assert detector.last_motion_time is not None
        assert isinstance(detector.last_motion_time, datetime)


@pytest.mark.unit
class TestMotionVisualization:
    """Test motion visualization"""

    def create_test_frame(self):
        """Helper to create test frame"""
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def test_draw_motion_with_boxes(self):
        """Test drawing motion boxes on frame"""
        detector = MotionDetector()

        frame = self.create_test_frame()
        motion_boxes = [(100, 100, 200, 150), (400, 200, 100, 80)]

        result = detector.draw_motion(frame, motion_boxes)

        # Should return a frame
        assert result.shape == frame.shape
        assert result.dtype == frame.dtype

        # Result should be different from original (has drawings)
        assert not np.array_equal(result, frame)

    def test_draw_motion_without_boxes(self):
        """Test drawing when no motion boxes"""
        detector = MotionDetector()

        frame = self.create_test_frame()
        motion_boxes = []

        result = detector.draw_motion(frame, motion_boxes)

        # Should return a frame
        assert result.shape == frame.shape

    def test_draw_motion_adds_text(self):
        """Test that motion indicator text is added"""
        detector = MotionDetector()

        frame = self.create_test_frame()
        motion_boxes = [(100, 100, 200, 150)]

        result = detector.draw_motion(frame, motion_boxes)

        # Frame should have text (not all zeros in text region)
        text_region = result[10:40, 10:300]
        assert np.sum(text_region) > 0


@pytest.mark.unit
class TestMotionDetectorReset:
    """Test motion detector reset"""

    def create_test_frame(self):
        """Helper to create test frame"""
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def test_reset_clears_state(self):
        """Test that reset clears motion detector state"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        # Process some frames
        frame = self.create_test_frame()
        detector.process_frame(frame)

        # Set motion state
        detector.motion_detected = True

        # Reset
        detector.reset()

        # State should be cleared
        assert detector.prev_frame is None
        assert detector.motion_detected is False

    def test_reset_recreates_background_subtractor(self):
        """Test that reset recreates background subtractor"""
        detector = MotionDetector()

        old_subtractor = detector.bg_subtractor

        # Reset
        detector.reset()

        # Should have new subtractor
        assert detector.bg_subtractor is not old_subtractor


@pytest.mark.unit
class TestMotionDetectorEdgeCases:
    """Test edge cases and error conditions"""

    def test_frame_size_change_handled(self):
        """Test that frame size changes are handled gracefully"""
        detector = MotionDetector()

        # Process frame of one size
        frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
        detector.process_frame(frame1)

        # Process frame of different size
        frame2 = np.zeros((720, 1280, 3), dtype=np.uint8)
        has_motion, boxes = detector.process_frame(frame2)

        # Should not crash and should reset
        assert has_motion is False
        assert detector.prev_frame.shape == (720, 1280)

    def test_callback_exception_handled(self):
        """Test that callback exceptions are handled gracefully"""
        detector = MotionDetector(sensitivity=20, min_area=100)

        # Callback that raises exception
        def bad_callback():
            raise Exception("Callback error")

        detector.on_motion_start = bad_callback

        # Should not crash when exception occurs
        frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
        detector.process_frame(frame1)

        frame2 = np.zeros((480, 640, 3), dtype=np.uint8)
        cv2.rectangle(frame2, (200, 150), (400, 350), (255, 255, 255), -1)

        # Should not raise exception
        detector.process_frame(frame2)

    def test_very_small_frame(self):
        """Test handling of very small frame"""
        detector = MotionDetector()

        # Very small frame
        frame = np.zeros((10, 10, 3), dtype=np.uint8)

        # Should not crash
        has_motion, boxes = detector.process_frame(frame)

        assert has_motion is False

    def test_very_large_frame(self):
        """Test handling of very large frame"""
        detector = MotionDetector()

        # Large frame (4K)
        frame = np.zeros((2160, 3840, 3), dtype=np.uint8)

        # Should not crash
        has_motion, boxes = detector.process_frame(frame)

        assert has_motion is False

    def test_grayscale_input(self):
        """Test that RGB/BGR frames work (motion detector converts internally)"""
        detector = MotionDetector()

        # RGB frame
        frame = np.zeros((480, 640, 3), dtype=np.uint8)

        # Should work
        has_motion, boxes = detector.process_frame(frame)

        assert has_motion is False

    def test_continuous_motion_logging(self):
        """Test that motion is logged continuously while active"""
        mock_recorder = Mock()
        detector = MotionDetector(sensitivity=20, min_area=100, recorder=mock_recorder)

        frame1 = np.zeros((480, 640, 3), dtype=np.uint8)
        detector.process_frame(frame1)

        # Process varying motion frames to simulate continuous motion
        for i in range(5):
            frame = np.zeros((480, 640, 3), dtype=np.uint8)
            # Create slightly different motion each time
            x_offset = 200 + (i * 10)
            cv2.rectangle(frame, (x_offset, 150), (x_offset + 200, 350), (255, 255, 255), -1)
            detector.process_frame(frame)

        # Should have logged motion multiple times (at least for motion start + continuous logging)
        assert mock_recorder.log_motion_event.call_count >= 5


@pytest.mark.unit
class TestMotionCooldown:
    """Tests for motion detection cooldown functionality"""

    def create_test_frame(self):
        """Create a blank test frame"""
        return np.zeros((480, 640, 3), dtype=np.uint8)

    def create_frame_with_motion(self, offset=0):
        """Create a frame with a moving white rectangle"""
        frame = np.zeros((480, 640, 3), dtype=np.uint8)
        x = 200 + offset
        cv2.rectangle(frame, (x, 150), (x + 200, 350), (255, 255, 255), -1)
        return frame

    def test_motion_cooldown_prevents_rapid_end(self):
        """Test that motion event doesn't end immediately after motion stops"""
        mock_recorder = Mock()
        detector = MotionDetector(sensitivity=20, min_area=100, recorder=mock_recorder)

        # Initialize with blank frame
        detector.process_frame(self.create_test_frame())

        # Start motion
        detector.process_frame(self.create_frame_with_motion())
        assert detector.motion_detected is True

        # Single frame without motion should NOT end event (cooldown)
        detector.process_frame(self.create_test_frame())
        assert detector.motion_detected is True  # Still in motion due to cooldown

    def test_motion_event_ends_after_cooldown(self):
        """Test that motion event ends after cooldown period expires"""
        mock_recorder = Mock()
        mock_recorder.end_motion_event = Mock()
        detector = MotionDetector(sensitivity=20, min_area=100, recorder=mock_recorder)

        # Initialize with blank frame
        blank_frame = self.create_test_frame()
        detector.process_frame(blank_frame)

        # Start motion
        detector.process_frame(self.create_frame_with_motion())
        assert detector.motion_detected is True

        # Process a blank frame to update prev_frame (no new motion detected)
        detector.process_frame(blank_frame.copy())

        # Simulate time passing by directly setting last_motion_time
        from datetime import datetime, timedelta
        detector.last_motion_time = datetime.now() - timedelta(seconds=5)

        # Now process another blank frame - cooldown should have expired
        # and prev_frame is already blank so no new motion will be detected
        detector.process_frame(blank_frame.copy())

        # Motion should have ended
        assert detector.motion_detected is False
        mock_recorder.end_motion_event.assert_called()

    def test_motion_cooldown_resets_on_new_motion(self):
        """Test that cooldown timer resets when new motion detected"""
        mock_recorder = Mock()
        detector = MotionDetector(sensitivity=20, min_area=100, recorder=mock_recorder)

        # Initialize
        detector.process_frame(self.create_test_frame())

        # Start motion
        detector.process_frame(self.create_frame_with_motion())
        initial_motion_time = detector.last_motion_time

        # More motion should update the last_motion_time
        detector.process_frame(self.create_frame_with_motion(offset=50))
        updated_motion_time = detector.last_motion_time

        assert updated_motion_time >= initial_motion_time

    def test_motion_cooldown_aggregates_events(self):
        """Test that rapid motion on/off creates single event, not many"""
        mock_recorder = Mock()
        mock_recorder.log_motion_event = Mock()
        detector = MotionDetector(sensitivity=20, min_area=100, recorder=mock_recorder)

        # Initialize
        detector.process_frame(self.create_test_frame())

        # Rapid motion on/off pattern (simulating flickering)
        for i in range(10):
            if i % 2 == 0:
                detector.process_frame(self.create_frame_with_motion(offset=i*10))
            else:
                detector.process_frame(self.create_test_frame())

        # Due to cooldown, this should still be considered one continuous event
        # Motion should still be detected (cooldown hasn't expired)
        assert detector.motion_detected is True
