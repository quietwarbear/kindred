/* Synthetic, local-only browser campaign for the reunion attendee hub. */
const fs = require('fs');
const http = require('http');
const path = require('path');
const puppeteer = require('puppeteer-core');

const BUILD = path.resolve(__dirname, '..', 'build');
const OUTPUT = path.resolve(__dirname, '..', '..', 'docs', 'screenshots', 'release-4');
const HOST = '127.0.0.1';
const PORT = Number(process.env.KINDRED_ATTENDEE_HUB_PORT || 4175);
const API_ORIGIN = 'https://kindred-production-badd.up.railway.app';
const EVENT_ID = 'synthetic-attendee-reunion';
const INVITATION = 'synthetic-attendee-invitation';

const session = {
  token: 'synthetic-attendee-session',
  user: {
    id: 'synthetic-member',
    community_id: 'synthetic-community',
    full_name: 'Jordan Relative',
    role: 'member',
    auth_provider: 'email',
    onboarding_completed: true,
  },
  community: { id: 'synthetic-community', name: 'The Example Family' },
};

const activities = [
  {
    id: 'welcome',
    title: 'Welcome dinner',
    description: 'Reconnect over the first meal of the weekend.',
    start_at: '2027-07-16T18:00:00-04:00',
    end_at: '2027-07-16T20:00:00-04:00',
    timezone: 'America/New_York',
    venue_name: 'Heritage Hall',
    venue_address: '100 Reunion Way',
    venue_detail: 'Garden room',
    location_tba: false,
    attendance_requested: true,
    response_open: true,
    my_response: 'coming',
    attendance: { coming: 31, maybe: 3, not_coming: 2, party_size: 42 },
    notes: 'Step-free entrance available.',
    featured: true,
  },
  {
    id: 'story-circle',
    title: 'Family story circle',
    description: 'Bring one photograph or story for younger relatives.',
    start_at: '2027-07-17T10:00:00-04:00',
    end_at: '2027-07-17T11:30:00-04:00',
    timezone: 'America/New_York',
    venue_name: 'Cedar Room',
    venue_address: '22 Story Lane',
    venue_detail: '',
    location_tba: false,
    attendance_requested: true,
    response_open: true,
    my_response: 'maybe',
    attendance: { coming: 18, maybe: 4, not_coming: 3, party_size: 22 },
    notes: '',
    featured: false,
  },
];

const gathering = {
  id: EVENT_ID,
  title: 'The Example Family Reunion',
  description: 'A synthetic reunion used only for local browser verification.',
  start_at: '2027-07-16T18:00:00-04:00',
  end_at: '2027-07-18T12:00:00-04:00',
  timezone: 'America/New_York',
  location: 'Cedar Grove, Georgia',
  gathering_format: 'in-person',
  zoom_link: '',
  event_template: 'reunion',
};

let hubState = {
  gathering,
  rsvp: {
    my_status: 'going',
    my_guests: 1,
    summary: { going: 24, some: 7, maybe: 4, not_going: 3 },
  },
  itinerary: { activities, reviewed: false },
  contributions: {
    potluck: [
      { id: 'ice', item_name: 'Ice and coolers', claimed: false, is_mine: false },
      { id: 'dessert', item_name: 'Dessert tray', claimed: true, is_mine: false },
    ],
    volunteer: [
      {
        id: 'welcome-table',
        title: 'Welcome table',
        needed_count: 3,
        filled_count: 2,
        openings: 1,
        is_mine: false,
      },
    ],
    own_commitments: { potluck: [], volunteer: [], count: 0 },
  },
  memory_prompt: {
    available: true,
    code: 'reunion_story',
    title: 'Keep one story from this reunion',
    question: 'What is one family story you want everyone to remember?',
    sharing_boundary: 'Your story is saved to this private Kindred community. It is not published to the open web.',
    completed: false,
  },
  next_action: { code: 'choose_contribution' },
};

const publicView = {
  invitee_name: 'Taylor Guest',
  rsvp_status: 'pending',
  invited_by_name: 'Avery Organizer',
  community_name: 'The Example Family',
  gathering: {
    ...gathering,
    activity_count: activities.length,
    activities: activities.map((activity) => ({
      ...activity,
      my_response: 'no-response',
    })),
  },
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
      });
      if (requestUrl.pathname === '/api/auth/me') return jsonResponse(request, session);
      if (requestUrl.pathname === `/api/events/${EVENT_ID}/attendee-hub`) {
        return jsonResponse(request, hubState);
      }
      if (
        requestUrl.pathname === `/api/events/${EVENT_ID}/potluck-claim`
        && request.method() === 'POST'
      ) {
        hubState = {
          ...hubState,
          contributions: {
            ...hubState.contributions,
            potluck: hubState.contributions.potluck.map((item) => (
              item.id === 'ice' ? { ...item, claimed: true, is_mine: true } : item
            )),
            own_commitments: {
              potluck: [{ id: 'ice', item_name: 'Ice and coolers', claimed: true, is_mine: true }],
              volunteer: [],
              count: 1,
            },
          },
          next_action: { code: 'review_itinerary' },
        };
        return jsonResponse(request, { ok: true });
      }
      if (
        requestUrl.pathname === `/api/events/${EVENT_ID}/attendee-hub/itinerary-reviewed`
        && request.method() === 'POST'
      ) {
        hubState = {
          ...hubState,
          itinerary: { ...hubState.itinerary, reviewed: true },
          next_action: { code: 'share_a_memory' },
        };
        return jsonResponse(request, hubState);
      }
      if (requestUrl.pathname === '/api/public/rsvp') {
        if (request.method() === 'POST') {
          return jsonResponse(request, { ...publicView, rsvp_status: 'going', saved: true });
        }
        return jsonResponse(request, publicView);
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

async function clickButtonByText(page, label, all = false) {
  const clicked = await page.evaluate(({ text, every }) => {
    const matches = Array.from(document.querySelectorAll('button'))
      .filter((button) => button.textContent.trim() === text);
    (every ? matches : matches.slice(0, 1)).forEach((button) => button.click());
    return matches.length;
  }, { text: label, every: all });
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
    await page.goto(`http://${HOST}:${PORT}/reunion/hub/${EVENT_ID}`, {
      waitUntil: 'networkidle0',
    });
    await assertVisible(page, '[data-testid="reunion-attendee-hub"]', 'Attendee hub did not render.');
    const desktopText = await page.$eval(
      '[data-testid="reunion-attendee-hub"]',
      (element) => element.innerText,
    );
    for (const expected of [
      'The Example Family Reunion',
      'Choose one way to help',
      'Welcome dinner',
      'Ice and coolers',
      'Keep one story from this reunion',
    ]) {
      if (!desktopText.includes(expected)) throw new Error(`Missing attendee content: ${expected}`);
    }
    for (const forbidden of [
      'invitation credential',
      'planning checklist',
      '$500',
      'private travel itinerary details',
      'other@example.invalid',
    ]) {
      if (desktopText.toLowerCase().includes(forbidden)) {
        throw new Error(`Attendee hub exposed forbidden marker: ${forbidden}`);
      }
    }
    await page.screenshot({
      path: path.join(OUTPUT, 'reunion-attendee-hub-desktop.png'),
      fullPage: true,
    });

    await clickButtonByText(page, 'Claim');
    await page.waitForFunction(() => document.body.innerText.includes('Your commitment'));
    const claimRequest = evidence.apiRequests.find(
      (request) => request.pathname.endsWith('/potluck-claim') && request.method === 'POST',
    );
    if (!claimRequest) throw new Error('Contribution claim did not reach the canonical endpoint.');

    await page.setOfflineMode(true);
    await page.waitForFunction(() => document.body.innerText.includes("You’re offline"));
    const disabledClaimCount = await page.$$eval('button:disabled', (buttons) => buttons.length);
    if (!disabledClaimCount) throw new Error('Offline mutation controls were not disabled.');
    await page.setOfflineMode(false);

    await page.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await page.goto(`http://${HOST}:${PORT}/reunion/hub/${EVENT_ID}`, {
      waitUntil: 'networkidle0',
    });
    await assertVisible(page, '[data-testid="reunion-attendee-hub"]', 'Mobile attendee hub did not render.');
    await page.screenshot({
      path: path.join(OUTPUT, 'reunion-attendee-hub-mobile.png'),
      fullPage: true,
    });

    const publicPage = await browser.newPage();
    await configurePage(publicPage, evidence);
    await publicPage.setViewport({ width: 390, height: 844, deviceScaleFactor: 1 });
    await publicPage.goto(`http://${HOST}:${PORT}/rsvp#${INVITATION}`, {
      waitUntil: 'networkidle0',
    });
    await publicPage.click('[data-testid="public-rsvp-going"]');
    await publicPage.click('[data-testid="public-rsvp-continue"]');
    await clickButtonByText(publicPage, 'Coming', true);
    await clickButtonByText(publicPage, 'Review response');
    await publicPage.click('[data-testid="public-rsvp-submit"]');
    await assertVisible(
      publicPage,
      '[data-testid="public-rsvp-confirmation"]',
      'Public RSVP confirmation did not render.',
    );
    const confirmationText = await publicPage.$eval(
      '[data-testid="public-rsvp-confirmation"]',
      (element) => element.innerText,
    );
    for (const expected of ['Your reunion response is saved', 'Welcome dinner', '31 coming', 'Revise my response']) {
      if (!confirmationText.includes(expected)) throw new Error(`Missing confirmation content: ${expected}`);
    }
    await publicPage.screenshot({
      path: path.join(OUTPUT, 'public-rsvp-confirmation-mobile.png'),
      fullPage: true,
    });

    if (evidence.errors.length) throw new Error(`Browser errors:\n${evidence.errors.join('\n')}`);
    if (evidence.externalRequests.length) {
      throw new Error(`Unexpected external requests:\n${evidence.externalRequests.join('\n')}`);
    }
    for (const request of evidence.apiRequests) {
      if (request.pathname === '/api/subscriptions/plans') continue;
      if (request.pathname === '/api/public/rsvp') {
        if (
          request.search
          || request.authorization !== `Bearer ${INVITATION}`
        ) {
          throw new Error(`Unsafe public RSVP request: ${JSON.stringify(request)}`);
        }
        continue;
      }
      if (
        request.search
        || request.pathname.includes(session.token)
        || request.authorization !== `Bearer ${session.token}`
      ) {
        throw new Error(`Unsafe authenticated request: ${JSON.stringify(request)}`);
      }
    }
    console.log(
      'Verified desktop/mobile attendee hub, deterministic next action, contribution claim, offline mutation lockout, public RSVP confirmation continuity, and header-only credential transport with synthetic local responses.',
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
