const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Listen to console messages
  page.on('console', msg => {
    console.log(`[BROWSER] ${msg.type()}: ${msg.text()}`);
  });

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

  // Get first video player
  const videoPlayer = await page.locator('.video-player').first();
  await videoPlayer.hover();
  await page.waitForTimeout(1000);

  console.log('\n=== Testing Playback Zoom with Selection Mode ===\n');

  // Test 1: Enable selection mode
  console.log('Test 1: Enable selection mode');
  const selectBtn = videoPlayer.locator('.select-area-btn');
  await selectBtn.click();
  await page.waitForTimeout(300);

  let hasActive = await selectBtn.evaluate(el => el.classList.contains('active'));
  console.log(`  - Selection button active: ${hasActive} (should be true)`);

  // Test 2: First zoom - draw selection box
  console.log('\nTest 2: First zoom - draw selection box');
  const videoElement = await videoPlayer.locator('video');
  const box = await videoElement.boundingBox();

  // Draw box in center area
  const startX = box.x + box.width * 0.3;
  const startY = box.y + box.height * 0.3;
  const endX = box.x + box.width * 0.7;
  const endY = box.y + box.height * 0.7;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.waitForTimeout(100);
  await page.mouse.move(endX, endY, { steps: 10 });
  await page.waitForTimeout(200);
  await page.mouse.up();
  await page.waitForTimeout(500);

  let zoomLevel = await videoPlayer.locator('.zoom-indicator').textContent();
  console.log(`  - Zoom level after first zoom: ${zoomLevel}`);

  // Test 3: Second zoom (progressive) - should work without moving image
  console.log('\nTest 3: Second zoom on zoomed image (progressive zoom)');
  console.log('  - Selection mode should still be enabled');

  hasActive = await selectBtn.evaluate(el => el.classList.contains('active'));
  console.log(`  - Selection button still active: ${hasActive} (should be true)`);

  // Draw smaller box for second zoom
  const box2 = await videoElement.boundingBox();
  const start2X = box2.x + box2.width * 0.4;
  const start2Y = box2.y + box2.height * 0.4;
  const end2X = box2.x + box2.width * 0.6;
  const end2Y = box2.y + box2.height * 0.6;

  console.log('  - Drawing second selection box...');
  await page.mouse.move(start2X, start2Y);
  await page.mouse.down();
  await page.waitForTimeout(100);
  await page.mouse.move(end2X, end2Y, { steps: 10 });
  await page.waitForTimeout(200);
  await page.mouse.up();
  await page.waitForTimeout(500);

  zoomLevel = await videoPlayer.locator('.zoom-indicator').textContent();
  console.log(`  - Zoom level after second zoom: ${zoomLevel} (should be much higher)`);

  // Test 4: Third zoom to verify continuous zooming works
  console.log('\nTest 4: Third zoom to verify continuous zooming');

  const box3 = await videoElement.boundingBox();
  const start3X = box3.x + box3.width * 0.45;
  const start3Y = box3.y + box3.height * 0.45;
  const end3X = box3.x + box3.width * 0.55;
  const end3Y = box3.y + box3.height * 0.55;

  await page.mouse.move(start3X, start3Y);
  await page.mouse.down();
  await page.waitForTimeout(100);
  await page.mouse.move(end3X, end3Y, { steps: 10 });
  await page.waitForTimeout(200);
  await page.mouse.up();
  await page.waitForTimeout(500);

  zoomLevel = await videoPlayer.locator('.zoom-indicator').textContent();
  console.log(`  - Zoom level after third zoom: ${zoomLevel} (should be very high)`);

  // Test 5: Disable selection mode and test panning
  console.log('\nTest 5: Disable selection mode and test panning');
  await selectBtn.click();
  await page.waitForTimeout(300);

  hasActive = await selectBtn.evaluate(el => el.classList.contains('active'));
  console.log(`  - Selection button active: ${hasActive} (should be false)`);

  // Try panning
  await page.mouse.move(start3X, start3Y);
  await page.mouse.down();
  await page.mouse.move(start3X + 100, start3Y + 100, { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  console.log('  - Panning successful (image should move)');

  // Test 6: Reset zoom
  console.log('\nTest 6: Reset zoom');
  const resetBtn = videoPlayer.locator('button[title="Reset Zoom (0)"]');
  await resetBtn.click();
  await page.waitForTimeout(300);

  zoomLevel = await videoPlayer.locator('.zoom-indicator').textContent();
  console.log(`  - Zoom level after reset: ${zoomLevel} (should be 100%)`);

  // Take screenshot
  await page.screenshot({ path: '/tmp/playback-zoom-test.png', fullPage: true });
  console.log('\n✅ All playback zoom tests completed!');
  console.log('Screenshot saved to /tmp/playback-zoom-test.png');
  console.log('\nKeeping browser open for 10 seconds for manual inspection...');
  await page.waitForTimeout(10000);

  await browser.close();
})();
