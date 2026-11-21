"use strict";

const byId = (id) => document.getElementById(id);
const tabList = document.querySelector('.tab-list');
const tabs = [...tabList.querySelectorAll('[role="tab"]')];
const reloadButtons = [...document.querySelectorAll('[data-reload]')];
const consentButtons = ['accept-demo', 'decline-demo', 'disconnect-demo'].map(byId);
const feeMarket = byId('fee-market');
const feeAmount = byId('fee-amount');
const calculateFee = byId('calculate-fee');
const chatForm = byId('chat-form');
const chatQuestion = byId('chat-question');
const askQuestion = byId('ask-question');
const suggestions = [...chatForm.querySelectorAll('[data-suggestion]')];
const narrowLayout = matchMedia('(max-width: 780px)');
const number = new Intl.NumberFormat('ko-KR', { maximumFractionDigits: 8 });
const dollars = new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' });
const percent = new Intl.NumberFormat('ko-KR', {
  style: 'percent',
  signDisplay: 'exceptZero',
  maximumFractionDigits: 2,
});
const sampleAmounts = {
  KOSPI: [100000000, 10000000, 1000000],
  KOSDAQ: [100000000, 10000000, 1000000],
  US: [10000, 1000, 100],
};
const toolTitles = {
  chat: '로컬 리서치 시작하기',
  portfolio: '샘플 포트폴리오 둘러보기',
  fee: '샘플 매도 비용 계산하기',
  alert: '샘플 주가 조건 확인하기',
};

let consented = null;
let selectedView = 'chat';
let sessionRevision = 0;
let chatBusy = false;
let personalMode = false;
let portfolioEnabled = false;
let changingConsent = false;
let checkingState = false;
const pending = new Set();
const loaded = new Set();

function money(amount, currency) {
  if (!Number.isFinite(amount)) return '—';
  if (currency === 'USD') return dollars.format(amount);
  if (currency === 'KRW') return `${number.format(amount)}원`;
  return `${number.format(amount)} ${currency ?? ''}`.trim();
}

async function request(path, body) {
  const options = { cache: 'no-store', credentials: 'same-origin' };
  if (body !== undefined) {
    options.method = 'POST';
    options.headers = { 'Content-Type': 'application/json' };
    options.body = JSON.stringify(body);
  }
  const response = await fetch(path, options);
  if (!response.ok) {
    const error = new Error('로컬 앱 요청에 실패했습니다.');
    error.status = response.status;
    throw error;
  }
  return response.json();
}

function showPanels() {
  byId('consent-card').hidden = consented !== false;
  byId('consent-title').textContent = personalMode && selectedView === 'portfolio'
    ? '내 포트폴리오 조회 시작하기'
    : toolTitles[selectedView];
  byId('session-footer').hidden = consented !== true;
  for (const tab of tabs) {
    byId(tab.getAttribute('aria-controls')).hidden = consented !== true || tab.dataset.view !== selectedView;
  }
}

function clearPortfolio() {
  byId('portfolio-data').hidden = true;
  for (const id of ['buying-krw', 'buying-usd', 'holding-count', 'holding-rows']) byId(id).replaceChildren();
}

function clearLocalData() {
  loaded.clear();
  pending.clear();
  for (const view of ['chat', 'portfolio', 'alert', 'fee']) {
    byId(`${view}-message`).textContent = '';
    byId(`${view}-panel`).removeAttribute('aria-busy');
  }
  clearPortfolio();
  for (const id of ['alert-data', 'fee-result']) byId(id).hidden = true;
  for (const id of [
    'fee-total', 'fee-base', 'fee-commission', 'fee-tax',
    'alert-symbol', 'alert-status', 'alert-close', 'alert-threshold', 'alert-low', 'alert-progress-count',
  ]) byId(id).replaceChildren();
  byId('alert-progress').max = 1;
  byId('alert-progress').value = 0;
  byId('chat-log').replaceChildren();
  byId('chat-log').hidden = true;
  chatForm.reset();
  setChatBusy(false);
  for (const button of reloadButtons) button.disabled = button.dataset.reload === 'portfolio' && !portfolioEnabled;
  setFeeBusy(false);
  byId('fee-form').reset();
  syncFeeAmounts();
}

function setLocalMode(state) {
  if (typeof state.portfolioEnabled !== 'boolean') return false;
  const usesPersonalAccount = state.mode === 'personal';
  const usesBizRouter = state.router === 'bizrouter';
  const changed = personalMode !== usesPersonalAccount || portfolioEnabled !== state.portfolioEnabled;
  personalMode = usesPersonalAccount;
  portfolioEnabled = state.portfolioEnabled;
  if (changed && consented) {
    sessionRevision += 1;
    clearLocalData();
  }

  byId('app-mode').textContent = personalMode ? '개인 계좌 모드' : '샘플 데이터 모드';
  byId('app-mode-detail').textContent = personalMode
    ? '이 컴퓨터의 토스증권 연결을 사용합니다.'
    : '가상 포트폴리오와 예시 숫자로 실행합니다.';
  byId('consent-scope').textContent = personalMode
    ? '이 컴퓨터의 토스증권 연결로 계좌를 조회합니다. 매도 비용과 주가 조건은 샘플입니다.'
    : '이 컴퓨터에서 가상 포트폴리오와 샘플 매도 비용, 주가 조건을 조회합니다.';
  byId('portfolio-title').textContent = personalMode ? '내 포트폴리오' : '샘플 포트폴리오';
  byId('portfolio-detail').textContent = personalMode
    ? '토스증권 계좌의 주문 가능 금액과 보유 종목입니다.'
    : '가상 계좌의 주문 가능 금액과 보유 종목입니다.';
  byId('portfolio-unavailable').hidden = portfolioEnabled;
  if (!pending.has('portfolio')) {
    reloadButtons.find((button) => button.dataset.reload === 'portfolio').disabled = !portfolioEnabled;
  }

  const router = byId('chat-router');
  router.textContent = usesBizRouter ? 'BizRouter 사용 중' : '예시 답변 모드';
  router.classList.toggle('active', usesBizRouter);
  const chatDetail = usesBizRouter
    ? '선택한 예시 질문을 BizRouter로 보내 답변을 생성합니다.'
    : '선택한 질문에 이 컴퓨터에서 예시 답변을 보여줍니다.';
  byId('consent-chat-detail').textContent = chatDetail;
  byId('chat-note').textContent = chatDetail;
  if (changed) showPanels();
  return changed;
}

function setSession(next, message = '') {
  if (consented !== next) {
    sessionRevision += 1;
    if (!next) clearLocalData();
  }
  consented = next;
  byId('demo-body').setAttribute('aria-busy', 'false');
  byId('startup-error').hidden = true;
  byId('consent-message').textContent = message;
  const status = byId('session-status');
  status.textContent = next ? '로컬 세션 이용 중' : '로컬 세션 동의 전';
  status.classList.toggle('active', next);
  showPanels();
  if (next) ensureView();
}

async function checkState() {
  if (checkingState || changingConsent) return;
  checkingState = true;
  const revision = sessionRevision;
  const retry = byId('retry-state');
  retry.disabled = true;
  try {
    const result = await request('/api/state');
    if (revision !== sessionRevision || changingConsent) return;
    if (typeof result.consented !== 'boolean') throw new Error('Invalid consent state');
    const modeChanged = setLocalMode(result);
    if (result.consented !== consented) {
      const expired = consented === true && !result.consented;
      const moveFocus = expired && byId('demo-body').contains(document.activeElement);
      setSession(result.consented, expired ? '로컬 세션 동의가 만료되었습니다. 계속하려면 다시 동의해 주세요.' : '');
      if (moveFocus) byId('accept-demo').focus();
    } else if (modeChanged && result.consented) {
      ensureView();
    }
  } catch {
    if (consented !== null) return;
    byId('demo-body').setAttribute('aria-busy', 'false');
    byId('session-status').textContent = '동의 상태 확인 실패';
    byId('startup-error').hidden = false;
  } finally {
    checkingState = false;
    retry.disabled = false;
  }
}

async function changeConsent(next) {
  if (changingConsent) return;
  changingConsent = true;
  for (const button of consentButtons) button.disabled = true;
  const status = byId(next ? 'consent-message' : 'disconnect-message');
  status.textContent = next ? '로컬 세션을 시작하는 중입니다…' : '동의를 철회하는 중입니다…';
  try {
    const result = next
      ? await request('/api/consent', { accepted: true })
      : await request('/api/disconnect', {});
    if (result.consented !== next) throw new Error('Invalid consent response');
    setLocalMode(result);
    setSession(next, next ? '' : '동의를 철회했습니다. 화면에 표시된 조회 결과를 지웠습니다.');
    if (next) byId(`${selectedView}-panel`).focus();
    status.textContent = next ? '' : '로컬 세션 동의는 최대 30분 동안 유지됩니다.';
  } catch {
    status.textContent = next
      ? '로컬 세션을 시작하지 못했습니다. 다시 시도해 주세요.'
      : '동의를 철회하지 못했습니다. 다시 시도해 주세요.';
  } finally {
    changingConsent = false;
    for (const button of consentButtons) button.disabled = false;
    if (!next && consented === false) byId('accept-demo').focus();
  }
}

function selectTab(tab) {
  selectedView = tab.dataset.view;
  for (const item of tabs) {
    item.setAttribute('aria-selected', String(item === tab));
    item.tabIndex = item === tab ? 0 : -1;
  }
  showPanels();
  ensureView();
}

function ensureView() {
  if (!consented || selectedView === 'chat' || selectedView === 'fee' || loaded.has(selectedView)) return;
  loadView(selectedView);
}

async function describeFailure(error, revision, message) {
  if (error.status === 401 || error.status === 403) await checkState();
  if (revision === sessionRevision) {
    message.textContent = message.id === 'portfolio-message' && personalMode
      ? '개인 계좌를 조회하지 못했습니다. 이 컴퓨터의 토스증권 연결을 확인해 주세요.'
      : '결과를 불러오지 못했습니다. 다시 시도해 주세요.';
  }
}

async function loadView(view) {
  if (!consented || pending.has(view) || (view === 'portfolio' && !portfolioEnabled)) return;
  const panel = byId(`${view}-panel`);
  const message = byId(`${view}-message`);
  const reload = reloadButtons.find((button) => button.dataset.reload === view);
  const revision = sessionRevision;
  pending.add(view);
  loaded.delete(view);
  if (view === 'portfolio') clearPortfolio();
  reload.disabled = true;
  panel.setAttribute('aria-busy', 'true');
  message.textContent = view === 'portfolio' && personalMode
    ? '개인 계좌를 조회하는 중입니다…'
    : '샘플 데이터를 불러오는 중입니다…';
  try {
    const data = await request(`/api/${view}`);
    if (revision !== sessionRevision) return;
    if (view === 'portfolio') renderPortfolio(data);
    else renderAlert(data);
    loaded.add(view);
    message.textContent = '';
  } catch (error) {
    if (revision === sessionRevision) await describeFailure(error, revision, message);
  } finally {
    if (revision === sessionRevision) {
      pending.delete(view);
      reload.disabled = false;
      panel.removeAttribute('aria-busy');
    }
  }
}

function cell(tag, value, className = '') {
  const element = document.createElement(tag);
  element.className = className;
  element.textContent = value;
  return element;
}

function setChatBusy(busy) {
  chatBusy = busy;
  chatQuestion.disabled = busy;
  askQuestion.disabled = busy || !chatQuestion.value;
  for (const suggestion of suggestions) suggestion.disabled = busy;
  byId('chat-panel').setAttribute('aria-busy', String(busy));
}

function appendTurn(question, data) {
  const turn = document.createElement('article');
  turn.className = 'chat-turn';
  const answer = document.createElement('div');
  answer.className = 'chat-answer';
  answer.append(
    cell('h3', data.mode === 'bizrouter' ? '리서치 팀 · BizRouter' : '리서치 팀 · 샘플 답변'),
    cell('p', data.answer),
  );
  const sources = document.createElement('ul');
  sources.className = 'chat-sources';
  if (Array.isArray(data.sources)) {
    for (const source of data.sources) {
      const title = source?.title;
      const href = source?.url;
      if (typeof title !== 'string' || typeof href !== 'string') continue;
      let url;
      try {
        url = new URL(href);
      } catch {
        continue;
      }
      if (url.protocol !== 'https:' || url.username || url.password) continue;
      const link = cell('a', title);
      link.href = url.href;
      link.rel = 'noreferrer noopener';
      link.target = '_blank';
      const item = document.createElement('li');
      item.append(link);
      sources.append(item);
    }
  }
  if (sources.childElementCount) {
    sources.setAttribute('aria-label', '답변 출처');
    answer.append(sources);
  }
  turn.append(cell('p', question, 'chat-question'), answer);
  const log = byId('chat-log');
  log.hidden = false;
  log.append(turn);
  log.scrollTop = log.scrollHeight;
}

async function chatSubmit(event) {
  event.preventDefault();
  if (!consented || askQuestion.disabled) return;
  const revision = sessionRevision;
  const question = chatQuestion.value;
  const message = byId('chat-message');
  setChatBusy(true);
  message.textContent = '리서치 팀이 답변을 준비하고 있습니다…';
  try {
    const data = await request('/api/chat', { question });
    if (revision !== sessionRevision) return;
    appendTurn(question, data);
    message.textContent = '';
  } catch (error) {
    if (revision === sessionRevision) await describeFailure(error, revision, message);
  } finally {
    if (revision === sessionRevision) {
      setChatBusy(false);
      if (selectedView === 'chat') chatQuestion.focus();
    }
  }
}

function renderPortfolio(data) {
  const rows = data.holdings.map((holding) => {
    const row = document.createElement('tr');
    const company = cell('th', '', 'company');
    company.scope = 'row';
    company.append(cell('span', holding.symbol, 'company-symbol'), cell('span', holding.name ?? '', 'company-name'));
    const returnClass = holding.returnPct > 0 ? 'positive' : holding.returnPct < 0 ? 'negative' : '';
    row.append(
      company,
      cell('td', Number.isFinite(holding.quantity) ? number.format(holding.quantity) : '—'),
      cell('td', money(holding.marketValue, holding.currency)),
      cell('td', Number.isFinite(holding.returnPct) ? percent.format(holding.returnPct / 100) : '—', returnClass),
    );
    return row;
  });
  if (!rows.length) {
    const row = document.createElement('tr');
    const empty = cell('td', '보유 종목이 없습니다.');
    empty.colSpan = 4;
    row.append(empty);
    rows.push(row);
  }
  byId('holding-rows').replaceChildren(...rows);
  byId('buying-krw').textContent = money(data.buyingPower?.krw, 'KRW');
  byId('buying-usd').textContent = money(data.buyingPower?.usd, 'USD');
  byId('holding-count').textContent = `${number.format(data.holdings.length)}종목`;
  byId('portfolio-data').hidden = false;
}

function renderAlert(data) {
  const matched = data.state === 'satisfied';
  byId('alert-symbol').textContent = data.symbol;
  byId('alert-status').textContent = matched ? '조건 충족' : '조건 대기';
  byId('alert-status').classList.toggle('active', matched);
  byId('alert-close').textContent = money(data.close, 'USD');
  byId('alert-threshold').textContent = money(data.threshold, 'USD');
  byId('alert-low').textContent = money(data.minimumLow, 'USD');
  byId('alert-progress-count').textContent = `${number.format(data.matchedSessions)} / ${number.format(data.requiredSessions)}거래일`;
  byId('alert-progress').max = data.requiredSessions;
  byId('alert-progress').value = data.matchedSessions;
  byId('alert-data').hidden = false;
}

function syncFeeAmounts() {
  const currency = feeMarket.value === 'US' ? 'USD' : 'KRW';
  feeAmount.replaceChildren(...sampleAmounts[feeMarket.value].map((amount) => new Option(money(amount, currency), amount)));
  byId('fee-result').hidden = true;
  byId('fee-message').textContent = '';
}

function setFeeBusy(busy) {
  for (const control of [feeMarket, feeAmount, calculateFee]) control.disabled = busy;
  byId('fee-panel').setAttribute('aria-busy', String(busy));
}

async function feeSubmit(event) {
  event.preventDefault();
  if (!consented || calculateFee.disabled) return;
  const revision = sessionRevision;
  const input = { market: feeMarket.value, amount: Number(feeAmount.value) };
  const message = byId('fee-message');
  byId('fee-result').hidden = true;
  setFeeBusy(true);
  message.textContent = '샘플 매도 비용을 계산하는 중입니다…';
  try {
    const data = await request('/api/fee', input);
    if (revision !== sessionRevision) return;
    byId('fee-total').textContent = money(data.estimatedCost, data.currency);
    byId('fee-base').textContent = money(data.amount, data.currency);
    byId('fee-commission').textContent = money(data.commission, data.currency);
    byId('fee-tax').textContent = money(data.tax, data.currency);
    byId('fee-result').hidden = false;
    message.textContent = `예상 총비용은 ${money(data.estimatedCost, data.currency)}입니다.`;
  } catch (error) {
    if (revision === sessionRevision) await describeFailure(error, revision, message);
  } finally {
    if (revision === sessionRevision) setFeeBusy(false);
  }
}

tabList.addEventListener('click', (event) => {
  const tab = event.target.closest('[role="tab"]');
  if (tab) selectTab(tab);
});
tabList.addEventListener('keydown', (event) => {
  const index = tabs.indexOf(event.target);
  const nextByKey = {
    [narrowLayout.matches ? 'ArrowLeft' : 'ArrowUp']: (index + tabs.length - 1) % tabs.length,
    [narrowLayout.matches ? 'ArrowRight' : 'ArrowDown']: (index + 1) % tabs.length,
    Home: 0,
    End: tabs.length - 1,
  };
  if (index === -1 || !Object.hasOwn(nextByKey, event.key)) return;
  event.preventDefault();
  const next = tabs[nextByKey[event.key]];
  selectTab(next);
  next.focus();
});
byId('accept-demo').addEventListener('click', () => changeConsent(true));
byId('decline-demo').addEventListener('click', () => {
  byId('consent-message').textContent = '동의하지 않았습니다. 안내는 계속 읽을 수 있습니다.';
});
byId('disconnect-demo').addEventListener('click', () => changeConsent(false));
byId('retry-state').addEventListener('click', checkState);
chatForm.addEventListener('submit', chatSubmit);
chatQuestion.addEventListener('change', () => setChatBusy(chatBusy));
for (const suggestion of suggestions) {
  suggestion.addEventListener('click', () => {
    chatQuestion.value = byId(suggestion.dataset.suggestion).value;
    setChatBusy(chatBusy);
    askQuestion.focus();
  });
}
byId('fee-form').addEventListener('submit', feeSubmit);
feeMarket.addEventListener('change', syncFeeAmounts);
feeAmount.addEventListener('change', () => {
  byId('fee-result').hidden = true;
  byId('fee-message').textContent = '';
});
for (const button of reloadButtons) {
  button.addEventListener('click', () => loadView(button.dataset.reload));
}
document.addEventListener('visibilitychange', () => {
  if (!document.hidden) checkState();
});
window.addEventListener('focus', checkState);
window.setInterval(() => {
  if (consented && !document.hidden) checkState();
}, 30000);

function syncTabOrientation() {
  tabList.setAttribute('aria-orientation', narrowLayout.matches ? 'horizontal' : 'vertical');
}
narrowLayout.addEventListener('change', syncTabOrientation);

syncFeeAmounts();
syncTabOrientation();
setChatBusy(false);
checkState();
