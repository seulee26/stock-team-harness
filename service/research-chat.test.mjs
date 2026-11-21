import assert from 'node:assert/strict';
import { test } from 'node:test';
import { answerResearchQuestion, researchChatConfig, ResearchChatError } from './research-chat.mjs';

const demoEnv = {};
const providerEnv = { RESEARCH_CHAT_PROVIDER: 'bizrouter', BIZROUTER_API_KEY: 'mock-server-key' };
const sampleAlert = {
  symbol: 'ANT', close: 98.2, threshold: 99, minimumLow: 93, requiredSessions: 2, matchedSessions: 0,
};

function noNetwork() {
  assert.fail('Unexpected external request');
}

function providerResponse(content, finish_reason = 'stop') {
  return Response.json({ choices: [{ message: { content }, finish_reason }] });
}

test('provider setup requires explicit opt-in and a server key; config exposes no key', () => {
  assert.equal(researchChatConfig(demoEnv).mode, 'demo');
  assert.equal(researchChatConfig({ RESEARCH_CHAT_PROVIDER: 'bizrouter' }).mode, 'demo');
  assert.equal(researchChatConfig({ BIZROUTER_API_KEY: providerEnv.BIZROUTER_API_KEY }).mode, 'demo');
  const config = researchChatConfig(providerEnv);
  assert.equal(config.mode, 'bizrouter');
  assert.equal(config.external, true);
  assert.equal(config.maxQuestionLength, 240);
  assert.match(config.privacyNotice, /주제.+종목 기호.+BizRouter/u);
  assert.doesNotMatch(JSON.stringify(config), /mock-server-key/);
});

test('all ten UI question presets have specific Korean demo answers without a network call', async () => {
  const prompts = [
    ['샘플 포트폴리오에서 먼저 볼 것은 무엇인가요?', /평가액/u],
    ['엔비디아 실적을 볼 때 어떤 숫자가 중요한가요?', /데이터센터 매출/u],
    ['기업 공시에서 실적은 어디서 확인하나요?', /10-Q/u],
    ['주가수익비율(PER)은 어떻게 읽나요?', /주당순이익/u],
    ['매출이 늘어도 주가가 떨어지는 이유가 있나요?', /기대치/u],
    ['미국주식 매도 비용은 어떻게 구성되나요?', /환전 비용/u],
    ['국내 주식 매도 비용에 어떤 항목이 있나요?', /부과될 수 있는 세금/u],
    ['ANT 샘플 종가 조건은 충족했나요?', /\$98\.20.*2회 중 0회/u],
    ['정규장 종가와 장중 저가는 무엇이 다른가요?', /가장 낮은 값/u],
    ['달러 환율은 원화 수익률에 어떤 영향을 주나요?', /매도 환율 ÷ 매수 환율/u],
  ];
  for (const [question, expected] of prompts) {
    const result = await answerResearchQuestion({ question }, { env: demoEnv, fetchImpl: noNetwork, sampleAlert });
    assert.equal(result.mode, 'demo', question);
    assert.match(result.answer, expected, question);
    assert.ok(result.sources.every(({ url }) => new URL(url).protocol === 'https:'));
  }
});

test('known aliases, explicit share classes, quote limitations and earnings comparison are supported', async () => {
  const options = { env: demoEnv, fetchImpl: noNetwork };
  const comparison = await answerResearchQuestion({ question: '엔비디아와 AMD 비교' }, options);
  assert.deepEqual(new Set(comparison.tickers), new Set(['NVDA', 'AMD']));
  assert.match(comparison.answer, /같은 회계기간/u);
  assert.ok(comparison.sources.some(({ url }) => url === 'https://ir.amd.com/'));

  const quote = await answerResearchQuestion({ question: '알파벳 GOOG 지금 주가 알려줘' }, options);
  assert.deepEqual(quote.tickers, ['GOOG']);
  assert.match(quote.answer, /현재 시세를 조회하지 않습니다/u);
  assert.equal(quote.sources[0].url, 'https://www.nasdaq.com/market-activity/stocks/goog');

  const valuation = await answerResearchQuestion({ question: 'MSFT 주가수익비율(PER)은?' }, options);
  assert.match(valuation.answer, /주당이익/u);
  assert.ok(valuation.sources.some(({ url }) => url.includes('investor.gov')));
});

test('local sample questions remain local even when the provider is enabled', async () => {
  const env = providerEnv;
  const fetchImpl = noNetwork;
  const portfolio = await answerResearchQuestion({ question: '샘플 포트폴리오에서 먼저 볼 것은 무엇인가요?' }, { env, fetchImpl });
  assert.equal(portfolio.mode, 'demo');
  const alert = await answerResearchQuestion({ question: 'ANT 샘플 종가 조건은 충족했나요?' }, {
    env, fetchImpl, sampleAlert: { ...sampleAlert, matchedSessions: 2, close: 100.01 },
  });
  assert.equal(alert.mode, 'demo');
  assert.match(alert.answer, /충족했습니다.*\$100\.01.*2회 중 2회/u);
});

test('rejects unexpected fields, oversized questions, unrelated topics and private account details', async () => {
  const failures = [
    [{}, 'invalid_question'],
    [{ question: ' ' }, 'invalid_question'],
    [{ question: 'NVDA', model: 'other' }, 'invalid_question'],
    [{ question: `NVDA ${'실'.repeat(240)}` }, 'question_too_long'],
    [{ question: 'NVDA\u202e 실적' }, 'invalid_question'],
    [{ question: 'NVDA와 모르는 종목 비교' }, 'unsupported_question'],
    [{ question: 'NVDA와 AMD와 MSFT 비교' }, 'unsupported_question'],
    [{ question: '피자 요리법' }, 'unsupported_question'],
    [{ question: '내 계좌로 NVDA 실적 알려줘' }, 'private_input'],
    [{ question: 'NVDA 실적 example@example.com' }, 'private_input'],
    [{ question: 'NVDA 실적 ０１０－１２３４－５６７８' }, 'private_input'],
    [{ question: 'NVDA 실적 ' + ['s', 'k-', 'Z'.repeat(16)].join('') }, 'private_input'],
    [{ question: 'NVDA 실적 https://target.invalid' }, 'private_input'],
  ];
  for (const [input, code] of failures) {
    await assert.rejects(answerResearchQuestion(input, { env: providerEnv, fetchImpl: noNetwork }), {
      name: 'ResearchChatError', status: 400, code,
    });
  }
});

test('provider receives only canonical public data and can order approved Korean paragraphs', async () => {
  let called = false;
  const result = await answerResearchQuestion({ question: '엔비디아 실적. 뒤의 비공개 문구 XYZ-PRIVATE-WORD는 무시' }, {
    env: providerEnv,
    fetchImpl: async (url, init) => {
      called = true;
      assert.equal(url, 'https://api.bizrouter.ai/v1/chat/completions');
      assert.equal(init.method, 'POST');
      assert.equal(init.redirect, 'error');
      assert.ok(init.signal instanceof AbortSignal);
      assert.equal(init.headers.Authorization, 'Bearer mock-server-key');
      assert.doesNotMatch(init.body, /XYZ-PRIVATE-WORD|mock-server-key|엔비디아 실적\./u);
      const request = JSON.parse(init.body);
      assert.equal(request.model, 'bizrouter/route');
      assert.equal(request.max_tokens, 128);
      assert.equal(request.stream, false);
      assert.equal(request.tools, undefined);
      assert.equal(request.messages.length, 2);
      const publicData = JSON.parse(request.messages[1].content);
      assert.equal(publicData.topic, '실적');
      assert.deepEqual(publicData.tickers, ['NVDA']);
      assert.match(publicData.points[0], /데이터센터 매출/u);
      return providerResponse('[2, 1]');
    },
  });
  assert.equal(called, true);
  assert.equal(result.mode, 'bizrouter');
  assert.match(result.answer, /^실제 발표 수치는/u);
  assert.match(result.answer, /엔비디아\(NVDA\)/u);
  assert.equal(result.sources[0].url, 'https://investor.nvidia.com/');
});

test('provider errors and untrusted content are replaced with safe public errors', async () => {
  const question = { question: 'NVDA 실적' };
  const cases = [
    [() => Response.json({ secret: 'mock-server-key' }, { status: 429 }), 503, 'provider_unavailable'],
    [() => Response.json({ secret: 'mock-server-key' }, { status: 401 }), 502, 'provider_unavailable'],
    [() => providerResponse('<script>alert(1)</script>'), 502, 'provider_unavailable'],
    [() => providerResponse('[1, 1]'), 502, 'provider_unavailable'],
    [() => providerResponse('[1, 2]', 'length'), 502, 'provider_unavailable'],
    [() => new Response('x'.repeat(32_769)), 502, 'provider_unavailable'],
  ];
  for (const [respond, status, code] of cases) {
    await assert.rejects(answerResearchQuestion(question, { env: providerEnv, fetchImpl: async () => respond() }), (error) => {
      assert.ok(error instanceof ResearchChatError);
      assert.equal(error.status, status);
      assert.equal(error.code, code);
      assert.doesNotMatch(error.message, /mock-server-key|script/);
      return true;
    });
  }
});

test('provider requests can be cancelled through the server signal', async () => {
  const controller = new AbortController();
  const result = answerResearchQuestion({ question: 'NVDA 실적' }, {
    env: providerEnv,
    signal: controller.signal,
    fetchImpl: async (_url, init) => new Promise((resolve, reject) => {
      init.signal.addEventListener('abort', () => reject(init.signal.reason), { once: true });
    }),
  });
  controller.abort();
  await assert.rejects(result, { status: 504, code: 'provider_timeout' });
});
