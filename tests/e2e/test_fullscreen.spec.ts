/**
 * Tests for fullscreen camera preview
 */

import { test, expect } from '@playwright/test';

test.describe('Fullscreen Preview', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);
  });

  test('should open fullscreen from MJPEG mode', async ({ page }) => {
    // Ensure we're in MJPEG mode
    const mjpegButton = page.locator('#mode-mjpeg');
    if (!await mjpegButton.evaluate(el => el.classList.contains('active'))) {
      await mjpegButton.click();
      await page.waitForTimeout(1000);
    }

    // Click on first camera video area
    const firstCamera = page.locator('.camera-video').first();
    await firstCamera.click();

    // Fullscreen modal should appear
    const modal = page.locator('#fullscreen-modal');
    await expect(modal).toHaveClass(/active/, { timeout: 5000 });

    // Stream should load
    const stream = page.locator('#fullscreen-stream');
    await expect(stream).toBeVisible();

    // Wait for stream to load
    await page.waitForTimeout(3000);

    // Check status shows "Live"
    const status = page.locator('#fullscreen-status');
    const statusText = await status.textContent();
    console.log('Fullscreen status (MJPEG):', statusText);

    // Status should be "Live" or at least not "Loading..."
    expect(statusText).not.toBe('Loading...');
  });

  test('should open fullscreen from WebSocket mode', async ({ page }) => {
    // Capture console logs
    page.on('console', msg => {
      if (msg.text().includes('Stream') || msg.text().includes('WebSocket') || msg.text().includes('Fullscreen')) {
        console.log(`[BROWSER] ${msg.text()}`);
      }
    });

    // WebSocket is now the default - wait for connections to establish
    await page.waitForTimeout(5000);

    // Verify WebSocket mode is active
    const wsActive = await page.locator('#mode-websocket').evaluate(el => el.classList.contains('active'));
    expect(wsActive).toBe(true);
    console.log('WebSocket mode active');

    // Click on first camera video area (canvas in WebSocket mode)
    const firstCamera = page.locator('.camera-video').first();
    await firstCamera.click();

    // Fullscreen modal should appear
    const modal = page.locator('#fullscreen-modal');
    await expect(modal).toHaveClass(/active/, { timeout: 5000 });
    console.log('Fullscreen modal opened');

    // In WebSocket mode, fullscreen uses canvas instead of img
    const canvas = page.locator('#fullscreen-canvas');
    await expect(canvas).toBeVisible();

    // Wait for status to become "Live" (with timeout)
    const status = page.locator('#fullscreen-status');
    await expect(status).toHaveText('Live', { timeout: 15000 });

    // Take screenshot
    await page.screenshot({ path: 'test-results/fullscreen-from-websocket.png' });

    // Verify status
    const statusText = await status.textContent();
    console.log('Fullscreen status (from WebSocket mode):', statusText);
  });

  test('should close fullscreen and restore streams', async ({ page }) => {
    // WebSocket is now the default - wait for connections
    await page.waitForTimeout(5000);

    // Open fullscreen
    const firstCamera = page.locator('.camera-video').first();
    await firstCamera.click();

    // Wait for modal
    const modal = page.locator('#fullscreen-modal');
    await expect(modal).toHaveClass(/active/);
    await page.waitForTimeout(2000);

    // Close fullscreen
    await page.locator('.close-btn').click();

    // Modal should be hidden
    await expect(modal).not.toHaveClass(/active/);

    // Wait for streams to restore
    await page.waitForTimeout(3000);

    // Check that canvas streams are working again (if still in WebSocket mode)
    const canvases = await page.locator('canvas.camera-stream[data-camera-id]').all();
    console.log(`Found ${canvases.length} canvases after closing fullscreen`);

    // At least some canvases should have content
    let hasContent = false;
    for (const canvas of canvases) {
      const content = await canvas.evaluate((el: HTMLCanvasElement) => {
        if (el.width === 0 || el.height === 0) return false;
        const ctx = el.getContext('2d');
        if (!ctx) return false;
        const data = ctx.getImageData(el.width/2, el.height/2, 1, 1).data;
        return data[0] > 0 || data[1] > 0 || data[2] > 0;
      });
      if (content) {
        hasContent = true;
        break;
      }
    }

    expect(hasContent).toBe(true);
  });

  test('should close fullscreen with ESC key', async ({ page }) => {
    // Open fullscreen
    const firstCamera = page.locator('.camera-video').first();
    await firstCamera.click();

    const modal = page.locator('#fullscreen-modal');
    await expect(modal).toHaveClass(/active/);

    // Press ESC
    await page.keyboard.press('Escape');

    // Modal should close
    await expect(modal).not.toHaveClass(/active/);
  });
});

test.describe('Fullscreen - WebSocket Connection Cleanup', () => {
  test('should close WebSocket connections when opening fullscreen', async ({ page }) => {
    // Track WebSocket closures
    const wsClosures: string[] = [];
    page.on('console', msg => {
      if (msg.text().includes('WebSocket closed')) {
        wsClosures.push(msg.text());
      }
    });

    await page.goto('/');
    // WebSocket is now the default - wait for connections to establish
    await page.waitForTimeout(5000);

    // Get number of active WebSocket connections
    const wsCountBefore = await page.evaluate(() => {
      return Object.keys((window as any).websockets || {}).length;
    });
    console.log(`WebSocket connections before fullscreen: ${wsCountBefore}`);

    // Open fullscreen
    const firstCamera = page.locator('.camera-video').first();
    await firstCamera.click();

    // Wait for modal and cleanup
    await page.waitForTimeout(2000);

    // Check WebSocket connections were closed
    const wsCountAfter = await page.evaluate(() => {
      return Object.keys((window as any).websockets || {}).length;
    });
    console.log(`WebSocket connections after fullscreen: ${wsCountAfter}`);

    // Should have fewer (ideally 0) WebSocket connections
    expect(wsCountAfter).toBe(0);
    expect(wsClosures.length).toBeGreaterThan(0);
  });
});
