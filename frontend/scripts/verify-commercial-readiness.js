/* Browser smoke test and screenshot capture for anonymous commercial flows. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots');
const HOST = '127.0.0.1';
const PORT = 4173;
const API_URL = 'https://kindred-production-badd.up.railway.app/api/subscriptions/plans';

const mime = {
  '.css': 'text/css',
  '.html': 'text/html',
  '.js': 'text/javascript',
  '.json': 'application/json',
  '.png': 'image/png',
  '.svg': 'image/svg+xml',
  '.woff2': 'font/woff2',
};

function startServer() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const pathname = decodeURIComponent(req.url.split('?')[0]);
      let file = path.join(BUILD, pathname);
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
      if (!fs.existsSync(file)) file = path.join(BUILD, 'index.html');
      res.writeHead(200, { 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(PORT, HOST, () => resolve(server));
  });
}

async function assertVisible(page, selector, message) {
  await page.waitForSelector(selector, { visible: true, timeout: 15000 });
  if (!(await page.$(selector))) throw new Error(message);
}

(async () => {
  const liveResponse = await fetch(API_URL);
  if (!liveResponse.ok) throw new Error(`Live plans API returned ${liveResponse.status}`);
  const livePlans = await liveResponse.text();
  const livePayload = JSON.parse(livePlans);
  const expectedAmounts = {
    sapling: { monthly: 9.99, annual: 89.99 },
    oak: { monthly: 19.99, annual: 179.99 },
    redwood: { monthly: 39.99, annual: 359.99 },
  };
  for (const [tier, expected] of Object.entries(expectedAmounts)) {
    const plan = livePayload.plans.find((candidate) => candidate.id === tier);
    const monthly = plan?.billing_options?.monthly?.amount ?? plan?.monthly_price;
    const annual = plan?.billing_options?.annual?.amount ?? plan?.annual_price;
    if (monthly !== expected.monthly || annual !== expected.annual) {
      throw new Error(`Live API pricing drift for ${tier}: monthly=${monthly}, annual=${annual}`);
    }
  }
  const server = await startServer();
  const browser = await puppeteer.launch({
    channel: 'chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });

  try {
    fs.mkdirSync(OUTPUT, { recursive: true });
    const page = await browser.newPage();
    const browserErrors = [];
    page.on('console', (message) => {
      if (message.type() === 'error') browserErrors.push(`console: ${message.text()}`);
    });
    page.on('pageerror', (error) => browserErrors.push(`page: ${error.message}`));
    await page.setBypassServiceWorker(true);
    await page.setRequestInterception(true);
    page.on('request', (request) => {
      if (request.url() === API_URL) {
        request.respond({
          status: 200,
          contentType: 'application/json',
          headers: {
            'access-control-allow-origin': `http://${HOST}:${PORT}`,
            'access-control-allow-credentials': 'true',
          },
          body: livePlans,
        });
      } else if (new URL(request.url()).pathname === '/sw.js') {
        request.abort();
      } else {
        request.continue();
      }
    });

    await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="landing-see-all-plans-link"]', 'Public plans link is missing.');
    if (await page.$('[data-testid="landing-read-strategy-link"]')) throw new Error('Consumer strategy link still exists.');
    await assertVisible(page, '[data-testid="public-plan-seedling"]', 'Canonical landing prices did not render.');
    await page.screenshot({ path: path.join(OUTPUT, 'public-navigation-desktop.png'), fullPage: true });

    await page.focus('[data-testid="landing-see-all-plans-link"]');
    await page.keyboard.press('Enter');
    await page.waitForFunction(() => window.location.pathname === '/pricing');
    await assertVisible(page, '[data-testid="public-pricing-page"]', 'Public pricing route did not open.');
    for (const tier of ['seedling', 'sapling', 'oak', 'redwood', 'elder-grove']) {
      await assertVisible(page, `[data-testid="public-plan-${tier}"]`, `Missing ${tier} on public pricing.`);
    }
    await assertVisible(page, '[data-testid="public-plan-price-seedling-free"]', 'Seedling is not explicitly free.');
    for (const tier of ['sapling', 'oak', 'redwood']) {
      await assertVisible(page, `[data-testid="public-plan-price-${tier}-monthly"]`, `Missing ${tier} monthly price.`);
      await assertVisible(page, `[data-testid="public-plan-price-${tier}-annual"]`, `Missing ${tier} annual price.`);
    }
    const pricingText = await page.$eval('[data-testid="public-pricing-page"]', (element) => element.innerText);
    for (const amount of ['$9.99', '$89.99', '$19.99', '$179.99', '$39.99', '$359.99']) {
      if (!pricingText.includes(amount)) throw new Error(`Public pricing is missing ${amount}.`);
    }
    if (!pricingText.includes('Billed every month') || !pricingText.includes('Billed once per year')) {
      throw new Error('Public pricing does not disclose both billing intervals.');
    }
    await page.screenshot({ path: path.join(OUTPUT, 'public-pricing-desktop.png'), fullPage: true });

    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="landing-see-all-plans-link"]', 'Mobile plans link is missing.');
    await page.screenshot({ path: path.join(OUTPUT, 'public-navigation-mobile.png'), fullPage: true });

    await page.goto(`http://${HOST}:${PORT}/pricing`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="public-plan-redwood"]', 'Mobile pricing did not render.');
    await page.screenshot({ path: path.join(OUTPUT, 'public-pricing-mobile.png'), fullPage: true });

    for (const route of ['/privacy', '/terms', '/support']) {
      await page.goto(`http://${HOST}:${PORT}${route}`, { waitUntil: 'networkidle0' });
      if (page.url().includes('/login')) throw new Error(`${route} unexpectedly required authentication.`);
      if ((await page.evaluate(() => document.body.innerText.length)) < 500) {
        throw new Error(`${route} did not render enough public content.`);
      }
    }
    if (browserErrors.length) {
      throw new Error(`Browser errors detected:\n${browserErrors.join('\n')}`);
    }

    console.log('Verified keyboard-accessible anonymous home → pricing navigation, five live plans, privacy, terms, and support at desktop/mobile widths with no browser errors.');
    console.log(`Screenshots: ${OUTPUT}`);
  } finally {
    await browser.close();
    server.close();
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
