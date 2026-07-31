/* Synthetic, local-only browser campaign for Release 6 family-space activation. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-6');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_FAMILY_ACTIVATION_PORT || 4178);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';

const session = {
  token: 'synthetic-release6-session',
  user: {
    id: 'synthetic-release6-organizer',
    community_id: 'synthetic-release6-community',
    full_name: 'Synthetic Organizer',
    role: 'organizer',
    auth_provider: 'email',
    onboarding_completed: true,
  },
  community: {
    id: 'synthetic-release6-community',
    name: 'Synthetic Internal Planning Space',
    community_type: 'family reunion',
    lifecycle_state: 'provisional',
    lifecycle_revision: 0,
  },
};

const ready = {
  lifecycle_state: 'provisional',
  lifecycle_revision: 0,
  readiness_status: 'ready',
  ready: true,
  aggregate_counts: {
    reunions: 1,
    verified_invitations: 3,
    accepted_responses: 2,
    non_host_participants: 2,
  },
  unmet_condition_codes: [],
  elapsed_day_bucket: '2_7',
  next_action: { code: 'activate_family_space' },
};

const active = {
  ...ready,
  lifecycle_state: 'active',
  lifecycle_revision: 1,
  readiness_status: 'active',
  next_action: { code: 'open_family_home' },
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

function safeHomeResponse(pathname) {
  if (pathname === '/api/subscriptions/plans') return { plans: [] };
  if (pathname === '/api/communications/unread-summary') {
    return { announcements_unread: 0, chat_unread: 0, total_unread: 0 };
  }
  if (pathname === '/api/notifications/unread-count') return { unread_count: 0 };
  if (pathname === '/api/notifications/history') return { items: [], total: 0 };
  if (pathname === '/api/communities/mine') return { communities: [] };
  if (pathname === '/api/community/modules') return { enabled: [] };
  if (pathname === '/api/courtyard/home') {
    return {
      stats: { members: 3, subyards: 0, gatherings: 1, funds_total: 0 },
      upcoming_gatherings: [],
      active_courtyards: [],
      quick_actions: [],
      notifications: [],
      role_catalog: [],
    };
  }
  return null;
}

async function configurePage(page, evidence, mode = 'ready') {
  let conflictPending = mode === 'ready';
  let currentReadiness = mode === 'active' ? active : ready;
  page.on('console', (message) => {
    const text = message.text();
    const expectedHttpFailure = /status of (403|409)/.test(text);
    if (message.type() === 'error' && !expectedHttpFailure) {
      evidence.errors.push(`console: ${text}`);
    }
  });
  page.on('pageerror', (error) => evidence.errors.push(`page: ${error.message}`));
  await page.setBypassServiceWorker(true);
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const requestUrl = new URL(request.url());
    if (request.method() === 'OPTIONS') return jsonResponse(request, {}, 204);
    if (requestUrl.origin === API_ORIGIN) {
      const postData = request.postData() || '';
      evidence.apiRequests.push({
        method: request.method(),
        pathname: requestUrl.pathname,
        search: requestUrl.search,
        authorization: request.headers().authorization || '',
        postData,
      });
      if (requestUrl.pathname === '/api/auth/me') {
        return jsonResponse(request, {
          ...session,
          community: currentReadiness.lifecycle_state === 'active'
            ? { ...session.community, name: 'The Synthetic Family', lifecycle_state: 'active', lifecycle_revision: 1 }
            : session.community,
        });
      }
      if (requestUrl.pathname === '/api/family-space/activation') {
        if (mode === 'denied') {
          return jsonResponse(request, { detail: 'You do not have access to perform this action.' }, 403);
        }
        if (request.method() === 'GET') return jsonResponse(request, currentReadiness);
        if (request.method() === 'POST' && conflictPending) {
          conflictPending = false;
          return jsonResponse(request, {
            detail: {
              code: 'family_space_activation_conflict',
              message: 'The family space changed. Refresh before trying again.',
            },
          }, 409);
        }
        if (request.method() === 'POST') {
          currentReadiness = active;
          return jsonResponse(request, {
            status: 'activated',
            lifecycle_state: 'active',
            lifecycle_revision: 1,
            next_action: { code: 'open_family_home' },
          });
        }
      }
      const homeResponse = safeHomeResponse(requestUrl.pathname);
      if (homeResponse) return jsonResponse(request, homeResponse);
      evidence.unexpectedRoutes.push(`${request.method()} ${requestUrl.pathname}`);
      return jsonResponse(request, {});
    }
    if (requestUrl.origin === `http://${HOST}:${PORT}`) return request.continue();
    evidence.externalRequests.push(request.url());
    return request.abort();
  });
}

async function seedSession(page, value = session) {
  await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((stored) => {
    window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(stored));
  }, value);
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
  const evidence = { errors: [], externalRequests: [], apiRequests: [], unexpectedRoutes: [] };

  try {
    const page = await browser.newPage();
    await configurePage(page, evidence);
    await page.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    await seedSession(page);
    await page.goto(`http://${HOST}:${PORT}/family/activate`, { waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="family-space-activation-page"]', 'Activation page did not render.');
    const text = (await page.$eval('body', (element) => element.innerText)).toLowerCase();
    for (const expected of [
      'from reunion plan to family home',
      'meaningful participation, not link copying',
      'everything already shared stays together',
      'activate family space',
    ]) {
      if (!text.includes(expected)) throw new Error(`Missing activation content: ${expected}`);
    }
    for (const forbidden of [
      session.community.name.toLowerCase(),
      session.community.id.toLowerCase(),
      'invitation credential',
      'subscription management',
      'payment required',
    ]) {
      if (text.includes(forbidden)) throw new Error(`Activation page exposed forbidden marker: ${forbidden}`);
    }
    await page.screenshot({
      path: path.join(OUTPUT, 'family-space-activation-desktop.png'),
      fullPage: true,
    });

    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.reload({ waitUntil: 'networkidle0' });
    await assertVisible(page, '[data-testid="family-space-activation-page"]', 'Mobile activation page did not render.');
    await page.screenshot({
      path: path.join(OUTPUT, 'family-space-activation-mobile.png'),
      fullPage: true,
    });

    await page.setOfflineMode(true);
    await page.waitForFunction(() => document.body.innerText.includes('Reconnect to activate'));
    const disabledOffline = await page.$eval(
      '[data-testid="family-space-activate-button"]',
      (button) => button.disabled,
    );
    if (!disabledOffline) throw new Error('Offline activation control was not disabled.');
    await page.setOfflineMode(false);

    await page.type('[data-testid="family-space-name-input"]', 'The Synthetic Family');
    await clickButton(page, 'Activate family space');
    await page.waitForFunction(() => document.body.innerText.includes('changed. Review the latest state'));
    await clickButton(page, 'Activate family space');
    await page.waitForFunction(() => document.body.innerText.includes('Your family home is ready.'));
    await page.waitForFunction(() => window.location.pathname === '/home');

    const posts = evidence.apiRequests.filter(
      (request) => request.method === 'POST' && request.pathname === '/api/family-space/activation',
    );
    if (posts.length !== 2) throw new Error(`Expected two activation attempts, received ${posts.length}.`);
    for (const post of posts) {
      const body = JSON.parse(post.postData);
      if (!body.idempotency_key || body.expected_revision !== 0) {
        throw new Error('Activation request omitted idempotency or expected revision.');
      }
    }
    if (JSON.parse(posts[0].postData).idempotency_key === JSON.parse(posts[1].postData).idempotency_key) {
      throw new Error('A definitive conflict retained the stale idempotency key.');
    }

    const postsBeforeDefer = evidence.apiRequests.filter(
      (request) => request.method === 'POST' && request.pathname === '/api/family-space/activation',
    ).length;
    const deferPage = await browser.newPage();
    await configurePage(deferPage, evidence);
    await seedSession(deferPage);
    await deferPage.goto(`http://${HOST}:${PORT}/family/activate`, { waitUntil: 'networkidle0' });
    await assertVisible(deferPage, '[data-testid="family-space-defer-button"]', 'Defer control did not render.');
    await clickButton(deferPage, 'Decide later');
    await deferPage.waitForFunction(() => window.location.pathname === '/home');
    await deferPage.close();
    const postsAfterDefer = evidence.apiRequests.filter(
      (request) => request.method === 'POST' && request.pathname === '/api/family-space/activation',
    ).length;
    if (postsAfterDefer !== postsBeforeDefer) {
      throw new Error('Deferring unexpectedly submitted an activation mutation.');
    }

    const deniedPage = await browser.newPage();
    await configurePage(deniedPage, evidence, 'denied');
    await seedSession(deniedPage, { ...session, user: { ...session.user, role: 'member' } });
    await deniedPage.goto(`http://${HOST}:${PORT}/family/activate`, { waitUntil: 'networkidle0' });
    await deniedPage.waitForFunction(() => document.body.innerText.includes('Organizer access required'));
    await deniedPage.close();

    const activePage = await browser.newPage();
    await configurePage(activePage, evidence, 'active');
    await seedSession(activePage, { ...session, community: { ...session.community, lifecycle_state: 'active' } });
    await activePage.goto(`http://${HOST}:${PORT}/family/activate`, { waitUntil: 'networkidle0' });
    await activePage.waitForFunction(() => document.body.innerText.includes('This family space is active.'));
    await activePage.close();

    if (evidence.errors.length) throw new Error(`Browser errors:\n${evidence.errors.join('\n')}`);
    if (evidence.externalRequests.length) {
      throw new Error(`Unexpected external requests:\n${evidence.externalRequests.join('\n')}`);
    }
    if (evidence.unexpectedRoutes.length) {
      throw new Error(`Unexpected API routes:\n${evidence.unexpectedRoutes.join('\n')}`);
    }
    for (const request of evidence.apiRequests) {
      if (request.pathname === '/api/subscriptions/plans') continue;
      if (request.search || request.pathname.includes(session.token)) {
        throw new Error(`Unsafe authenticated request URL: ${request.method} ${request.pathname}`);
      }
      if (request.authorization !== `Bearer ${session.token}`) {
        throw new Error(`Missing header-only session transport: ${request.method} ${request.pathname}`);
      }
    }
    console.log('Verified desktop/mobile activation, aggregate readiness, mutation-free defer, conflict refresh, idempotency transport, offline lockout, organizer denial, already-active continuity, home navigation, and zero external requests.');
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
