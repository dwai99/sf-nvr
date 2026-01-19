const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Listen to console messages
  page.on('console', msg => {
    console.log(`[BROWSER] ${msg.type()}: ${msg.text()}`);
  });

  // Listen to page errors
  page.on('pageerror', error => {
    console.error(`[PAGE ERROR] ${error.message}`);
  });

  // Listen to failed requests
  page.on('requestfailed', request => {
    console.error(`[REQUEST FAILED] ${request.url()} - ${request.failure().errorText}`);
  });

  // Listen to responses
  page.on('response', response => {
    if (response.status() >= 400) {
      console.error(`[HTTP ${response.status()}] ${response.url()}`);
    }
  });

  // Navigate to the NVR interface
  console.log('Navigating to http://localhost:8080...');
  await page.goto('http://localhost:8080');

  // Wait for cameras to load
  console.log('Waiting for cameras to load...');
  await page.waitForSelector('.camera-card', { timeout: 10000 });

  // Count cameras
  const cameraCount = await page.locator('.camera-card').count();
  console.log(`Found ${cameraCount} cameras`);

  // Click the first camera to open fullscreen modal
  console.log('Clicking first camera to open fullscreen...');
  await page.locator('.camera-video').first().click();

  // Wait for modal to appear
  console.log('Waiting for modal...');
  await page.waitForSelector('.fullscreen-modal.active', { timeout: 5000 });
  console.log('Modal is active');

  // Check if stream image is present
  const streamImg = page.locator('#fullscreen-stream');
  const imgSrc = await streamImg.getAttribute('src');
  console.log(`Stream image src: ${imgSrc}`);

  // Check if image is visible
  const isVisible = await streamImg.isVisible();
  console.log(`Stream image visible: ${isVisible}`);

  // Get computed styles
  const boundingBox = await streamImg.boundingBox();
  console.log(`Image bounding box:`, boundingBox);

  // Check image natural dimensions after waiting a bit
  await page.waitForTimeout(2000);
  const dimensions = await streamImg.evaluate(img => {
    const computedStyle = window.getComputedStyle(img);
    return {
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      width: img.width,
      height: img.height,
      complete: img.complete,
      display: computedStyle.display,
      visibility: computedStyle.visibility,
      opacity: computedStyle.opacity,
      maxWidth: computedStyle.maxWidth,
      maxHeight: computedStyle.maxHeight,
      objectFit: computedStyle.objectFit
    };
  });
  console.log('Image dimensions and styles:', dimensions);

  // Check status text
  const statusText = await page.locator('#fullscreen-status').textContent();
  console.log(`Status text: ${statusText}`);

  // Take a screenshot
  await page.screenshot({ path: '/tmp/fullscreen-modal.png', fullPage: true });
  console.log('Screenshot saved to /tmp/fullscreen-modal.png');

  // Keep browser open for inspection
  console.log('\nBrowser will stay open for 30 seconds for inspection...');
  await page.waitForTimeout(30000);

  await browser.close();
})();
