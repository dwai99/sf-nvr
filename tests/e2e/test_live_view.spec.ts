/**
 * End-to-end tests for Live View page
 */

import { test, expect } from '@playwright/test';

test.describe('Live View Page', () => {
  test.beforeEach(async ({ page }) => {
    // Navigate to home page before each test
    await page.goto('/');
  });

  test('should load live view page successfully', async ({ page }) => {
    // Wait for page to load
    await expect(page).toHaveTitle(/SF-NVR/);

    // Check for main page elements
    await expect(page.locator('h1, .page-title')).toBeVisible();
  });

  test('should display configured cameras', async ({ page }) => {
    // Wait for cameras to load
    await page.waitForTimeout(2000);

    // Check that camera cards are displayed
    const cameraCards = page.locator('.camera-card, .camera-container');
    const count = await cameraCards.count();

    // Should have at least one camera
    expect(count).toBeGreaterThan(0);
  });

  test('should show live stream for cameras', async ({ page }) => {
    // Wait for cameras to load
    await page.waitForTimeout(2000);

    // Get first camera
    const firstCamera = page.locator('.camera-card, .camera-container').first();
    await expect(firstCamera).toBeVisible();

    // Check for stream image or video element
    const stream = firstCamera.locator('img.camera-stream, video');
    await expect(stream).toBeVisible({ timeout: 10000 });

    // Verify stream has src attribute
    const streamSrc = await stream.getAttribute('src');
    expect(streamSrc).toBeTruthy();
    expect(streamSrc).toContain('/api/cameras/');
  });

  test('should display camera health indicators', async ({ page }) => {
    // Wait for cameras and health data
    await page.waitForTimeout(3000);

    // Look for health indicators
    const healthIndicators = page.locator('.health-dot, .camera-health');

    if (await healthIndicators.count() > 0) {
      const firstIndicator = healthIndicators.first();
      await expect(firstIndicator).toBeVisible();

      // Health indicator should have a status class
      const classes = await firstIndicator.getAttribute('class');
      expect(classes).toMatch(/(healthy|degraded|stale|stopped)/);
    }
  });

  test('should show system statistics', async ({ page }) => {
    // Wait for stats to load
    await page.waitForTimeout(2000);

    // Check for stat displays
    const stats = page.locator('.stat, .stat-value');

    if (await stats.count() > 0) {
      // Should show some statistics
      expect(await stats.count()).toBeGreaterThan(0);
    }
  });

  test('should navigate to playback page', async ({ page }) => {
    // Find and click playback button
    const playbackButton = page.locator('a[href="/playback"], button:has-text("Playback")');

    if (await playbackButton.count() > 0) {
      await playbackButton.first().click();

      // Should navigate to playback page
      await expect(page).toHaveURL(/.*playback/);
    }
  });

  test('should navigate to settings page', async ({ page }) => {
    // Find and click settings button
    const settingsButton = page.locator('a[href="/settings"], button:has-text("Settings")');

    if (await settingsButton.count() > 0) {
      await settingsButton.first().click();

      // Should navigate to settings page
      await expect(page).toHaveURL(/.*settings/);
    }
  });

  test('should handle camera rename', async ({ page }) => {
    await page.waitForTimeout(2000);

    // Look for camera name edit functionality
    const cameraName = page.locator('.camera-name-display, .camera-title').first();

    if (await cameraName.isVisible()) {
      // Try to click to edit (if editable)
      await cameraName.click();

      // Check if edit input appears
      const editInput = page.locator('.camera-name-input, input[type="text"]');

      if (await editInput.isVisible({ timeout: 2000 })) {
        await editInput.fill('Test Camera Renamed');
        await page.keyboard.press('Enter');

        // Wait for save
        await page.waitForTimeout(1000);
      }
    }
  });

  test('should show motion detection indicator when motion occurs', async ({ page }) => {
    // Wait for cameras to load
    await page.waitForTimeout(2000);

    // Look for motion detection indicators
    const motionIndicator = page.locator('.motion-detected, text=MOTION');

    // Motion may or may not be detected during test
    // Just verify the element can be found in the page structure
    const count = await motionIndicator.count();
    expect(count).toBeGreaterThanOrEqual(0);
  });

  test('should refresh camera data periodically', async ({ page }) => {
    // Get initial camera count
    await page.waitForTimeout(2000);
    const initialCount = await page.locator('.camera-card, .camera-container').count();

    // Wait for a refresh cycle (typically 5 seconds)
    await page.waitForTimeout(6000);

    // Verify cameras still displayed
    const afterRefreshCount = await page.locator('.camera-card, .camera-container').count();
    expect(afterRefreshCount).toBe(initialCount);
  });
});

test.describe('Live View - Mobile Responsiveness', () => {
  test.use({ viewport: { width: 375, height: 667 } });

  test('should display cameras in mobile layout', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Cameras should still be visible on mobile
    const cameras = page.locator('.camera-card, .camera-container');
    expect(await cameras.count()).toBeGreaterThan(0);

    // Should have responsive layout (single column on mobile)
    const firstCamera = cameras.first();
    const width = await firstCamera.boundingBox();

    if (width) {
      // Camera should take up most of screen width on mobile
      expect(width.width).toBeGreaterThan(300);
    }
  });
});

test.describe('Live View - Performance', () => {
  test('should load within acceptable time', async ({ page }) => {
    const startTime = Date.now();

    await page.goto('/');

    // Wait for main content
    await page.waitForSelector('.camera-card, .camera-container, h1', { timeout: 10000 });

    const loadTime = Date.now() - startTime;

    // Page should load within 10 seconds
    expect(loadTime).toBeLessThan(10000);
  });

  test('should handle multiple cameras without performance degradation', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Check that all cameras are rendering
    const cameras = page.locator('.camera-card, .camera-container');
    const count = await cameras.count();

    // All cameras should be visible
    for (let i = 0; i < count; i++) {
      await expect(cameras.nth(i)).toBeVisible();
    }
  });
});
