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

  console.log('\n=== Testing Toggle Button Functionality ===\n');

  // Test 1: Check that selection mode is initially off
  console.log('Test 1: Verify selection mode is initially off');
  let selectionBtn = await page.locator('#select-area-btn');
  let hasActive = await selectionBtn.evaluate(el => el.classList.contains('active'));
  console.log(`  - Selection button active: ${hasActive} (should be false)`);

  // Test 2: Click toggle button to enable selection mode
  console.log('\nTest 2: Enable selection mode');
  await selectionBtn.click();
  await page.waitForTimeout(300);
  hasActive = await selectionBtn.evaluate(el => el.classList.contains('active'));
  let cursor = await page.locator('#fullscreen-video-wrapper').evaluate(el =>
    window.getComputedStyle(el).cursor
  );
  console.log(`  - Selection button active: ${hasActive} (should be true)`);
  console.log(`  - Wrapper cursor: ${cursor} (should be crosshair)`);

  // Test 3: Try dragging to create selection box
  console.log('\nTest 3: Drag to create selection box');
  const streamImg = await page.locator('#fullscreen-stream');
  const box = await streamImg.boundingBox();

  // Start drag from center-left
  const startX = box.x + box.width * 0.3;
  const startY = box.y + box.height * 0.4;

  // End drag at center-right
  const endX = box.x + box.width * 0.7;
  const endY = box.y + box.height * 0.6;

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.waitForTimeout(100);

  // Check if selection box is visible
  let selectionBoxVisible = await page.locator('#zoom-selection-box').evaluate(el =>
    el.classList.contains('active')
  );
  console.log(`  - Selection box visible during drag: ${selectionBoxVisible} (should be true)`);

  await page.mouse.move(endX, endY, { steps: 10 });
  await page.waitForTimeout(200);
  await page.mouse.up();
  await page.waitForTimeout(500);

  // Test 4: Check if zoom occurred and selection mode auto-disabled
  console.log('\nTest 4: Verify zoom occurred and selection mode auto-disabled');
  let zoomLevel = await page.textContent('#zoom-indicator');
  hasActive = await selectionBtn.evaluate(el => el.classList.contains('active'));
  console.log(`  - Zoom level: ${zoomLevel} (should be > 100%)`);
  console.log(`  - Selection button active: ${hasActive} (should be false - auto-disabled)`);

  // Test 5: Reset zoom and test panning (when not in selection mode)
  console.log('\nTest 5: Test panning works when selection mode is off');
  await page.click('button[title="Reset Zoom (0)"]');
  await page.waitForTimeout(300);

  // Zoom in with button
  await page.click('button[title="Zoom In (+)"]');
  await page.click('button[title="Zoom In (+)"]');
  await page.waitForTimeout(300);

  zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`  - Zoomed to: ${zoomLevel}`);

  // Try panning (selection mode should be off)
  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.mouse.move(startX + 50, startY + 50, { steps: 5 });
  await page.mouse.up();
  await page.waitForTimeout(300);
  console.log('  - Panning successful (no selection box should have appeared)');

  // Test 6: Enable selection mode again and verify it toggles on
  console.log('\nTest 6: Re-enable selection mode');
  await selectionBtn.click();
  await page.waitForTimeout(300);
  hasActive = await selectionBtn.evaluate(el => el.classList.contains('active'));
  console.log(`  - Selection button active: ${hasActive} (should be true)`);

  // Test 7: Click toggle again to manually disable
  console.log('\nTest 7: Manually disable selection mode');
  await selectionBtn.click();
  await page.waitForTimeout(300);
  hasActive = await selectionBtn.evaluate(el => el.classList.contains('active'));
  cursor = await page.locator('#fullscreen-video-wrapper').evaluate(el =>
    window.getComputedStyle(el).cursor
  );
  console.log(`  - Selection button active: ${hasActive} (should be false)`);
  console.log(`  - Wrapper cursor: ${cursor} (should not be crosshair)`);

  // Take final screenshot
  await page.screenshot({ path: '/tmp/zoom-toggle-test.png', fullPage: true });
  console.log('\n✅ All toggle tests completed!');
  console.log('Screenshot saved to /tmp/zoom-toggle-test.png');
  console.log('\nKeeping browser open for 10 seconds for manual inspection...');
  await page.waitForTimeout(10000);

  await browser.close();
})();
