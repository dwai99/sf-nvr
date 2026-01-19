const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Listen to ALL console messages
  page.on('console', msg => {
    const type = msg.type();
    const text = msg.text();
    console.log(`[${type.toUpperCase()}] ${text}`);
  });

  console.log('Opening NVR interface...');
  await page.goto('http://localhost:8080');
  await page.waitForSelector('.camera-card', { timeout: 10000 });

  console.log('Clicking first camera to open fullscreen modal...');
  await page.locator('.camera-video').first().click();

  await page.waitForSelector('.fullscreen-modal.active', { timeout: 3000 });
  console.log('Fullscreen modal opened\n');

  // Wait for stream to load
  await page.waitForTimeout(2000);

  console.log('=== Testing Selection Zoom ===\n');

  // Enable selection mode
  console.log('1. Clicking select area button...');
  await page.click('#select-area-btn');
  await page.waitForTimeout(500);

  // Get the image bounds
  const streamImg = await page.locator('#fullscreen-stream');
  const box = await streamImg.boundingBox();

  console.log(`2. Image bounds: ${JSON.stringify(box)}\n`);

  // Draw a selection box (center quarter of the image)
  const startX = box.x + box.width * 0.25;
  const startY = box.y + box.height * 0.25;
  const endX = box.x + box.width * 0.75;
  const endY = box.y + box.height * 0.75;

  console.log(`3. Drawing selection from (${startX}, ${startY}) to (${endX}, ${endY})\n`);

  await page.mouse.move(startX, startY);
  await page.mouse.down();
  await page.waitForTimeout(100);
  await page.mouse.move(endX, endY, { steps: 10 });
  await page.waitForTimeout(200);
  await page.mouse.up();
  await page.waitForTimeout(1000);

  // Check zoom level
  const zoomLevel = await page.textContent('#zoom-indicator');
  console.log(`\n4. Zoom level after selection: ${zoomLevel}`);

  // Keep open for inspection
  console.log('\nKeeping browser open for 30 seconds...');
  await page.waitForTimeout(30000);

  await browser.close();
})();
