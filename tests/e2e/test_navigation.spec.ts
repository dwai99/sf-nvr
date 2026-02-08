/**
 * Tests for page navigation with active camera streams
 */

import { test, expect } from '@playwright/test';

test.describe('Navigation with Active Streams', () => {
  test('should navigate to playback from MJPEG mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Verify streams are loading
    const streams = await page.locator('img.camera-stream[src*="/live"]').count();
    console.log(`Active MJPEG streams: ${streams}`);

    // Click Playback link
    await page.locator('a[href="/playback"]').click();

    // Should navigate to playback page
    await expect(page).toHaveURL(/.*playback/, { timeout: 10000 });
  });

  test('should navigate to playback from WebSocket mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Switch to WebSocket mode
    await page.locator('#mode-websocket').click();

    // Wait for WebSocket mode to be active and canvases to render
    await expect(page.locator('#mode-websocket')).toHaveClass(/active/);
    await page.waitForTimeout(3000);

    // Verify we're in WebSocket mode (canvases should exist)
    const canvasCount = await page.locator('canvas.camera-stream').count();
    console.log(`Canvas elements (WebSocket mode): ${canvasCount}`);
    expect(canvasCount).toBeGreaterThan(0);

    // Click Playback link
    await page.locator('a[href="/playback"]').click();

    // Should navigate to playback page
    await expect(page).toHaveURL(/.*playback/, { timeout: 10000 });
  });

  test('should navigate to settings from MJPEG mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);

    // Click Settings link
    await page.locator('a[href="/settings"]').click();

    // Should navigate to settings page
    await expect(page).toHaveURL(/.*settings/, { timeout: 10000 });
  });

  test('should navigate to settings from WebSocket mode', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Switch to WebSocket mode
    await page.locator('#mode-websocket').click();
    await page.waitForTimeout(3000);

    // Click Settings link
    await page.locator('a[href="/settings"]').click();

    // Should navigate to settings page
    await expect(page).toHaveURL(/.*settings/, { timeout: 10000 });
  });

  test('should navigate even with fullscreen open', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Open fullscreen
    await page.locator('.camera-video').first().click();
    await page.waitForTimeout(1000);

    // Close fullscreen
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    // Navigate to playback
    await page.locator('a[href="/playback"]').click();

    // Should navigate
    await expect(page).toHaveURL(/.*playback/, { timeout: 10000 });
  });

  test('should navigate with WebSocket fullscreen open then closed', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(2000);

    // Switch to WebSocket mode
    await page.locator('#mode-websocket').click();
    await page.waitForTimeout(3000);

    // Open fullscreen
    await page.locator('.camera-video').first().click();
    await page.waitForTimeout(2000);

    // Close fullscreen
    await page.keyboard.press('Escape');
    await page.waitForTimeout(500);

    // Navigate to playback
    await page.locator('a[href="/playback"]').click();

    // Should navigate
    await expect(page).toHaveURL(/.*playback/, { timeout: 10000 });
  });
});

test.describe('Navigation - Edge Cases', () => {
  test('should navigate when streams are still loading', async ({ page }) => {
    await page.goto('/');
    // Don't wait for streams to fully load
    await page.waitForTimeout(500);

    // Click Playback immediately
    await page.locator('a[href="/playback"]').click();

    // Should still navigate
    await expect(page).toHaveURL(/.*playback/, { timeout: 10000 });
  });

  test('should handle rapid navigation', async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(1000);

    // Navigate to playback
    await page.locator('a[href="/playback"]').click();
    await expect(page).toHaveURL(/.*playback/, { timeout: 10000 });

    // Navigate back to live view
    await page.goto('/');
    await page.waitForTimeout(1000);

    // Navigate to settings
    await page.locator('a[href="/settings"]').click();
    await expect(page).toHaveURL(/.*settings/, { timeout: 10000 });
  });
});
