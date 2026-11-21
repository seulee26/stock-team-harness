import assert from 'node:assert/strict';
import { once } from 'node:events';
import { request } from 'node:http';
import test from 'node:test';
import { makeServer } from './server.mjs';

const question = '엔비디아 실적을 볼 때 어떤 숫자가 중요한가요?';

async function fixture(t, options = {}) {
  const server = makeServer(options);
  server.listen(0, '127.0.0.1');
  await once(server, 'listening');
  t.after(() => {
    server.closeAllConnections();
    return new Promise((resolve) => server.close(resolve));
  });
  const port = server.address().port;
  const origin = `http://localhost:${port}`;
  function send(path, { body, cookie, host = `localhost:${port}`, requestOrigin = origin,
    contentType = 'application/json', site } = {}) {
    const headers = { Host: host };
    if (cookie) headers.Cookie = cookie;
    if (site) headers['Sec-Fetch-Site'] = site;
    const data = body === undefined ? null : JSON.stringify(body);
    if (data !== null) {
      if (requestOrigin) headers.Origin = requestOrigin;
      headers['Content-Type'] = contentType;
      headers['Content-Length'] = Buffer.byteLength(data);
    }
    return new Promise((resolve, reject) => {
      const req = request({ host: '127.0.0.1', port, path, headers, method: data === null ? 'GET' : 'POST' }, async (res) => {
        const chunks = [];
        for await (const chunk of res) chunks.push(chunk);
        const bodyText = Buffer.concat(chunks).toString('utf8');
        resolve({ status: res.statusCode, headers: res.headers, json: () => JSON.parse(bodyText) });
      });
      req.on('error', reject);
      req.end(data);
    });
  }
  async function consent() {
    const res = await send('/api/consent', { body: { accepted: true } });
    assert.equal(res.status, 200);
    const cookie = res.headers['set-cookie'][0];
    assert.match(cookie, /^__Host-stock_team_local=[A-Za-z0-9_-]{43}; Path=\/; Secure; HttpOnly; SameSite=Strict; Max-Age=1800$/);
    return cookie.split(';', 1)[0];
  }
  return { send, consent };
}

test('loopback host gate, explicit consent, CSRF, and closed private paths', async (t) => {
  const { send, consent } = await fixture(t);
  const home = await send('/');
  assert.equal(home.status, 200);
  assert.match(home.headers['content-security-policy'], /frame-ancestors 'none'/);
  assert.equal(home.headers['cache-control'], 'no-store');
  assert.equal(home.headers['access-control-allow-origin'], undefined);
  assert.equal((await send('/', { host: 'foreign.example' })).status, 403);
  assert.equal((await send('/api/portfolio')).status, 403);
  assert.equal((await send('/api/consent', { body: { accepted: false } })).status, 400);
  for (const requestOrigin of [null, 'https://example.com', 'http://localhost:65534']) {
    assert.equal((await send('/api/consent', { body: { accepted: true }, requestOrigin })).status, 403);
  }
  assert.equal((await send('/api/consent', { body: { accepted: true }, contentType: 'text/plain' })).status, 415);
  for (const path of ['/api/toss/connect', '/api/payment', '/.env', '/server.mjs', '/harness/README.md', '/reports/ant.pdf']) {
    assert.equal((await send(path)).status, 404);
  }

  const cookie = await consent();
  assert.equal((await send('/api/portfolio', { cookie, site: 'same-site' })).status, 403);
  assert.equal((await send('/api/portfolio', { cookie, site: 'same-origin' })).json().holdings.length, 3);
  assert.equal((await send('/api/fee', { cookie, body: { market: 'KOSPI', amount: 100_000_000 } })).json().estimatedCost, 215_000);
  const withdrawn = await send('/api/disconnect', { cookie, body: {} });
  assert.match(withdrawn.headers['set-cookie'][0], /Max-Age=0/);
  assert.equal((await send('/api/alert', { cookie })).status, 403);
});

test('local answers continue beyond ten and do not automatically enable a remote model', async (t) => {
  const { send, consent } = await fixture(t);
  const cookie = await consent();
  assert.equal((await send('/api/chat', { cookie, body: { a: question } })).status, 400);
  assert.equal((await send('/api/chat', { cookie, body: { question: 'x'.repeat(1100) } })).status, 413);
  for (let i = 0; i < 12; i += 1) {
    const response = await send('/api/chat', { cookie, body: { question } });
    assert.equal(response.status, 200);
    assert.match(response.json().answer, /데이터센터/);
  }
  assert.deepEqual((await send('/api/state', { cookie })).json(), {
    consented: true, mode: 'demo', router: 'demo', portfolioEnabled: true,
  });
});

test('withdrawal aborts an in-flight personal read and never replaces failure with a demo portfolio', async (t) => {
  let now = 0;
  let began;
  let result;
  const started = new Promise((resolve) => { began = resolve; });
  const done = new Promise((resolve) => { result = resolve; });
  let signal;
  const { send, consent } = await fixture(t, {
    now: () => now,
    readPortfolio: async (input) => {
      signal = input;
      began();
      return done;
    },
  });
  const cookie = await consent();
  assert.equal((await send('/api/state', { cookie })).json().mode, 'personal');
  const pending = send('/api/portfolio', { cookie });
  await started;
  assert.equal((await send('/api/portfolio', { cookie })).status, 409);
  assert.equal((await send('/api/disconnect', { cookie, body: {} })).status, 200);
  assert.equal(signal.aborted, true);
  result({ holdings: [], buyingPower: { krw: 0, usd: 0 } });
  assert.equal((await pending).status, 403);
  const second = await consent();
  now = 1_800_000;
  assert.equal((await send('/api/alert', { cookie: second })).status, 403);
});

test('personal mode returns only its configured data and an explicit access error', async (t) => {
  let denied = false;
  const { send, consent } = await fixture(t, {
    readPortfolio: async () => denied
      ? { error: 'toss_access_denied' }
      : { buyingPower: { krw: 100, usd: 20 }, holdings: [{ symbol: 'NVDA', currency: 'USD', marketValue: 42 }] },
  });
  const cookie = await consent();
  assert.equal((await send('/api/portfolio', { cookie })).json().holdings[0].marketValue, 42);
  denied = true;
  const failure = await send('/api/portfolio', { cookie });
  assert.equal(failure.status, 502);
  assert.deepEqual(failure.json(), { error: 'toss_access_denied' });
});
