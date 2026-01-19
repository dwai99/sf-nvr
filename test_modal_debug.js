const { chromium } = require('playwright');

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage();

  // Listen to console messages
  page.on('console', msg => {
    console.log(`[BROWSER] ${msg.type()}: ${msg.text()}`);
  });

  await page.goto('http://localhost:8080');
  await page.waitForSelector('.camera-card', { timeout: 10000 });

  console.log('Clicking first camera...');
  await page.locator('.camera-video').first().click();

  // Wait a bit for modal
  await page.waitForTimeout(1000);

  // Check modal state
  const modalState = await page.evaluate(() => {
    const modal = document.getElementById('fullscreen-modal');
    const computedStyle = window.getComputedStyle(modal);
    return {
      classList: modal.className,
      display: computedStyle.display,
      position: computedStyle.position,
      zIndex: computedStyle.zIndex,
      top: computedStyle.top,
      left: computedStyle.left,
      width: computedStyle.width,
      height: computedStyle.height,
      opacity: computedStyle.opacity,
      visibility: computedStyle.visibility
    };
  });

  console.log('Modal state:', JSON.stringify(modalState, null, 2));

  // Check if image is loading
  const imgState = await page.evaluate(() => {
    const img = document.getElementById('fullscreen-stream');
    const computedStyle = window.getComputedStyle(img);
    return {
      src: img.src,
      display: computedStyle.display,
      width: computedStyle.width,
      height: computedStyle.height,
      naturalWidth: img.naturalWidth,
      naturalHeight: img.naturalHeight,
      complete: img.complete
    };
  });

  console.log('Image state:', JSON.stringify(imgState, null, 2));

  await page.screenshot({ path: '/tmp/modal-debug.png', fullPage: true });
  console.log('Screenshot saved');

  console.log('\nKeeping browser open for 30 seconds...');
  await page.waitForTimeout(30000);

  await browser.close();
})();
