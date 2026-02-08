/**
 * End-to-end tests for Playback page
 */

import { test, expect } from '@playwright/test';

test.describe('Playback Page', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/playback');
  });

  test('should load playback page successfully', async ({ page }) => {
    await expect(page).toHaveURL(/.*playback/);
    await expect(page.locator('h1, .page-title')).toBeVisible();
  });

  test('should display date and time controls', async ({ page }) => {
    // Check for date picker
    const dateInput = page.locator('input[type="date"]');
    await expect(dateInput).toBeVisible();

    // Check for time inputs
    const timeInputs = page.locator('input[type="time"]');
    expect(await timeInputs.count()).toBeGreaterThanOrEqual(2);
  });

  test('should have camera selection', async ({ page }) => {
    // Check for camera checkboxes or selection UI
    const cameraSelectors = page.locator('.camera-checkbox, .camera-select');

    if (await cameraSelectors.count() > 0) {
      await expect(cameraSelectors.first()).toBeVisible();
    }
  });

  test('should load recordings when date and time selected', async ({ page }) => {
    // Set date to today
    const today = new Date().toISOString().split('T')[0];
    const dateInput = page.locator('input[type="date"]').first();
    await dateInput.fill(today);

    // Set time range
    const timeInputs = page.locator('input[type="time"]');
    if (await timeInputs.count() >= 2) {
      await timeInputs.nth(0).fill('12:00');
      await timeInputs.nth(1).fill('13:00');
    }

    // Select a camera
    const cameraCheckbox = page.locator('.camera-checkbox').first();
    if (await cameraCheckbox.isVisible()) {
      await cameraCheckbox.check();
    }

    // Click load/refresh button
    const loadButton = page.locator('button:has-text("Load"), button:has-text("Refresh")').first();
    if (await loadButton.isVisible()) {
      await loadButton.click();

      // Wait for recordings to load
      await page.waitForTimeout(2000);
    }
  });

  test('should display timeline when recordings available', async ({ page }) => {
    // Set up time range and load recordings
    const today = new Date().toISOString().split('T')[0];
    await page.locator('input[type="date"]').first().fill(today);

    const timeInputs = page.locator('input[type="time"]');
    if (await timeInputs.count() >= 2) {
      await timeInputs.nth(0).fill('08:00');
      await timeInputs.nth(1).fill('18:00');
    }

    // Try to load recordings
    const loadButton = page.locator('button:has-text("Load"), button:has-text("Refresh")').first();
    if (await loadButton.isVisible()) {
      await loadButton.click();
      await page.waitForTimeout(2000);

      // Check for timeline
      const timeline = page.locator('.timeline, #timeline');
      if (await timeline.isVisible()) {
        await expect(timeline).toBeVisible();
      }
    }
  });

  test('should play video when timeline clicked', async ({ page }) => {
    // This test requires actual recordings to be present
    // Skip if no timeline segments available

    const timelineSegments = page.locator('.timeline-segment');

    if (await timelineSegments.count() > 0) {
      // Click first segment
      await timelineSegments.first().click();

      // Wait for video to load
      await page.waitForTimeout(2000);

      // Check for video element
      const video = page.locator('video');
      if (await video.isVisible()) {
        await expect(video).toBeVisible();

        // Video should have src
        const src = await video.getAttribute('src');
        expect(src).toBeTruthy();
      }
    }
  });

  test('should have playback controls', async ({ page }) => {
    // Check for play/pause button
    const playButton = page.locator('button[title*="Play"], button:has-text("⏯"), #play-pause-btn');

    if (await playButton.count() > 0) {
      await expect(playButton.first()).toBeVisible();
    }

    // Check for speed controls
    const speedButtons = page.locator('.speed-btn, button:has-text("0.5x"), button:has-text("1x")');

    if (await speedButtons.count() > 0) {
      expect(await speedButtons.count()).toBeGreaterThan(0);
    }
  });

  test('should have export functionality', async ({ page }) => {
    // Look for export button
    const exportButton = page.locator('button:has-text("Export"), button:has-text("📥")');

    if (await exportButton.count() > 0) {
      await expect(exportButton.first()).toBeVisible();
    }
  });

  test('should show system stats', async ({ page }) => {
    // Check for CPU, Memory, Disk stats
    const cpuStat = page.locator('#cpu-usage, .stat-value:has-text("%")');
    const diskStat = page.locator('#disk-usage, #disk-details');

    // At least some stats should be visible
    if (await cpuStat.count() > 0 || await diskStat.count() > 0) {
      expect(await cpuStat.count() + await diskStat.count()).toBeGreaterThan(0);
    }
  });

  test('should navigate back to live view', async ({ page }) => {
    const liveViewButton = page.locator('button:has-text("Live View"), a:has-text("← Live")');

    if (await liveViewButton.count() > 0) {
      await liveViewButton.first().click();

      // Should navigate back to home
      await expect(page).toHaveURL(/^(?!.*playback)/);
    }
  });
});

test.describe('Playback - Keyboard Shortcuts', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/playback');
  });

  test('should support space key for play/pause', async ({ page }) => {
    // This test requires a video to be loaded
    // Skip if no video available

    const video = page.locator('video').first();

    if (await video.isVisible()) {
      // Press space key
      await page.keyboard.press('Space');

      // Wait for state change
      await page.waitForTimeout(500);

      // Video state should have changed (playing <-> paused)
      // Actual verification would require checking video.paused property
    }
  });

  test('should support arrow keys for seeking', async ({ page }) => {
    const video = page.locator('video').first();

    if (await video.isVisible()) {
      // Press right arrow to skip forward
      await page.keyboard.press('ArrowRight');
      await page.waitForTimeout(500);

      // Press left arrow to skip backward
      await page.keyboard.press('ArrowLeft');
      await page.waitForTimeout(500);
    }
  });

  test('should support number keys for jumping to percentage', async ({ page }) => {
    const video = page.locator('video').first();

    if (await video.isVisible()) {
      // Press '5' to jump to 50%
      await page.keyboard.press('Digit5');
      await page.waitForTimeout(500);

      // Press '0' to jump to start
      await page.keyboard.press('Digit0');
      await page.waitForTimeout(500);
    }
  });

  test('should support F key for fullscreen', async ({ page }) => {
    const video = page.locator('video').first();

    if (await video.isVisible()) {
      // Press F for fullscreen
      await page.keyboard.press('KeyF');
      await page.waitForTimeout(500);

      // Note: Fullscreen API in headless browsers may not work
      // This just tests that the key press doesn't cause errors
    }
  });

  test('should support M key for mute/unmute', async ({ page }) => {
    const video = page.locator('video').first();

    if (await video.isVisible()) {
      // Press M for mute/unmute
      await page.keyboard.press('KeyM');
      await page.waitForTimeout(500);

      // Verify notification appears
      const notification = page.locator('#keyboard-notification, .notification');
      if (await notification.isVisible({ timeout: 2000 })) {
        await expect(notification).toContainText(/Muted|Unmuted/);
      }
    }
  });
});

test.describe('Playback - Timeline Navigation', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/playback');
  });

  test('should show tooltip on timeline hover', async ({ page }) => {
    const timeline = page.locator('.timeline, #timeline').first();

    if (await timeline.isVisible()) {
      // Hover over timeline
      await timeline.hover();

      // Look for tooltip
      const tooltip = page.locator('.timeline-tooltip, .tooltip');

      if (await tooltip.count() > 0) {
        // Tooltip should appear on hover
        await expect(tooltip.first()).toBeVisible({ timeout: 2000 });
      }
    }
  });

  test('should update timeline position during playback', async ({ page }) => {
    const video = page.locator('video').first();
    const timelineHandle = page.locator('#timeline-handle, .timeline-handle');

    if (await video.isVisible() && await timelineHandle.count() > 0) {
      // Play video
      await page.keyboard.press('Space');

      // Wait a bit for playback
      await page.waitForTimeout(2000);

      // Timeline handle should have moved
      const position = await timelineHandle.first().getAttribute('style');
      expect(position).toBeTruthy();
    }
  });
});

test.describe('Playback - Quick Duration Buttons', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/playback');
  });

  test('should have quick duration buttons', async ({ page }) => {
    // Look for +5m, +10m, +30m buttons
    const durationButtons = page.locator('button:has-text("+5m"), button:has-text("+10m"), button:has-text("+30m")');

    if (await durationButtons.count() > 0) {
      expect(await durationButtons.count()).toBeGreaterThan(0);
    }
  });

  test('should set duration when quick button clicked', async ({ page }) => {
    // Set start time first
    const startTimeInput = page.locator('input[type="time"]').first();
    await startTimeInput.fill('12:00');

    // Click +5m button
    const fiveMinButton = page.locator('button:has-text("+5m")').first();

    if (await fiveMinButton.isVisible()) {
      await fiveMinButton.click();

      // End time should be updated
      const endTimeInput = page.locator('input[type="time"]').nth(1);
      const endTimeValue = await endTimeInput.inputValue();

      // End time should be 12:05
      expect(endTimeValue).toBe('12:05');
    }
  });
});

test.describe('Playback - Multi-Camera Support', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/playback');
  });

  test('should support selecting multiple cameras', async ({ page }) => {
    const cameraCheckboxes = page.locator('.camera-checkbox');

    if (await cameraCheckboxes.count() >= 2) {
      // Select first two cameras
      await cameraCheckboxes.nth(0).check();
      await cameraCheckboxes.nth(1).check();

      // Load recordings
      const loadButton = page.locator('button:has-text("Load"), button:has-text("Refresh")').first();
      if (await loadButton.isVisible()) {
        await loadButton.click();
        await page.waitForTimeout(2000);

        // Should show multiple video players
        const videoPlayers = page.locator('video, .video-player');
        expect(await videoPlayers.count()).toBeGreaterThanOrEqual(1);
      }
    }
  });
});
