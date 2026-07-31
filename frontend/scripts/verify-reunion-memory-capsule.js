/* Synthetic, local-only browser campaign for the private reunion memory capsule. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-5');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_CAPSULE_PORT || 4177);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const EVENT_ID = 'synthetic-capsule-reunion';

const session = {
  token: 'synthetic-capsule-session',
  user: {
    id: 'synthetic-capsule-member',
    community_id: 'synthetic-capsule-community',
    full_name: 'Synthetic Member',
    role: 'member',
    auth_provider: 'email',
    onboarding_completed: true,
  },
  community: { id: 'synthetic-capsule-community', name: 'Synthetic Community' },
};

const reunion = {
  id: EVENT_ID,
  title: 'Synthetic Reunion',
  start_at: '2027-08-01T12:00:00-04:00',
  end_at: '2027-08-02T16:00:00-04:00',
  timezone: 'America/New_York',
};

const itinerary = [
  {
    id: 'published-activity',
    title: 'Published reunion gathering',
    start_at: '2027-08-01T18:00:00-04:00',
    end_at: '2027-08-01T20:00:00-04:00',
    timezone: 'America/New_York',
    venue_name: 'Example Hall',
    venue_detail: 'Community room',
    location_tba: false,
  },
];

let capsule = {
  reunion,
  itinerary,
  memories: [
    {
      id: 'synthetic-shared-memory',
      story: 'A synthetic story used only for local verification.',
      contributor_name: 'Synthetic Contributor',
      created_at: '2027-08-03T00:00:00Z',
      updated_at: '',
      is_mine: false,
    },
  ],
  memory_count: 1,
  own_contribution: {
    id: 'synthetic-own-contribution',
    story: 'A private synthetic draft.',
    status: 'draft',
    created_at: '2027-08-03T01:00:00Z',
    updated_at: '',
  },
  visibility: {
    code: 'private_community',
    label: 'Your private Kindred community',
    explanation: 'Community members who can see this reunion can revisit published stories in this capsule.',
  },
  reviewed: false,
  next_action: { code: 'finish_memory_draft' },
};

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
    const server = http.createServer((request, response) => {
      const pathname = decodeURIComponent(request.url.split('?')[0]);
      let file = path.join(BUILD, pathname);
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) {
        file = path.join(file, 'index.html');
      }
      if (!fs.existsSync(file)) file = path.join(BUILD, 'index.html');
      response.writeHead(200, {
        'Cache-Control': 'no-store',
        'Content-Type': mime[path.extname(file)] || 'application/octet-stream',
      });
      fs.createReadStream(file).pipe(response);
    });
    server.listen(PORT, HOST, () => resolve(server));
  });
}

function jsonResponse(request, body, status = 200) {
  return request.respond({
    status,
    contentType: 'application/json',
    headers: {
      'access-control-allow-origin': request.headers().origin || `http://${HOST}:${PORT}`,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization,content-type',
      'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS',
    },
    body: JSON.stringify(body),
  });
}

async function configurePage(page, evidence) {
  page.on('console', (message) => {
    if (message.type() === 'error') evidence.errors.push(`console: ${message.text()}`);
  });
  page.on('pageerror', (error) => evidence.errors.push(`page: ${error.message}`));
  await page.setBypassServiceWorker(true);
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const requestUrl = new URL(request.url());
    if (request.method() === 'OPTIONS') return jsonResponse(request, {}, 204);
    if (requestUrl.origin === API_ORIGIN) {
      evidence.apiRequests.push({
        method: request.method(),
        pathname: requestUrl.pathname,
        search: requestUrl.search,
        authorization: request.headers().authorization || '',
        hasIdempotencyKey: (request.postData() || '').includes('idempotency_key'),
      });
      if (requestUrl.pathname === '/api/auth/me') return jsonResponse(request, session);
      if (
        requestUrl.pathname === `/api/events/${EVENT_ID}/memory-capsule`
        && request.method() === 'GET'
      ) {
        return jsonResponse(request, capsule);
      }
      if (
        requestUrl.pathname === `/api/events/${EVENT_ID}/memory-capsule/contribution/synthetic-own-contribution`
        && request.method() === 'PUT'
      ) {
        capsule = {
          ...capsule,
          memories: [
            ...capsule.memories,
            {
              id: 'synthetic-own-contribution',
              story: 'A private synthetic draft.',
              contributor_name: 'Synthetic Member',
              created_at: '2027-08-03T01:00:00Z',
              updated_at: '2027-08-03T02:00:00Z',
              is_mine: true,
            },
          ],
          memory_count: 2,
          own_contribution: {
            ...capsule.own_contribution,
            status: 'published',
          },
          next_action: { code: 'review_reunion_memories' },
        };
        return jsonResponse(request, capsule);
      }
      if (
        requestUrl.pathname === `/api/events/${EVENT_ID}/memory-capsule/reviewed`
        && request.method() === 'POST'
      ) {
        capsule = {
          ...capsule,
          reviewed: true,
          next_action: { code: 'reunion_capsule_complete' },
        };
        return jsonResponse(request, capsule);
      }
      if (
        requestUrl.pathname === `/api/events/${EVENT_ID}/memory-capsule/contribution/synthetic-own-contribution`
        && request.method() === 'DELETE'
      ) {
        capsule = {
          ...capsule,
          memories: capsule.memories.filter((item) => !item.is_mine),
          memory_count: 1,
          own_contribution: null,
          next_action: { code: 'reunion_capsule_complete' },
        };
        return jsonResponse(request, capsule);
      }
      if (requestUrl.pathname === '/api/subscriptions/plans') {
        return jsonResponse(request, { plans: [] });
      }
      return jsonResponse(request, { detail: 'Unexpected synthetic route.' }, 404);
    }
    if (requestUrl.origin === `http://${HOST}:${PORT}`) return request.continue();
    evidence.externalRequests.push(request.url());
    return request.abort();
  });
}

async function seedSession(page) {
  await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((value) => {
    window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(value));
  }, session);
}

async function assertVisible(page, selector, message) {
  try {
    await page.waitForSelector(selector, { visible: true, timeout: 15000 });
  } catch (error) {
    const rendered = await page.evaluate(() => document.body.innerText.slice(0, 1800));
    throw new Error(`${message}\nRendered text: ${rendered}`, { cause: error });
  }
}

async function clickButton(page, label) {
  const clicked = await page.evaluate((text) => {
    const button = Array.from(document.querySelectorAll('button'))
      .find((candidate) => candidate.textContent.trim() === text);
    if (button) button.click();
    return Boolean(button);
  }, label);
  if (!clicked) throw new Error(`Button was unavailable: ${label}`);
}

(async () => {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) {
    throw new Error('Run the production frontend build before this campaign.');
  }
  fs.mkdirSync(OUTPUT, { recursive: true });
  const server = await startServer();
  const browser = await puppeteer.launch({
    channel: 'chrome',
    headless: true,
    args: ['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
  });
  const evidence = { errors: [], externalRequests: [], apiRequests: [] };

  try {
    const page = await browser.newPage();
    await configurePage(page, evidence);
    await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    await seedSession(page);
    await page.goto(`http://${HOST}:${PORT}/reunion/memories/${EVENT_ID}`, {
      waitUntil: 'networkidle0',
    });
    await assertVisible(page, '[data-testid="reunion-memory-capsule"]', 'Capsule did not render.');
    const text = await page.$eval(
      '[data-testid="reunion-memory-capsule"]',
      (element) => element.innerText,
    );
    const normalizedText = text.toLowerCase();
    for (const expected of [
      'private reunion memory capsule',
      'finish your saved draft',
      'published reunion gathering',
      'community members who can see this reunion',
    ]) {
      if (!normalizedText.includes(expected)) throw new Error(`Missing capsule content: ${expected}`);
    }
    for (const forbidden of [
      'invitation credential',
      'organizer-only',
      'private planning note',
      'community_id',
      'capsule_revision',
    ]) {
      if (normalizedText.includes(forbidden)) {
        throw new Error(`Capsule exposed forbidden marker: ${forbidden}`);
      }
    }
    await page.screenshot({
      path: path.join(OUTPUT, 'reunion-memory-capsule-desktop.png'),
      fullPage: true,
    });

    await clickButton(page, 'Publish to the capsule');
    await page.waitForFunction(() => document.body.innerText.includes('Revisit the family stories'));
    const publishRequest = evidence.apiRequests.find(
      (request) => request.method === 'PUT' && request.pathname.includes('/contribution/'),
    );
    if (!publishRequest?.hasIdempotencyKey) {
      throw new Error('Contribution publish did not include a stable idempotency key.');
    }

    await page.setOfflineMode(true);
    await page.waitForFunction(() => document.body.innerText.includes('You’re offline'));
    if (!(await page.$$('button:disabled')).length) {
      throw new Error('Offline capsule mutation controls were not disabled.');
    }
    await page.setOfflineMode(false);

    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.reload({ waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="reunion-memory-capsule"]', 'Mobile capsule did not render.');
    await page.screenshot({
      path: path.join(OUTPUT, 'reunion-memory-capsule-mobile.png'),
      fullPage: true,
    });

    await clickButton(page, 'Mark memories reviewed');
    await page.waitForFunction(() => document.body.innerText.includes('The reunion capsule is ready'));
    await clickButton(page, 'Withdraw my contribution');
    await page.waitForFunction(() => document.body.innerText.includes('no longer appears'));
    const withdrawalRequest = evidence.apiRequests.find(
      (request) => request.method === 'DELETE' && request.pathname.includes('/contribution/'),
    );
    if (!withdrawalRequest?.hasIdempotencyKey) {
      throw new Error('Contribution withdrawal did not include a stable idempotency key.');
    }

    if (evidence.errors.length) throw new Error(`Browser errors:\n${evidence.errors.join('\n')}`);
    if (evidence.externalRequests.length) {
      throw new Error(`Unexpected external requests:\n${evidence.externalRequests.join('\n')}`);
    }
    for (const request of evidence.apiRequests) {
      if (request.pathname === '/api/subscriptions/plans') continue;
      if (
        request.search
        || request.pathname.includes(session.token)
        || request.authorization !== `Bearer ${session.token}`
      ) {
        throw new Error(`Unsafe authenticated request metadata: ${request.method} ${request.pathname}`);
      }
    }
    console.log(
      'Verified desktop/mobile capsule, strict content, draft publication, review, withdrawal, offline lockout, idempotency transport, and zero external requests with synthetic responses.',
    );
    console.log(`Screenshots: ${OUTPUT}`);
  } finally {
    await browser.close();
    server.closeAllConnections?.();
    await new Promise((resolve, reject) => {
      server.close((error) => (error ? reject(error) : resolve()));
    });
  }
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
