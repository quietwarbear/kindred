/* Synthetic, local-only browser campaign for Stage 8 reunion continuity. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-8');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_REUNION_RECAP_PORT || 4180);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const EVENT_PATH_ID = 'synthetic-release8-browser-reunion';

const organizerSession = {
  token: 'synthetic-release8-organizer-session',
  user: {
    id: 'synthetic-release8-organizer', community_id: 'synthetic-release8-family',
    full_name: 'Synthetic Organizer', role: 'organizer', auth_provider: 'password',
  },
  community: { id: 'synthetic-release8-family', name: 'Synthetic Family', lifecycle_state: 'active' },
};
const memberSession = {
  ...organizerSession,
  token: 'synthetic-release8-member-session',
  user: { ...organizerSession.user, id: 'synthetic-release8-member', full_name: 'Synthetic Member', role: 'member' },
};

const baseRecap = {
  state: 'ready', revision: 0, viewer_role: 'organizer',
  reunion: {
    title: 'Synthetic Family Reunion', start_at: '2026-06-01T09:00:00-04:00',
    end_at: '2026-06-02T17:00:00-04:00', timezone: 'America/New_York',
  },
  itinerary: [{
    position: 1, title: 'Family dinner', start_at: '2026-06-02T15:00:00-04:00',
    end_at: '2026-06-02T19:00:00-04:00', timezone: 'America/New_York',
    my_response: 'coming', participation: { coming: 8, maybe: 2, not_coming: 1 },
  }],
  my_participation: { rsvp_status: 'going', guest_count: 0 },
  aggregate_participation: {
    going: 8, some: 1, maybe: 2, not_going: 1,
    available_categories: 4, claimed_categories: 3, published_memory_count: 5,
  },
  memory_capsule: { available: true },
  next_gathering: { state: 'not_started' },
};

const mime = {
  '.css': 'text/css', '.html': 'text/html', '.js': 'text/javascript',
  '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2',
};

function startServer() {
  return new Promise((resolve) => {
    const server = http.createServer((request, response) => {
      const pathname = decodeURIComponent(request.url.split('?')[0]);
      let file = path.join(BUILD, pathname);
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, 'index.html');
      if (!fs.existsSync(file)) file = path.join(BUILD, 'index.html');
      response.writeHead(200, { 'Cache-Control': 'no-store', 'Content-Type': mime[path.extname(file)] || 'application/octet-stream' });
      fs.createReadStream(file).pipe(response);
    });
    server.listen(PORT, HOST, () => resolve(server));
  });
}

function jsonResponse(request, body, status = 200) {
  return request.respond({
    status, contentType: 'application/json',
    headers: {
      'access-control-allow-origin': request.headers().origin || `http://${HOST}:${PORT}`,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization,content-type',
      'access-control-allow-methods': 'GET,POST,PUT,OPTIONS',
    },
    body: JSON.stringify(body),
  });
}

async function seedSession(page, session) {
  await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((stored) => window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(stored)), session);
}

async function clickButton(page, label) {
  const clicked = await page.evaluate((text) => {
    const button = Array.from(document.querySelectorAll('button')).find((item) => item.textContent.trim().includes(text));
    if (button) button.click();
    return Boolean(button);
  }, label);
  if (!clicked) throw new Error(`Button unavailable: ${label}`);
}

async function configurePage(page, session, evidence) {
  let current = { ...baseRecap, viewer_role: session.user.role === 'member' ? 'member' : 'organizer' };
  page.on('console', (message) => { if (message.type() === 'error') evidence.errors.push(message.text()); });
  page.on('pageerror', (error) => evidence.errors.push(error.message));
  await page.setBypassServiceWorker(true);
  await page.setRequestInterception(true);
  page.on('request', (request) => {
    const requestUrl = new URL(request.url());
    if (request.method() === 'OPTIONS') return jsonResponse(request, {}, 204);
    if (requestUrl.origin === API_ORIGIN) {
      evidence.apiRequests.push({ method: request.method(), pathname: requestUrl.pathname, search: requestUrl.search });
      if (requestUrl.pathname === '/api/auth/me') return jsonResponse(request, session);
      if (requestUrl.pathname === `/api/events/${EVENT_PATH_ID}/recap/organizer` && request.method() === 'GET') {
        return jsonResponse(request, {
          ...current,
          completion: { state: 'ready', boundary: 'at_or_after_final_end', completed_at: '2026-06-02T23:00:00+00:00' },
          carry_forward_catalog: { itinerary_templates: [], contribution_categories: [] },
        });
      }
      if (requestUrl.pathname === `/api/events/${EVENT_PATH_ID}/recap` && request.method() === 'GET') {
        return jsonResponse(request, { ...current, state: 'published', revision: 2, message: 'The family gathered, remembered, and made room for what comes next.' });
      }
      if (requestUrl.pathname.endsWith('/recap/message') && request.method() === 'PUT') {
        const data = JSON.parse(request.postData() || '{}');
        evidence.messageTransport = {
          urlContainsText: request.url().includes(encodeURIComponent(data.message || '')),
          bodyUsed: typeof data.message === 'string',
        };
        current = { ...current, revision: 1, message: data.message };
        return jsonResponse(request, current);
      }
      if (requestUrl.pathname.endsWith('/recap/publish') && request.method() === 'POST') {
        current = { ...current, state: 'published', revision: 2 };
        return jsonResponse(request, current);
      }
      if (requestUrl.pathname.endsWith('/next-gathering/preview')) {
        const data = JSON.parse(request.postData() || '{}');
        return jsonResponse(request, {
          preview_digest: 'a'.repeat(64),
          proposal: {
            new_gathering: {
              title: data.title, start_at: data.start_at, end_at: data.end_at,
              timezone: data.timezone, publication_state: 'organizer_draft', invitation_count: 0, rsvp_response_count: 0,
            },
            carried_forward: { gathering_format: 'in-person', max_attendees: 50, itinerary_templates: [], contribution_categories: [] },
            guarantees: { zero_invitations: true, zero_responses: true, zero_assignments: true, new_structural_identifiers: true },
          },
        });
      }
      if (requestUrl.pathname.endsWith('/next-gathering') && request.method() === 'POST') {
        evidence.createCount += 1;
        return jsonResponse(request, { status: 'draft_created', next_action: 'continue_planning', planning_path: '/reunion/command/synthetic-new-private-draft' });
      }
      return jsonResponse(request, {});
    }
    if (requestUrl.origin === `http://${HOST}:${PORT}` || requestUrl.protocol === 'data:') return request.continue();
    evidence.externalRequests.push(request.url());
    return request.abort();
  });
}

(async () => {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) throw new Error('Run the production frontend build first.');
  fs.mkdirSync(OUTPUT, { recursive: true });
  const server = await startServer();
  const browser = await puppeteer.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const evidence = { errors: [], apiRequests: [], externalRequests: [], createCount: 0, messageTransport: null };

  try {
    const organizerPage = await browser.newPage();
    await organizerPage.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    await configurePage(organizerPage, organizerSession, evidence);
    await seedSession(organizerPage, organizerSession);
    await organizerPage.goto(`http://${HOST}:${PORT}/reunion/recap/${EVENT_PATH_ID}`, { waitUntil: 'networkidle0' });
    await organizerPage.waitForSelector('[data-testid="organizer-recap-controls"]', { visible: true });
    await organizerPage.type('textarea', 'The family gathered, remembered, and made room for what comes next.');
    await clickButton(organizerPage, 'Save message');
    await organizerPage.waitForFunction(() => document.body.innerText.includes('The family gathered, remembered'));
    await clickButton(organizerPage, 'Publish recap');
    await organizerPage.waitForFunction(() => document.body.innerText.includes('The family recap is published'));
    await organizerPage.screenshot({ path: path.join(OUTPUT, 'organizer-recap-desktop.png'), fullPage: true });

    await organizerPage.evaluate(() => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value').set;
      const inputs = Array.from(document.querySelectorAll('input[type="datetime-local"]'));
      setter.call(inputs[0], '2027-11-06T10:00');
      inputs[0].dispatchEvent(new Event('input', { bubbles: true }));
      setter.call(inputs[1], '2027-11-06T18:00');
      inputs[1].dispatchEvent(new Event('input', { bubbles: true }));
    });
    await organizerPage.waitForFunction(() => {
      const button = Array.from(document.querySelectorAll('button')).find((item) => item.textContent.includes('Review carry-forward preview'));
      return button && !button.disabled;
    });
    await clickButton(organizerPage, 'Review carry-forward preview');
    await organizerPage.waitForSelector('[data-testid="next-gathering-preview"]', { visible: true });
    if (evidence.errors.length) throw new Error(`Organizer recap errors: ${evidence.errors.join(' | ')}`);
    // The destination command-center campaign is covered separately. Stop
    // collecting console evidence before navigating into that mocked surface.
    organizerPage.removeAllListeners('console');
    organizerPage.removeAllListeners('pageerror');
    await clickButton(organizerPage, 'Create private draft');
    await organizerPage.waitForFunction(() => window.location.pathname === '/reunion/command/synthetic-new-private-draft');

    const memberPage = await browser.newPage();
    await memberPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await configurePage(memberPage, memberSession, evidence);
    await seedSession(memberPage, memberSession);
    await memberPage.goto(`http://${HOST}:${PORT}/reunion/recap/${EVENT_PATH_ID}`, { waitUntil: 'networkidle0' });
    await memberPage.waitForSelector('[data-testid="published-recap-message"]', { visible: true });
    await memberPage.screenshot({ path: path.join(OUTPUT, 'member-recap-mobile.png'), fullPage: true });
    const memberText = await memberPage.$eval('body', (element) => element.innerText);
    for (const forbidden of ['private-invitation', 'example.invalid', 'Other Private Person', 'internal id']) {
      if (memberText.includes(forbidden)) throw new Error(`Member recap exposed forbidden marker: ${forbidden}`);
    }
    if (!evidence.messageTransport?.bodyUsed || evidence.messageTransport.urlContainsText) throw new Error('Private recap text transport was not body-only.');
    if (evidence.createCount !== 1) throw new Error('Next-gathering creation was not one explicit action.');
    if (evidence.apiRequests.some((item) => item.search)) throw new Error('Stage 8 API request used a query string.');
    if (evidence.externalRequests.length) throw new Error(`Unexpected external requests: ${evidence.externalRequests.join(' | ')}`);
    if (evidence.errors.length) throw new Error(`Browser errors: ${evidence.errors.join(' | ')}`);

    console.log(JSON.stringify({
      result: 'passed', organizer_preview_and_publish: true, member_projection: true,
      recap_text_body_only: true, explicit_next_gathering_creation: true,
      screenshots: ['organizer-recap-desktop.png', 'member-recap-mobile.png'],
    }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
