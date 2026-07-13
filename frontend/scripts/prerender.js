/* Post-build prerender (Kindred was invisible to crawlers): snapshot the public
 * routes to static HTML so crawlers get real content instead of an empty
 * <div id="root">. Runs as the `postbuild` npm hook, locally and on Vercel.
 *
 * Approach: serve build/ on localhost:3000 (that port is in the backend's
 * CORS allow-list, so the public blog fetch works during the snapshot),
 * visit each route with headless Chrome, write the rendered HTML back into
 * build/. index.js hydrates these snapshots for anonymous visitors only.
 */
const fs = require('fs');
const http = require('http');
const path = require('path');

const BUILD = path.resolve(__dirname, '..', 'build');
const PORT = 3000;
const ROUTES = ['/', '/privacy', '/terms', '/support'];

const MIME = {
  '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css',
  '.json': 'application/json', '.png': 'image/png', '.jpg': 'image/jpeg',
  '.svg': 'image/svg+xml', '.ico': 'image/x-icon', '.txt': 'text/plain',
  '.xml': 'application/xml', '.map': 'application/json', '.woff2': 'font/woff2',
};

function serveBuild() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      const urlPath = decodeURIComponent(req.url.split('?')[0]);
      let file = path.join(BUILD, urlPath);
      if (!fs.existsSync(file) || fs.statSync(file).isDirectory()) {
        file = path.join(BUILD, 'index.html'); // SPA fallback
      }
      res.writeHead(200, { 'Content-Type': MIME[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(PORT, () => resolve(server));
  });
}

// Vercel's build image lacks Chrome's shared system libs (libnspr4.so —
// launch fails with code 127), so serverless builds use @sparticuz/chromium.
// Local builds use the system Chrome via puppeteer-core's channel option.
async function launchBrowser(puppeteer) {
  if (process.env.VERCEL || process.env.AWS_REGION) {
    // ESM-first package: under CommonJS require() the API sits on .default
    const sparticuz = require('@sparticuz/chromium');
    const chromium = sparticuz.default || sparticuz;
    return puppeteer.launch({
      args: chromium.args,
      executablePath: await chromium.executablePath(),
      headless: true,
    });
  }
  return puppeteer.launch({
    channel: 'chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });
}

(async () => {
  let puppeteer;
  try {
    puppeteer = require('puppeteer-core');
  } catch (e) {
    console.warn('[prerender] puppeteer-core not installed — skipping (build stays CSR)');
    process.exit(0);
  }

  const server = await serveBuild();
  let browser;
  try {
    browser = await launchBrowser(puppeteer);
    const page = await browser.newPage();
    // A recognizable UA so analytics can filter the build machine out.
    await page.setUserAgent('kindred-prerender');

    for (const route of ROUTES) {
      await page.goto(`http://localhost:${PORT}${route}`, { waitUntil: 'networkidle0', timeout: 60000 });
      // Let lazy route chunks + fonts settle.
      await new Promise((r) => setTimeout(r, 1500));
      const html = await page.content();
      const outDir = route === '/' ? BUILD : path.join(BUILD, route.slice(1));
      fs.mkdirSync(outDir, { recursive: true });
      fs.writeFileSync(path.join(outDir, 'index.html'), html);
      const textLen = (await page.evaluate(() => document.body.innerText.length));
      console.log(`[prerender] ${route} -> ${path.relative(BUILD, path.join(outDir, 'index.html'))} (${textLen} chars of text)`);
      if (textLen < 100) {
        console.warn(`[prerender] WARNING: ${route} rendered <100 chars — check for runtime errors`);
      }
    }
  } finally {
    if (browser) await browser.close();
    server.close();
  }
  console.log('[prerender] done');
})().catch((e) => {
  // A failed prerender must not fail the deploy — the site still works CSR.
  console.warn('[prerender] failed, keeping CSR build:', e.message);
  process.exit(0);
});
