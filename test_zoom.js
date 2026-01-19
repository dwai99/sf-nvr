const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Listen to console messages
  page.on('console', msg => {
    console.log(`[BROWSER] ${msg.type()}: ${msg.text()}`);
  });

  console.log('Opening NVR interface...');
  await page.goto('http://localhost:8080');
  await page.waitForSelector('.camera-card', { timeout: 10000 });

  console.log('Clicking first camera to open fullscreen modal...');
  await page.locator('.camera-video').first().click();

  // Wait for modal to open
  await page.waitForSelector('.fullscreen-modal.active', { timeout: 3000 });
  console.log('Fullscreen modal opened');

  // Wait for stream to load
  await page.waitForTimeout(2000);

  console.log('Testing zoom functionality...');

  // Test zoom in button
  console.log('Clicking zoom in button...');
  await page.click('button[title="Zoom In (+)"]');
  await page.waitForTimeout(500);

  let zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`Zoom level after zoom in: ${zoomLevel}`);

  // Test zoom in again
  console.log('Clicking zoom in button again...');
  await page.click('button[title="Zoom In (+)"]');
  await page.waitForTimeout(500);

  zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`Zoom level after second zoom in: ${zoomLevel}`);

  // Test mouse wheel zoom
  console.log('Testing mouse wheel zoom...');
  await page.mouse.move(500, 500);
  await page.mouse.wheel(0, -100); // Scroll up to zoom in
  await page.waitForTimeout(500);

  zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`Zoom level after mouse wheel: ${zoomLevel}`);

  // Test reset zoom button
  console.log('Clicking reset zoom button...');
  await page.click('button[title="Reset Zoom (0)"]');
  await page.waitForTimeout(500);

  zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`Zoom level after reset: ${zoomLevel}`);

  // Test keyboard shortcuts
  console.log('Testing keyboard shortcut: + key...');
  await page.keyboard.press('+');
  await page.waitForTimeout(500);

  zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`Zoom level after + key: ${zoomLevel}`);

  console.log('Testing keyboard shortcut: - key...');
  await page.keyboard.press('-');
  await page.waitForTimeout(500);

  zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`Zoom level after - key: ${zoomLevel}`);

  console.log('Testing keyboard shortcut: 0 key (reset)...');
  await page.keyboard.press('0');
  await page.waitForTimeout(500);

  zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`Zoom level after 0 key: ${zoomLevel}`);

  // Take screenshot
  await page.screenshot({ path: '/tmp/zoom-test.png', fullPage: true });
  console.log('Screenshot saved to /tmp/zoom-test.png');

  console.log('\nClosing modal and testing playback page...');
  await page.keyboard.press('Escape');
  await page.waitForTimeout(500);

  // Navigate to playback
  console.log('Opening playback page...');
  await page.goto('http://localhost:8080/playback');
  await page.waitForSelector('.video-container', { timeout: 10000 });

  // Set date and load recordings
  console.log('Setting date to today and loading last 4 hours...');
  const today = new Date().toISOString().split('T')[0];
  await page.fill('#playback-date', today);
  await page.click('button:has-text("Last 4 Hours")');
  await page.waitForTimeout(2000);
  await page.click('button:has-text("Load Recordings")');
  await page.waitForTimeout(5000);

  // Wait for video to load
  console.log('Waiting for video to load...');
  await page.waitForSelector('video', { timeout: 10000 });

  // Hover over video to show zoom controls
  console.log('Hovering over video to show zoom controls...');
  const videoPlayer = await page.locator('.video-player').first();
  await videoPlayer.hover();
  await page.waitForTimeout(1000);

  // Test zoom on playback video
  console.log('Testing zoom in playback video...');
  const zoomInBtn = videoPlayer.locator('button[title="Zoom In (+)"]');
  await zoomInBtn.click();
  await page.waitForTimeout(500);

  // Take screenshot of playback
  await page.screenshot({ path: '/tmp/playback-zoom-test.png', fullPage: true });
  console.log('Screenshot saved to /tmp/playback-zoom-test.png');

  console.log('\n✅ All zoom tests completed successfully!');
  console.log('Keeping browser open for 10 seconds for manual inspection...');
  await page.waitForTimeout(10000);

  await browser.close();
})();
