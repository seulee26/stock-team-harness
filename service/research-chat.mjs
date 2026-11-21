const MAX_QUESTION_LENGTH = 240;
const BIZROUTER_URL = 'https://api.bizrouter.ai/v1/chat/completions';
const BIZROUTER_MODEL = 'bizrouter/route';
const PROVIDER_TIMEOUT_MS = 8_000;
const PROVIDER_RESPONSE_BYTES = 32_768;

const EDGAR = { title: '미국 SEC 공시 검색', url: 'https://www.sec.gov/edgar/search/' };
const PER = {
  title: '미국 SEC의 PER 설명',
  url: 'https://www.investor.gov/introduction-investing/investing-basics/glossary/price-earnings-pe-ratio',
};
const FINRA = {
  title: '미국 FINRA의 거래 비용 설명',
  url: 'https://syndication.finra.org/content/brokerage-and-advisory-accounts-factors-consider-when-choosing-account-type',
};
const KRX = {
  title: '한국거래소의 상품별 거래 비용 안내',
  url: 'https://www.krx.co.kr/contents/OPN/01/01030201/OPN01030201T3.jsp',
};
const FX = {
  title: '미국 SEC의 국제 투자와 환율 설명',
  url: 'https://www.investor.gov/introduction-investing/general-resources/news-alerts/alerts-bulletins/investor-bulletins/international-investing',
};

const COMPANIES = {
  NVDA: {
    name: '엔비디아', aliases: ['엔비디아', 'nvidia'], url: 'https://investor.nvidia.com/',
    business: '데이터센터와 게이밍을 비롯한 가속 컴퓨팅 사업을 살펴보세요.',
    earnings: '데이터센터 매출, 매출총이익률, 다음 분기 회사 전망을 함께 보세요. 매출이 커져도 이익률이 낮아지면 이익의 증가 속도가 달라질 수 있습니다.',
    risk: '고객의 데이터센터 투자 변화, 수출 규제, 제품 전환기 공급 문제를 공시의 위험 요인에서 확인하세요.',
  },
  MSFT: {
    name: '마이크로소프트', aliases: ['마이크로소프트', 'microsoft'], url: 'https://www.microsoft.com/en-us/investor',
    business: 'Azure 클라우드와 Microsoft 365 같은 생산성 제품이 기업 고객에게 어떤 방식으로 매출을 만드는지 보세요.',
    earnings: 'Azure 성장률과 클라우드 투자에 들어간 설비 지출을 함께 보세요. 투자 확대가 현금흐름에 어떤 영향을 주는지 살펴보면 좋습니다.',
    risk: '클라우드 경쟁과 데이터센터 투자비, 사이버 보안 관련 위험을 확인하세요.',
  },
  AAPL: {
    name: '애플', aliases: ['애플', 'apple'], url: 'https://investor.apple.com/investor-relations/default.aspx',
    business: '아이폰 중심의 제품 사업과 앱·구독을 포함한 서비스 사업을 살펴보세요.',
    earnings: '아이폰 매출과 서비스 매출의 증가율, 제품과 서비스의 이익률을 비교하세요.',
    risk: '아이폰 수요와 공급망 의존도, 앱 생태계에 영향을 주는 규제를 확인하세요.',
  },
  GOOGL: {
    name: '알파벳 클래스 A', aliases: ['알파벳', '구글', 'alphabet', 'google'], url: 'https://abc.xyz/investor/',
    business: '검색과 유튜브 광고, 구글 클라우드가 각각 어떤 방식으로 매출을 만드는지 살펴보세요.',
    earnings: '검색과 유튜브 광고 매출, 구글 클라우드 이익, 데이터센터 투자비를 함께 보세요.',
    risk: '검색 경쟁과 광고 수요, 반독점 규제가 사업에 미칠 수 있는 영향을 확인하세요.',
  },
  GOOG: {
    name: '알파벳 클래스 C', url: 'https://abc.xyz/investor/',
    business: '클래스 C는 같은 알파벳의 주식 클래스입니다. 기업 실적은 공통이며 시세는 GOOG를 따로 확인하세요.',
    earnings: '검색과 유튜브 광고 매출, 구글 클라우드 이익, 데이터센터 투자비를 함께 보세요.',
    risk: '검색과 광고 사업의 위험 요인과 함께 클래스별 의결권 구조를 확인하세요.',
  },
  TSLA: {
    name: '테슬라', aliases: ['테슬라', 'tesla'], url: 'https://ir.tesla.com/',
    business: '전기차와 에너지 저장 사업을 나누어 살펴보면 사업별 수익 구조가 보입니다.',
    earnings: '차량 인도량, 자동차 부문 매출총이익률, 에너지 저장 사업의 매출과 이익을 확인하세요.',
    risk: '차량 가격 경쟁, 생산 계획과 실제 인도량의 차이, 자율주행 규제를 확인하세요.',
  },
  AMD: {
    name: 'AMD', aliases: ['에이엠디'], url: 'https://ir.amd.com/',
    business: '데이터센터, PC, 게임, 임베디드에 쓰이는 반도체 사업을 살펴보세요.',
    earnings: '데이터센터 매출과 매출총이익률을 확인하고, PC 수요가 다른 사업의 실적 변화와 어떤 관계인지 살펴보세요.',
    risk: '서버와 가속기 경쟁, 고객의 제품 채택 속도와 외부 생산 파트너 의존도를 확인하세요.',
  },
  AMZN: {
    name: '아마존', aliases: ['아마존', 'amazon'], url: 'https://ir.aboutamazon.com/overview/default.aspx',
    business: '전자상거래, 광고와 AWS 클라우드가 각각 매출과 이익에 어떻게 기여하는지 보세요.',
    earnings: 'AWS의 매출과 영업이익, 소매 영업이익, 설비 투자 후 남는 현금을 함께 보세요.',
    risk: '클라우드 경쟁, 물류 비용과 소비 둔화로 인한 수익성 변화를 확인하세요.',
  },
  META: {
    name: '메타', aliases: ['메타 플랫폼스', '메타'], url: 'https://investor.atmeta.com/home/default.aspx',
    business: '소셜 서비스에서 얻는 광고 수익과 Reality Labs 사업을 구분해 살펴보세요.',
    earnings: '광고 매출, 광고 노출당 가격, 설비 투자와 Reality Labs 영업손익을 함께 보세요.',
    risk: '광고 수요, 개인정보 규제, 데이터센터 설비 투자가 이익과 현금흐름에 미치는 영향을 확인하세요.',
  },
  PLTR: {
    name: '팔란티어', aliases: ['팔란티어', 'palantir'], url: 'https://investors.palantir.com/',
    business: '정부와 기업에 데이터 분석 소프트웨어를 제공하는 사업을 구분해 살펴보세요.',
    earnings: '정부 부문과 민간 부문의 매출 성장률, 영업이익률, 주식보상 비용을 함께 보세요.',
    risk: '대형 계약의 갱신과 계약 규모, 주식보상에 따른 주당 지분 희석을 확인하세요.',
  },
  ANT: {
    name: '앤트알파', aliases: ['앤트알파', '엔트알파', 'antalpha'], url: 'https://ir.antalpha.com/',
    business: '디지털자산 업계에 대출과 담보 관리 솔루션을 제공하는 기업입니다. 공시에서 대출과 기술 플랫폼의 수익 구조를 확인하세요.',
    earnings: '대출잔액, 이자 수익과 담보 구성의 변화를 함께 보세요. 분기 발표와 연차보고서의 기준일을 맞추면 비교하기 쉽습니다.',
    risk: '디지털자산 담보 가격의 변동과 차입자 집중, 대출의 회수 조건을 확인하세요.',
  },
};

const CONCEPTS = [
  {
    topic: '샘플 포트폴리오', match: /샘플\s*(?:계좌|포트폴리오)|가상\s*포트폴리오/u, local: true,
    points: ['보유 종목별 평가액부터 보세요. 평가액이 가장 큰 종목이 전체 수익률에 더 큰 영향을 줍니다.', '그다음 각 종목의 수익률과 원화·달러 주문 가능 금액을 확인하세요. 수익률은 비율이고, 주문 가능 금액은 새 주문에 쓸 수 있는 예시 금액입니다.'],
  },
  { topic: 'ANT 샘플 주가 조건', match: /(?:\bANT\b|앤트알파).*샘플.*(?:종가|저가|조건)|샘플.*(?:종가|저가|주가\s*조건).*충족/iu, local: true },
  {
    topic: '미국주식 매도 비용 구성', match: /(?:미국|해외)\s*주식.*(?:매도\s*비용|매도\s*수수료|거래\s*비용)/u,
    points: ['미국주식을 매도할 때는 증권사 거래 수수료와 매도에 붙을 수 있는 유관기관 비용을 확인하세요.', '매도 대금을 원화로 바꾼다면 환전 비용도 살펴보세요. 실제 비용은 증권사와 거래 시점, 환전 여부 등에 따라 달라집니다.'], sources: [FINRA],
  },
  {
    topic: '국내 주식 매도 비용 구성', match: /(?:국내|한국)\s*주식.*(?:매도\s*비용|매도\s*수수료|거래\s*비용)/u,
    points: ['국내 주식 매도 때는 증권사 수수료와 시장·상품에 따라 부과될 수 있는 세금을 확인합니다.', '거래 명세의 수수료에 유관기관 비용이 포함돼 있는지 확인하세요. 실제 요율은 증권사와 시장, 상품 및 거래 시점에 따라 달라집니다.'], sources: [KRX],
  },
  {
    topic: '정규장 종가와 장중 저가', match: /정규장.*종가.*장중.*저가|종가.*저가.*(?:차이|다른|뜻)/u,
    points: ['정규장 종가는 정규장이 끝날 때의 공식 가격입니다. 같은 날의 정규장 저가는 정규장 중 체결된 가격 가운데 가장 낮은 값입니다.', '종가 기준 조건과 장중 저가 기준 조건은 같은 날에도 서로 다르게 판정될 수 있습니다. 비교할 때는 미국 동부시간의 날짜와 정규장 기준을 맞추세요.'],
    sources: [{ title: '나스닥의 정규장 시세 예시', url: 'https://www.nasdaq.com/market-activity/stocks/nvda' }],
  },
  {
    topic: '환율과 원화 수익률', match: /(?:환율|달러).*?(?:수익률|환차|원화)|원화.*환율/u,
    points: ['달러 표시 주가가 같아도 1달러당 원화 값이 오르면 원화 환산 평가액이 늘고, 내리면 줄어듭니다.', '원화 수익률은 달러 주가의 변동과 원·달러 환율의 변동을 곱해 계산합니다. 원화 수익률 = (1 + 달러 수익률) × (매도 환율 ÷ 매수 환율) − 1입니다. 이 계산은 비용과 배당을 제외한 예시입니다.'], sources: [FX],
  },
  {
    topic: '실적이 좋아도 주가가 하락하는 이유', match: /(?:매출|실적|이익).*(?:늘|좋|증가|성장|올랐).*주가.*(?:떨어|내리|하락|빠지)/u,
    points: ['매출이 늘어도 시장의 기대치를 밑돌거나 회사가 다음 분기 전망을 낮추면 주가가 하락할 수 있습니다.', '매출 외에 이익률과 현금흐름을 보세요. 주가 움직임의 원인을 확인하려면 발표 전 기대와 발표 내용, 같은 시점의 시장 움직임도 비교해야 합니다.'],
  },
  {
    topic: '공시에서 실적을 확인하는 방법', match: /(?:기업\s*공시|EDGAR|SEC).*실적|실적.*(?:공시|EDGAR).*(?:어디|어떻게)/iu,
    points: ['기업의 투자자 관계 사이트에서 분기 실적 발표를 먼저 찾아 매출, 영업이익, 회사 전망을 확인하세요.', '미국 SEC EDGAR에서 티커로 검색하면 공시 원문을 찾을 수 있습니다. 미국 내국 등록 발행사의 대표 서류는 분기 10-Q, 연간 10-K입니다. 외국 민간 발행사는 20-F와 6-K를 주로 확인합니다.'], sources: [EDGAR],
  },
  {
    topic: '주가수익비율 읽는 법', match: /주가수익비율|\bPER\b|\bP\/E\b/iu,
    points: ['PER은 주가를 주당순이익으로 나눈 값입니다. PER이 20배라면 주가가 계산에 사용한 주당순이익의 20배라는 뜻입니다.', '과거 실적 기준과 향후 예상 이익 기준을 구분하세요. 같은 업종과 같은 이익 기간을 비교하고 주당순이익이 적자라면 PER 해석에 유의하세요.'], sources: [PER],
  },
];

const TOPICS = [
  ['가치평가', /밸류에이션|가치\s*평가|저평가|고평가|주가수익비율|\b(?:P\/E|PER|valuation)\b/iu],
  ['주가', /주가|시세|종가|등락|\bprice\b/iu],
  ['리스크', /리스크|위험|우려|악재|\brisk\b/iu],
  ['실적', /실적|매출|재무|현금흐름|가이던스|영업이익|이익률|분기|\bearnings\b/iu],
  ['공시', /공시|뉴스|발표|일정|\bnews\b/iu],
  ['기업 개요', /기업|어때|어떤|무엇|무슨|개요|분석|요약|설명|알려|사업|리서치|체크\s*포인트|\b(?:overview|research)\b/iu],
];

const PRIVATE_PATTERNS = [
  /[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}|(?:\d[ -]?){8,}|https?:\/\//iu,
  /sk-[A-Za-z0-9_-]{8,}|\b(?:api[\s_-]*key|secret|bearer|token|password)\b/iu,
  /비밀번호|인증번호|주민\s*등록|계좌\s*번호|카드\s*번호|API\s*키|시크릿|토큰/u,
  /(?:내|제|개인|실제)\s*(?:계좌|포트폴리오|보유|평단|잔고|자산|수익률|매수\s*내역)/u,
  /\b(?:my|private)\s+(?:account|holdings|portfolio|transactions|balance)\b/iu,
];
const CONTROL_CONTENT = /[\x00-\x08\x0b-\x1f\x7f\p{Cf}]/u;

export class ResearchChatError extends Error {
  constructor(status, code, message) {
    super(message);
    this.name = 'ResearchChatError';
    this.status = status;
    this.code = code;
  }
}

export { ResearchChatError as ChatError };

export function researchChatConfig(env = process.env) {
  const external = env.RESEARCH_CHAT_PROVIDER === 'bizrouter' && Boolean(env.BIZROUTER_API_KEY?.trim());
  return {
    mode: external ? 'bizrouter' : 'demo',
    external,
    maxQuestionLength: MAX_QUESTION_LENGTH,
    privacyNotice: external
      ? '공개 리서치 답변을 정리할 때 선택된 주제, 공개 종목 기호와 공개 설명 자료를 BizRouter로 보냅니다. 질문 원문과 샘플 계좌 내용은 보내지 않습니다.'
      : '예시 답변과 공식 자료 확인 방법을 제공합니다. 질문은 외부 AI에 보내지 않습니다.',
  };
}

function validateInput(input) {
  if (!input || typeof input !== 'object' || Array.isArray(input) ||
      Object.keys(input).length !== 1 || typeof input.question !== 'string') {
    throw new ResearchChatError(400, 'invalid_question', '질문을 입력해 주세요.');
  }
  if (input.question.length > MAX_QUESTION_LENGTH) {
    throw new ResearchChatError(400, 'question_too_long', `질문은 ${MAX_QUESTION_LENGTH}자 이내로 입력해 주세요.`);
  }
  const question = input.question.normalize('NFKC').trim().replace(/\s+/gu, ' ');
  if (!question || question.length > MAX_QUESTION_LENGTH || CONTROL_CONTENT.test(input.question)) {
    throw new ResearchChatError(400, 'invalid_question', '주식 질문을 한두 문장으로 입력해 주세요.');
  }
  if (PRIVATE_PATTERNS.some((pattern) => pattern.test(question))) {
    throw new ResearchChatError(400, 'private_input', '계좌·개인정보와 비밀 키를 지운 뒤 공개 종목이나 주식 개념에 대해 질문해 주세요.');
  }
  return question;
}

function findTickers(question) {
  // Alphabet has two share classes. An explicit ticker takes precedence over its aliases.
  const explicit = question.toUpperCase().match(/\b[A-Z]{2,5}\b/g) ?? [];
  const tickers = explicit.filter((symbol) => Object.hasOwn(COMPANIES, symbol));
  const lower = question.toLowerCase();
  for (const [ticker, company] of Object.entries(COMPANIES)) {
    if (ticker === 'GOOGL' && tickers.includes('GOOG')) continue;
    if (company.aliases?.some((alias) => /^[a-z]/u.test(alias)
      ? new RegExp(`\\b${alias}\\b`, 'u').test(lower)
      : lower.includes(alias))) tickers.push(ticker);
  }
  return [...new Set(tickers)];
}

function sampleAlertPoints(alert) {
  if (!alert || alert.symbol !== 'ANT') {
    return ['주가 조건 탭에서 ANT의 예시 종가와 조건 충족 횟수를 확인하세요. 이 답변에는 샘플 값이 전달되지 않았습니다.'];
  }
  const close = alert.close.toFixed(2);
  const threshold = alert.threshold.toFixed(2);
  const minimumLow = alert.minimumLow.toFixed(2);
  const status = alert.matchedSessions >= alert.requiredSessions ? '충족했습니다' : '아직 충족하지 못했습니다';
  return [
    `ANT 샘플 조건은 ${status}. 최근 샘플 종가 $${close}, 충족 횟수는 ${alert.requiredSessions}회 중 ${alert.matchedSessions}회입니다.`,
    `조건은 정규장 종가 $${threshold} 초과와 장중 저가 $${minimumLow} 이상입니다. 주가 조건 탭과 동일한 가상 데이터입니다.`,
  ];
}

function companyPlan(tickers, topic) {
  const sources = [...new Map(tickers.map((ticker) => {
    const { name, url } = COMPANIES[ticker];
    return [url, { title: `${name} 투자자 관계`, url }];
  })).values()];
  const points = tickers.map((ticker) => {
    const { name, business, earnings, risk } = COMPANIES[ticker];
    const intro = `${name}(${ticker})`;
    if (topic === '실적' || topic === '비교') return `${intro} 실적. ${earnings}`;
    if (topic === '리스크') return `${intro}의 위험 요인입니다. ${risk}`;
    if (topic === '주가') return `${intro}의 가격은 연결된 나스닥 시세에서 거래일과 세션을 확인하세요. 이 채팅은 현재 시세를 조회하지 않습니다.`;
    if (topic === '공시') return `${intro}의 공식 투자자 관계 페이지에서 실적 발표와 공시를 찾아보세요. 이 채팅은 최근 공시를 조회하지 않습니다.`;
    if (topic === '가치평가') return `${intro}의 가치평가에는 같은 시점의 주가와 같은 기간의 주당이익이 필요합니다. 비교 기업의 성장률과 이익률도 함께 확인하세요.`;
    return `${intro} 사업. ${business}`;
  });
  if (topic === '실적') points.push('실제 발표 수치는 투자자 관계 자료에서 회계기간과 발표 날짜를 확인하세요. 이 채팅은 최신 수치를 조회하지 않습니다.');
  if (topic === '비교') points.push('두 기업의 지표는 같은 회계기간과 기준으로 비교하세요. 각 회사에서 성장을 이끄는 사업이 다르면 같은 지표의 의미도 달라집니다.');
  if (topic === '기업 개요') points.push('기업의 투자자 관계 사이트에서 실적 자료를 찾아 사업별 매출과 이익을 확인할 수 있습니다.');
  if (topic === '주가') points.push('정규장 종가와 시간외 가격을 구분하고, 같은 종목을 비교할 때는 미국 동부시간과 USD 기준을 맞추세요.');
  if (topic === '가치평가') points.push('PER을 비교할 때는 과거 실적과 전망치 중 어떤 이익을 사용했는지 확인하세요. 현재 배수는 시세를 확인한 뒤 계산할 수 있습니다.');
  if (topic === '리스크') points.push('정기 공시의 위험 요인과 경영진 설명을 함께 읽으면 회사가 언급한 위험의 원인과 영향을 확인할 수 있습니다.');
  if (topic === '공시') points.push('실적 발표 날짜와 회계기간을 구분하고, 수치가 회사 전망인지 이미 발표된 실적인지 확인하세요.');
  if (topic === '리스크' || topic === '공시') sources.push(EDGAR);
  if (topic === '가치평가') sources.push(PER);
  if (topic === '주가') sources.unshift(...tickers.map((ticker) => ({
    title: `나스닥 ${ticker} 시세`, url: `https://www.nasdaq.com/market-activity/stocks/${ticker.toLowerCase()}`,
  })));
  return { tickers, topic, points, sources };
}

function planQuestion(question, sampleAlert) {
  const tickers = findTickers(question);
  if (tickers.length > 2) throw new ResearchChatError(400, 'unsupported_question', '한 번에 미국 상장 종목을 두 개까지 비교할 수 있습니다.');
  const concept = CONCEPTS.find(({ topic, match, local }) =>
    (local || tickers.length === 0 || topic.includes('매도 비용')) && match.test(question));
  if (concept) {
    const { topic, local, sources = [], points = sampleAlertPoints(sampleAlert) } = concept;
    return { tickers, topic, local, points, sources };
  }
  const compare = /비교|차이|\bversus\b|\bvs\b/iu.test(question);
  if (compare && tickers.length === 1) {
    throw new ResearchChatError(400, 'unsupported_question', '비교할 미국 상장 종목의 티커를 두 개 입력해 주세요. 예를 들어 NVDA와 AMD를 비교할 수 있습니다.');
  }
  const topic = compare ? '비교' : TOPICS.find(([, match]) => match.test(question))?.[0];
  const bareTicker = /^(?:\$?[A-Z]{2,5}|[가-힣A-Za-z]+)[?.!]?$/u.test(question);
  if (tickers.length && (topic || bareTicker)) return companyPlan(tickers, topic ?? '기업 개요');
  throw new ResearchChatError(400, 'unsupported_question', '지원하는 미국 상장 종목이나 공개 주식 개념을 입력해 주세요. 예를 들어 ‘NVDA 실적’, ‘MSFT와 AMZN 비교’, ‘PER 읽는 법’을 물을 수 있습니다.');
}

async function readProviderJson(response) {
  const decoder = new TextDecoder();
  let bytes = 0;
  let text = '';
  for await (const chunk of response.body) {
    bytes += chunk.byteLength;
    if (bytes > PROVIDER_RESPONSE_BYTES) throw new Error('Provider response exceeds size limit');
    text += decoder.decode(chunk, { stream: true });
  }
  return JSON.parse(text + decoder.decode());
}

async function chooseAnswerOrder(plan, env, fetchImpl, signal) {
  const deadline = AbortSignal.timeout(PROVIDER_TIMEOUT_MS);
  const requestSignal = signal ? AbortSignal.any([signal, deadline]) : deadline;
  try {
    const response = await fetchImpl(BIZROUTER_URL, {
      method: 'POST', redirect: 'error', signal: requestSignal,
      headers: { Authorization: `Bearer ${env.BIZROUTER_API_KEY.trim()}`, 'Content-Type': 'application/json' },
      body: JSON.stringify({
        model: BIZROUTER_MODEL, max_tokens: 128, temperature: 0, stream: false,
        messages: [
          { role: 'system', content: '한국어 주식 공부 자료를 정리하는 편집자입니다. 사용자 질문에 답하는 핵심 항목을 먼저 배치하세요. 입력에 있는 항목을 빠짐없이 사용하세요. 출력은 1부터 시작하는 항목 번호의 JSON 배열 하나입니다. 그 외 텍스트나 새 사실을 출력하지 마세요.' },
          { role: 'user', content: JSON.stringify({ topic: plan.topic, tickers: plan.tickers, points: plan.points }) },
        ],
      }),
    });
    if (!response.ok) {
      await response.body?.cancel();
      const status = response.status === 429 ? 503 : 502;
      throw new ResearchChatError(status, 'provider_unavailable', '리서치 AI에 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.');
    }
    const data = await readProviderJson(response);
    const result = data?.choices?.[0];
    if (result?.finish_reason !== 'stop' || typeof result.message?.content !== 'string') throw new Error('Unfinished provider response');
    const order = JSON.parse(result.message.content.trim());
    if (!Array.isArray(order) || order.length !== plan.points.length || new Set(order).size !== order.length ||
        order.some((index) => !Number.isInteger(index) || index < 1 || index > plan.points.length)) {
      throw new Error('Invalid provider answer order');
    }
    return order.map((index) => plan.points[index - 1]);
  } catch (error) {
    if (error instanceof ResearchChatError) throw error;
    if (requestSignal.aborted) {
      throw new ResearchChatError(504, 'provider_timeout', '리서치 AI의 응답이 늦어지고 있습니다. 잠시 후 다시 시도해 주세요.');
    }
    throw new ResearchChatError(502, 'provider_unavailable', '리서치 AI의 답변을 불러오지 못했습니다. 잠시 후 다시 시도해 주세요.');
  }
}

export async function answerResearchQuestion(input, {
  env = process.env, fetchImpl = globalThis.fetch, sampleAlert, signal,
} = {}) {
  const question = validateInput(input);
  const plan = planQuestion(question, sampleAlert);
  const external = !plan.local && plan.points.length > 1 && researchChatConfig(env).external;
  const points = external ? await chooseAnswerOrder(plan, env, fetchImpl, signal) : plan.points;
  return {
    mode: external ? 'bizrouter' : 'demo',
    answer: points.join('\n\n'),
    sources: plan.sources,
    tickers: plan.tickers,
  };
}
