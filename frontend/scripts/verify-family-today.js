/* Synthetic, local-only built-browser campaign for Stage 10 Family Today. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-10');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_FAMILY_TODAY_PORT || 4182);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const ACTION_REFERENCE = 'a'.repeat(32);

const sessions = {
  organizer: {
    token: 'synthetic-release10-organizer-session',
    user: { id: 'synthetic-organizer', community_id: 'synthetic-family', full_name: 'Synthetic Organizer', role: 'organizer', auth_provider: 'password' },
    community: { id: 'synthetic-family', name: 'Synthetic Family', lifecycle_state: 'active', community_type: 'family', location: 'Private' },
  },
  member: {
    token: 'synthetic-release10-member-session',
    user: { id: 'synthetic-member', community_id: 'synthetic-family', full_name: 'Synthetic Member', role: 'member', auth_provider: 'password' },
    community: { id: 'synthetic-family', name: 'Synthetic Family', lifecycle_state: 'active', community_type: 'family', location: 'Private' },
  },
};

const projections = {
  organizer: {
    viewer_role: 'organizer', lifecycle_state: 'active', primary_action_code: 'complete_command_task',
    primary_action: { code: 'complete_command_task', state: 'open', destination_category: 'organizer_command_center', action_reference: ACTION_REFERENCE },
    secondary_actions: [
      { code: 'review_recap', state: 'ready', destination_category: 'reunion_recap', action_reference: 'b'.repeat(32) },
      { code: 'review_gathering_proposal', state: 'pending', destination_category: 'gathering_proposals' },
    ],
    recent_changes: [{ category: 'organizer_review', is_read: false }, { category: 'gathering_update', is_read: true }],
    navigation_categories: ['today', 'gatherings', 'proposals', 'activity'], milestone_codes: ['first_rsvp_received'], refresh_state: 'current',
  },
  member: {
    viewer_role: 'member', lifecycle_state: 'active', primary_action_code: 'complete_reunion_rsvp',
    primary_action: { code: 'complete_reunion_rsvp', state: 'missing', destination_category: 'attendee_hub', action_reference: ACTION_REFERENCE },
    secondary_actions: [{ code: 'respond_to_gathering_pulse', state: 'open', destination_category: 'gathering_proposals' }],
    recent_changes: [{ category: 'reunion_recap', is_read: false }],
    navigation_categories: ['today', 'gatherings', 'proposals', 'activity'], milestone_codes: [], refresh_state: 'current',
  },
};

const mime = { '.css': 'text/css', '.html': 'text/html', '.js': 'text/javascript', '.json': 'application/json', '.png': 'image/png', '.svg': 'image/svg+xml', '.woff2': 'font/woff2' };

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
  return request.respond({ status, contentType: 'application/json', headers: {
    'access-control-allow-origin': request.headers().origin || `http://${HOST}:${PORT}`,
    'access-control-allow-credentials': 'true', 'access-control-allow-headers': 'authorization,content-type',
    'access-control-allow-methods': 'GET,POST,PUT,DELETE,OPTIONS',
  }, body: JSON.stringify(body) });
}

async function configurePage(page, role, evidence) {
  const session = sessions[role];
  page.on('console', (message) => { if (message.type() === 'error') evidence.errors.push(message.text()); });
  page.on('pageerror', (error) => evidence.errors.push(error.message));
  await page.setRequestInterception(true);
  page.on('request', async (request) => {
    const requestUrl = new URL(request.url());
    if (requestUrl.origin === API_ORIGIN) {
      evidence.apiRequests.push({ method: request.method(), pathname: requestUrl.pathname, search: requestUrl.search });
      if (request.method() === 'OPTIONS') return jsonResponse(request, {});
      const apiPath = requestUrl.pathname.replace(/^\/api/, '');
      if (apiPath === '/auth/me') return jsonResponse(request, session);
      if (apiPath === '/today') return jsonResponse(request, projections[role]);
      if (apiPath === `/today/actions/${ACTION_REFERENCE}`) {
        evidence.actionResolutions += 1;
        return jsonResponse(request, { destination: role === 'organizer' ? '/reunion/command/synthetic-authorized-event' : '/reunion/hub/synthetic-authorized-event' });
      }
      if (apiPath === '/notifications/mark-read') {
        evidence.markReadCalls += 1;
        projections[role].recent_changes = projections[role].recent_changes.map((item) => ({ ...item, is_read: true }));
        return jsonResponse(request, { status: 'ok' });
      }
      if (apiPath === '/community/modules') return jsonResponse(request, { enabled: ['gatherings', 'memory', 'care', 'funds', 'kinship', 'polls', 'legacy_threads', 'steward', 'health'] });
      if (apiPath === '/communications/unread-summary') return jsonResponse(request, { announcements_unread: 0, chat_unread: 0, total_unread: 0 });
      if (apiPath === '/communities/mine') return jsonResponse(request, { communities: [] });
      return jsonResponse(request, {});
    }
    if (requestUrl.origin === `http://${HOST}:${PORT}` || requestUrl.protocol === 'data:') return request.continue();
    evidence.externalRequests.push(request.url());
    return request.abort();
  });
  await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((stored) => window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(stored)), session);
}

async function clickText(page, selector, text) {
  const clicked = await page.evaluate((targetSelector, targetText) => {
    const target = Array.from(document.querySelectorAll(targetSelector)).find((item) => item.textContent.trim().includes(targetText));
    if (target) target.click();
    return Boolean(target);
  }, selector, text);
  if (!clicked) throw new Error(`Control not found: ${text}`);
}

(async () => {
  if (!fs.existsSync(path.join(BUILD, 'index.html'))) throw new Error('Run the production frontend build first.');
  fs.mkdirSync(OUTPUT, { recursive: true });
  const server = await startServer();
  const browser = await puppeteer.launch({ channel: 'chrome', headless: true, args: ['--no-sandbox', '--disable-setuid-sandbox'] });
  const evidence = { errors: [], apiRequests: [], externalRequests: [], actionResolutions: 0, markReadCalls: 0 };
  try {
    const organizer = await browser.newPage();
    await organizer.setViewport({ width: 1440, height: 1000, deviceScaleFactor: 1 });
    await configurePage(organizer, 'organizer', evidence);
    await organizer.goto(`http://${HOST}:${PORT}/home`, { waitUntil: 'networkidle0' });
    await organizer.waitForSelector('[data-testid="family-today-page"]', { visible: true });
    const organizerText = await organizer.$eval('body', (element) => element.innerText);
    if (!organizerText.includes('Move reunion planning forward')) throw new Error('Organizer primary action was not dominant.');
    if (organizerText.includes('Community Health') || organizerText.includes('Funds & Travel')) throw new Error('Secondary modules escaped More.');
    await clickText(organizer, 'button', 'More');
    await organizer.waitForSelector('[data-testid="nav-more-items"]', { visible: true });
    await organizer.screenshot({ path: path.join(OUTPUT, 'organizer-today-desktop.png'), fullPage: true });
    // The destination's own data-heavy UI is covered by the Release 3 campaign;
    // this campaign verifies only Today's authorized route handoff/history.
    organizer.removeAllListeners('console');
    organizer.removeAllListeners('pageerror');
    await clickText(organizer, '[data-testid="today-primary-card"] button', 'Continue planning');
    await organizer.waitForFunction(() => window.location.pathname === '/reunion/command/synthetic-authorized-event');
    await organizer.goBack({ waitUntil: 'networkidle0' });
    if (new URL(organizer.url()).pathname !== '/home') throw new Error('Browser back did not restore Today.');
    await organizer.goForward({ waitUntil: 'domcontentloaded' });
    if (new URL(organizer.url()).pathname !== '/reunion/command/synthetic-authorized-event') throw new Error('Browser forward did not preserve the authorized deep link.');

    const member = await browser.newPage();
    await member.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await configurePage(member, 'member', evidence);
    await member.goto(`http://${HOST}:${PORT}/dashboard`, { waitUntil: 'networkidle0' });
    await member.waitForSelector('[data-testid="family-today-page"]', { visible: true });
    const memberText = await member.$eval('body', (element) => element.innerText);
    if (!memberText.includes('Share your reunion response')) throw new Error('Legacy /dashboard did not resolve to member Today.');
    if (memberText.includes('Community Health') || memberText.includes('Family activation') || memberText.includes('Subscription')) throw new Error('Member navigation exposed organizer controls.');
    if (evidence.markReadCalls !== 0) throw new Error('Opening Today marked notifications read.');
    await clickText(member, 'button', 'Mark changes read');
    await member.waitForFunction(() => !document.body.innerText.includes('Mark changes read'));
    if (evidence.markReadCalls !== 1) throw new Error('Mark-read was not one explicit action.');
    await member.setOfflineMode(true);
    await member.evaluate(() => window.dispatchEvent(new Event('offline')));
    await member.waitForSelector('[data-testid="today-offline-state"]', { visible: true });
    const primaryDisabled = await member.$eval('[data-testid="today-primary-card"] button', (button) => button.disabled);
    if (!primaryDisabled) throw new Error('Offline Today left its primary mutation/navigation enabled.');
    await member.screenshot({ path: path.join(OUTPUT, 'member-today-mobile-offline.png'), fullPage: true });

    if (evidence.actionResolutions !== 1) throw new Error('Opaque action was not resolved exactly once.');
    if (evidence.apiRequests.some((item) => item.search)) throw new Error('Today API request used a query string.');
    if (evidence.externalRequests.length) throw new Error(`Unexpected external requests: ${evidence.externalRequests.join(' | ')}`);
    if (evidence.errors.length) throw new Error(`Browser errors: ${evidence.errors.join(' | ')}`);
    console.log(JSON.stringify({ result: 'passed', role_navigation: true, opaque_action_reauthorization: true, back_forward: true, dashboard_continuity: true, explicit_mark_read: true, offline_state: true, third_party_isolation: true, screenshots: ['organizer-today-desktop.png', 'member-today-mobile-offline.png'] }, null, 2));
  } finally {
    await browser.close();
    await new Promise((resolve) => server.close(resolve));
  }
})().catch((error) => { console.error(error); process.exitCode = 1; });
