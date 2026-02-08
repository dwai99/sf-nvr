/**
 * Tests for fullscreen grid view (multi-camera)
 */

import { test, expect } from '@playwright/test';

test.describe('Fullscreen Grid View', () => {
  test.beforeEach(async ({ page }) => {
    await page.goto('/');
    await page.waitForTimeout(3000);
  });

  test('should enter fullscreen grid mode with F key', async ({ page }) => {
    // Press F to enter fullscreen grid
    await page.keyboard.press('f');
    await page.waitForTimeout(1000);

    // Body should have fullscreen-grid-mode class
    const isFullscreen = await page.evaluate(() =>
      document.body.classList.contains('fullscreen-grid-mode')
    );
    expect(isFullscreen).toBe(true);

    // Exit with ESC
    await page.keyboard.press('Escape');
  });

  test('should display cameras in MJPEG mode fullscreen grid', async ({ page }) => {
    // Enter fullscreen grid
    await page.locator('.fullscreen-grid-btn').click();
    await page.waitForTimeout(2000);

    // Check that camera streams are visible
    const streams = page.locator('img.camera-stream');
    const count = await streams.count();
    console.log(`MJPEG streams in fullscreen: ${count}`);
    expect(count).toBeGreaterThan(0);

    // Take screenshot
    await page.screenshot({ path: 'test-results/fullscreen-grid-mjpeg.png' });

    // Exit
    await page.keyboard.press('Escape');
  });

  test('should display cameras in WebSocket mode fullscreen grid', async ({ page }) => {
    // Switch to WebSocket mode first
    await page.locator('#mode-websocket').click();
    await page.waitForTimeout(5000);

    // Verify WebSocket mode is active
    await expect(page.locator('#mode-websocket')).toHaveClass(/active/);

    // Enter fullscreen grid
    await page.locator('.fullscreen-grid-btn').click();
    await page.waitForTimeout(5000);

    // Check that canvas streams are visible
    const canvases = page.locator('canvas.camera-stream');
    const count = await canvases.count();
    console.log(`WebSocket canvases in fullscreen grid: ${count}`);
    expect(count).toBeGreaterThan(0);

    // Check canvases have content
    const firstCanvas = canvases.first();
    const hasContent = await firstCanvas.evaluate((el: HTMLCanvasElement) => {
      if (el.width === 0 || el.height === 0) return false;
      const ctx = el.getContext('2d');
      if (!ctx) return false;
      const data = ctx.getImageData(el.width/2, el.height/2, 1, 1).data;
      return data[0] > 0 || data[1] > 0 || data[2] > 0;
    });
    console.log(`First canvas has content: ${hasContent}`);
    expect(hasContent).toBe(true);

    // Take screenshot
    await page.screenshot({ path: 'test-results/fullscreen-grid-websocket.png' });

    // Exit
    await page.keyboard.press('Escape');
  });

  test('should properly size canvases in fullscreen grid', async ({ page }) => {
    // Switch to WebSocket mode
    await page.locator('#mode-websocket').click();
    await page.waitForTimeout(3000);

    // Enter fullscreen grid
    await page.locator('.fullscreen-grid-btn').click();
    await page.waitForTimeout(3000);

    // Get canvas dimensions
    const canvasInfo = await page.evaluate(() => {
      const canvases = document.querySelectorAll('canvas.camera-stream');
      return Array.from(canvases).map((canvas: HTMLCanvasElement) => {
        const rect = canvas.getBoundingClientRect();
        const style = getComputedStyle(canvas);
        return {
          id: canvas.dataset.cameraId,
          displayWidth: rect.width,
          displayHeight: rect.height,
          bufferWidth: canvas.width,
          bufferHeight: canvas.height,
          objectFit: style.objectFit
        };
      });
    });

    console.log('Canvas info in fullscreen grid:', JSON.stringify(canvasInfo, null, 2));

    // All canvases should have non-zero display dimensions
    for (const info of canvasInfo) {
      expect(info.displayWidth).toBeGreaterThan(0);
      expect(info.displayHeight).toBeGreaterThan(0);
    }

    // Exit
    await page.keyboard.press('Escape');
  });

  test('should handle pagination in fullscreen grid', async ({ page }) => {
    // Enter fullscreen grid
    await page.locator('.fullscreen-grid-btn').click();
    await page.waitForTimeout(1000);

    // Check for pagination controls
    const pagination = page.locator('#grid-pagination');
    const pageInfo = await page.locator('#page-info').textContent();
    console.log(`Pagination info: ${pageInfo}`);

    // Exit
    await page.keyboard.press('Escape');
  });

  test('should exit fullscreen grid with button click', async ({ page }) => {
    // Enter fullscreen grid
    await page.locator('.fullscreen-grid-btn').click();
    await page.waitForTimeout(1000);

    // Verify we're in fullscreen mode
    let isFullscreen = await page.evaluate(() =>
      document.body.classList.contains('fullscreen-grid-mode')
    );
    expect(isFullscreen).toBe(true);

    // Click exit button
    await page.locator('.fullscreen-grid-exit').click();
    await page.waitForTimeout(500);

    // Verify we exited
    isFullscreen = await page.evaluate(() =>
      document.body.classList.contains('fullscreen-grid-mode')
    );
    expect(isFullscreen).toBe(false);
  });
});
