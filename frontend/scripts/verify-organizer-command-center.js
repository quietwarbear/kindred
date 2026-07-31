/* Synthetic, local-only browser campaign for the organizer command center. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-3');
const HOST = '127.0.0.1';
const PORT = 4174;
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const EVENT_ID = 'synthetic-reunion';

const session = {
  token: 'synthetic-local-browser-session',
  user: {
    id: 'synthetic-host',
    full_name: 'Avery Organizer',
    role: 'host',
    auth_provider: 'email',
    onboarding_completed: true,
  },
  community: {
    id: 'synthetic-community',
    name: 'The Example Family',
  },
};

const event = {
  id: EVENT_ID,
  community_id: session.community.id,
  created_by: session.user.id,
  created_by_name: session.user.full_name,
  title: 'The Example Family Reunion',
  description: 'A synthetic reunion used only for local browser verification.',
  start_at: '2027-07-18T09:00:00-07:00',
  end_at: '2027-07-20T18:00:00-07:00',
  timezone: 'America/Los_Angeles',
  location: 'Oakland, California',
  event_template: 'reunion',
  gathering_format: 'in-person',
  planning_team_member_ids: ['synthetic-host'],
};

const commandCenter = {
  event_timezone: event.timezone,
  next_action: { code: 'follow_up_missing_responses', count: 2 },
  responses: {
    total: 8,
    responded: 6,
    missing: 2,
    counts: { going: 4, some: 1, maybe: 1, 'not-going': 0, pending: 2 },
    reconciles: true,
  },
  deadlines: {
    valid: 2,
    invalid: 0,
    approaching: 1,
    next: { kind: 'activity_rsvp', at: '2027-07-12T23:59:00-07:00' },
  },
  progress: {
    itinerary: { status: 'in_progress', done: 3, total: 4 },
    checklist: { status: 'in_progress', done: 5, total: 8 },
    potluck: { status: 'in_progress', done: 4, total: 6 },
    volunteer_roles: { status: 'in_progress', done: 2, total: 3 },
    event_roles: { status: 'complete', done: 3, total: 3 },
    travel: { status: 'in_progress', plans: 3 },
    budget: null,
    planning_team: {
      status: 'active',
      assigned: 1,
      pending_invitations: 1,
    },
  },
  reminders: {
    available: false,
    code: 'privacy_safe_sender_unavailable',
    recipient_count: 2,
  },
  recent_changes: [
    { kind: 'overall-rsvp', at: '2027-07-10T18:20:00Z' },
    { kind: 'itinerary-update', at: '2027-07-09T17:00:00Z' },
  ],
  guest_preview_available: true,
};

const guestPreview = {
  invitee_name: 'Invited guest',
  rsvp_status: 'pending',
  invited_by_name: session.user.full_name,
  community_name: session.community.name,
  gathering: {
    title: event.title,
    start_at: event.start_at,
    end_at: event.end_at,
    timezone: event.timezone,
    location: event.location,
    gathering_format: event.gathering_format,
    description: event.description,
    event_template: 'reunion',
    activity_count: 3,
    activities: [],
  },
};

const members = {
  members: [
    { id: 'synthetic-host', full_name: 'Avery Organizer', role: 'host' },
    { id: 'synthetic-organizer', full_name: 'Jordan Planner', role: 'organizer' },
    { id: 'synthetic-member', full_name: 'Morgan Relative', role: 'member' },
  ],
};

const planningTeam = {
  assigned: [
    { id: 'synthetic-host', full_name: 'Avery Organizer', role: 'host' },
  ],
  pending_invitations: [
    {
      id: 'synthetic-planning-invitation',
      email: 'planner@example.invalid',
      created_at: '2027-07-08T12:00:00Z',
    },
  ],
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
  const origin = request.headers().origin || `http://${HOST}:${PORT}`;
  return request.respond({
    status,
    contentType: 'application/json',
    headers: {
      'access-control-allow-origin': origin,
      'access-control-allow-credentials': 'true',
      'access-control-allow-headers': 'authorization,content-type',
      'access-control-allow-methods': 'GET,POST,PUT,PATCH,DELETE,OPTIONS',
    },
    body: JSON.stringify(body),
  });
}

async function configurePage(page, evidence, authorize = true) {
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
      });
      if (requestUrl.pathname === '/api/auth/me') {
        return jsonResponse(request, authorize ? session : {
          ...session,
          user: { ...session.user, role: 'member' },
        });
      }
      if (requestUrl.pathname === '/api/subscriptions/plans') {
        return jsonResponse(request, { plans: [] });
      }
      if (requestUrl.pathname === '/api/family-space/activation') {
        return authorize
          ? jsonResponse(request, {
              lifecycle_state: 'provisional',
              lifecycle_revision: 0,
              readiness_status: 'ready',
              ready: true,
              aggregate_counts: {
                reunions: 1,
                verified_invitations: 3,
                accepted_responses: 2,
                non_host_participants: 1,
              },
              unmet_requirements: [],
              elapsed_bucket: 'week_2_plus',
              next_action: 'activate_family_space',
            })
          : jsonResponse(request, { detail: 'Organizer access required.' }, 403);
      }
      if (requestUrl.pathname === `/api/events/${EVENT_ID}/command-center`) {
        return authorize
          ? jsonResponse(request, commandCenter)
          : jsonResponse(request, { detail: 'Organizer access required.' }, 403);
      }
      if (requestUrl.pathname === `/api/events/${EVENT_ID}`) {
        return jsonResponse(request, event);
      }
      if (requestUrl.pathname === '/api/community/members') {
        return jsonResponse(request, members);
      }
      if (requestUrl.pathname === `/api/events/${EVENT_ID}/planning-team`) {
        return jsonResponse(request, planningTeam);
      }
      if (requestUrl.pathname === `/api/events/${EVENT_ID}/guest-preview`) {
        return jsonResponse(request, guestPreview);
      }
      if (
        requestUrl.pathname === `/api/events/${EVENT_ID}/reminders/preflight`
        && request.method() === 'POST'
      ) {
        return jsonResponse(request, commandCenter.reminders);
      }
      if (requestUrl.pathname.includes('/planning-team/')) {
        return jsonResponse(request, { status: 'revoked' });
      }
      return jsonResponse(request, { detail: 'Unexpected synthetic route.' }, 404);
    }
    if (requestUrl.origin === `http://${HOST}:${PORT}`) return request.continue();
    evidence.externalRequests.push(request.url());
    return request.abort();
  });
}

async function seedSession(page, seededSession = session) {
  await page.goto(`http://${HOST}:${PORT}/`, { waitUntil: 'domcontentloaded' });
  await page.evaluate((value) => {
    window.localStorage.setItem('gathering-cypher-auth', JSON.stringify(value));
  }, seededSession);
}

async function assertVisible(page, selector, message) {
  try {
    await page.waitForSelector(selector, { visible: true, timeout: 15000 });
  } catch (error) {
    const rendered = await page.evaluate(() => document.body.innerText.slice(0, 1600));
    throw new Error(`${message}\nRendered text: ${rendered}`, { cause: error });
  }
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
    await page.goto(`http://${HOST}:${PORT}/reunion/command/${EVENT_ID}`, {
      waitUntil: 'networkidle0',
    });
    await assertVisible(
      page,
      '[data-testid="organizer-command-center"]',
      'Organizer command center did not render.',
    );
    const text = await page.$eval(
      '[data-testid="organizer-command-center"]',
      (element) => element.innerText,
    );
    for (const expected of [
      'Follow up on missing responses',
      'Counts reconcile',
      'Pending invitations',
      'planner@example.invalid',
      'Budget',
    ]) {
      if (expected === 'Budget' ? text.includes(expected) : !text.includes(expected)) {
        throw new Error(`Unexpected command-center content for: ${expected}`);
      }
    }
    await page.click('header button');
    await assertVisible(
      page,
      '[data-testid="command-center-guest-preview"]',
      'Guest preview did not render.',
    );
    const previewText = await page.$eval(
      '[data-testid="command-center-guest-preview"]',
      (element) => element.innerText,
    );
    for (const forbidden of ['planner@example.invalid', 'Still missing', 'Planning team']) {
      if (previewText.toLowerCase().includes(forbidden.toLowerCase())) {
        throw new Error(`Guest preview exposed organizer-only marker: ${forbidden}`);
      }
    }
    await page.screenshot({
      path: path.join(OUTPUT, 'organizer-command-center-desktop.png'),
      fullPage: true,
    });

    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.goto(`http://${HOST}:${PORT}/reunion/command/${EVENT_ID}`, {
      waitUntil: 'networkidle0',
    });
    await assertVisible(
      page,
      '[data-testid="command-center-next-action"]',
      'Mobile next action did not render.',
    );
    await page.screenshot({
      path: path.join(OUTPUT, 'organizer-command-center-mobile.png'),
      fullPage: true,
    });

    const deniedEvidence = { errors: [], externalRequests: [], apiRequests: [] };
    const deniedPage = await browser.newPage();
    await configurePage(deniedPage, deniedEvidence, false);
    await seedSession(deniedPage, {
      ...session,
      user: { ...session.user, role: 'member' },
    });
    await deniedPage.goto(`http://${HOST}:${PORT}/reunion/command/${EVENT_ID}`, {
      waitUntil: 'networkidle0',
    });
    await deniedPage.waitForFunction(() => document.body.innerText.includes('Organizer access required'));
    await deniedPage.close();
    evidence.externalRequests.push(...deniedEvidence.externalRequests);
    evidence.apiRequests.push(...deniedEvidence.apiRequests);

    if (evidence.errors.length) {
      throw new Error(
        `Browser errors:\n${evidence.errors.join('\n')}\nAPI requests: ${JSON.stringify(evidence.apiRequests)}`,
      );
    }
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
        throw new Error(`Unsafe API request: ${JSON.stringify(request)}`);
      }
    }
    console.log(
      'Verified organizer-only access, aggregate status, honest budget omission, canonical guest preview, responsive safe areas, and header-only authenticated API transport using synthetic local responses.',
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
