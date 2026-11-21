"""Korean investor tax calculators. General information from dated rules, not tax advice."""

import argparse
import calendar
from datetime import date, datetime, timedelta
import json
import math
from pathlib import Path
import re

from quant import read_bars
from toss_client import HarnessError
from workflows import KST


RULES = Path(__file__).with_name("tax-rules-kr.json")
RELATIONS = {
    "spouse": "배우자", "child-adult": "성인 자녀 (부모·조부모에게서 받음)",
    "child-minor": "미성년 자녀 (부모·조부모에게서 받음)", "parent": "부모 (자녀에게서 받음)",
    "relative": "그 밖의 친족", "other": "친족이 아닌 사람",
}
MARKETS = {"kospi": "코스피", "kosdaq": "코스닥", "konex": "코넥스", "kotc": "K-OTC", "otc": "비상장·장외"}


def rules():
    return json.loads(RULES.read_text(encoding="utf-8"))


def won(value, label, allow_zero=True):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
        raise HarnessError(f"{label} 값은 원 단위 숫자로 입력해 주세요.")
    if value < 0 or (value == 0 and not allow_zero) or value > 10 ** 14:
        raise HarnessError(f"{label} 값은 0{'보다 큰' if not allow_zero else ' 이상의'} 금액으로 입력해 주세요.")
    return int(value)


def source(document, *ids):
    found = {rule["id"]: rule for rule in document["rules"]}
    return [{"title": found[key]["title"], "basis": found[key]["basis"], "url": found[key]["url"],
             "applies": found[key]["applies"]} for key in ids]


def envelope(document, result, *ids):
    checked = date.fromisoformat(document["checkedOn"])
    today = datetime.now(KST).date()
    stale = today.year != checked.year or (today - checked).days > 180
    return {
        "dataScope": "calculation-only", "rulesCheckedOn": document["checkedOn"], **result,
        "sources": source(document, *ids),
        "warnings": ([f"규칙을 확인한 지 오래됐습니다({document['checkedOn']}). 세법이 바뀌었는지 먼저 확인하세요."] if stale else [])
        + ["일반 정보를 바탕으로 한 계산이며 세무 자문이 아닙니다. 신고 전에 국세청 자료나 세무사에게 확인하세요."],
    }


def overseas_gain(gains, losses=0, domestic_taxable=0, small_business=False):
    """Capital gains tax on overseas shares for one calendar year."""
    document = rules()
    values = document["values"]
    gains, losses = won(gains, "양도차익"), won(losses, "양도손실")
    if isinstance(domestic_taxable, bool) or not isinstance(domestic_taxable, (int, float)) or not math.isfinite(domestic_taxable):
        raise HarnessError("국내 과세 대상 주식의 손익은 원 단위 숫자로 입력해 주세요.")
    net = gains - losses + int(domestic_taxable)
    base = max(net - values["overseasDeduction"], 0)
    rate = values["overseasRatePct"] / (2 if small_business else 1)
    tax = math.floor(base * rate / 100)
    return envelope(document, {
        "netGain": net, "basicDeduction": values["overseasDeduction"], "taxBase": base, "ratePct": rate,
        "tax": tax, "afterTax": net - tax,
        "filing": "다음 해 5월 1일~31일에 양도소득세 확정신고",
        "notes": ["1월 1일~12월 31일에 결제된 매도를 합쳐 계산합니다. 손실은 다음 해로 넘기지 못합니다.",
                  "차익은 원화로 계산합니다. 매수·매도 대금을 주고받은 날의 환율을 씁니다.",
                  "2026년에는 전용 계좌로 판 해외주식에 한시 감면이 있습니다. 조건이 까다로우니 따로 확인하세요."],
    }, "overseas-deduction", "overseas-rate", "overseas-netting", "overseas-filing", "overseas-fx", "ria-relief")


def progressive(base, brackets):
    for limit, rate, deduction in brackets:
        if limit is None or base <= limit:
            return math.floor(base * rate / 100 - deduction), rate
    raise HarnessError("세율표를 읽지 못했습니다.")


def month_end(day, months):
    index = day.year * 12 + day.month - 1 + months
    year, month = divmod(index, 12)
    return date(year, month + 1, calendar.monthrange(year, month + 1)[1])


def gift(amount, relation, prior=0, prior_tax=0, deduction_used=0, marriage_birth=0, skip_generation=False, gift_date=None):
    """Gift tax for a resident recipient, including the ten-year aggregation."""
    document = rules()
    values = document["values"]
    if relation not in RELATIONS:
        raise HarnessError("관계는 " + ", ".join(RELATIONS) + " 중에서 골라 주세요.")
    amount = won(amount, "증여 금액", allow_zero=False)
    prior, prior_tax = won(prior, "10년 안에 같은 사람에게 받은 금액"), won(prior_tax, "이미 낸 증여세")
    deduction_used, marriage_birth = won(deduction_used, "다른 사람에게서 이미 쓴 공제"), won(marriage_birth, "혼인·출산 공제")
    if marriage_birth and relation not in ("child-adult", "child-minor"):
        raise HarnessError("혼인·출산 공제는 부모나 조부모에게서 받을 때만 쓸 수 있습니다.")
    if marriage_birth > values["marriageBirthLimit"]:
        raise HarnessError("혼인·출산 공제는 합쳐서 1억 원까지입니다.")
    if skip_generation and relation not in ("child-adult", "child-minor"):
        raise HarnessError("세대를 건너뛴 증여는 조부모가 손주에게 줄 때 해당합니다.")
    total = amount + prior
    limit = values["giftDeduction"][relation]
    deduction = min(max(limit - deduction_used, 0) + marriage_birth, total)
    base = max(total - deduction, 0)
    computed, rate = progressive(base, values["giftBrackets"]) if base else (0, 0)
    surcharge_rate = 0
    if skip_generation and computed:
        heavy = relation == "child-minor" and total > values["skipMinorThreshold"]
        surcharge_rate = values["skipSurchargeMinorPct"] if heavy else values["skipSurchargePct"]
    surcharge = math.floor(computed * surcharge_rate / 100)
    after_prior = max(computed + surcharge - prior_tax, 0)
    credit = math.floor(after_prior * values["filingCreditPct"] / 100)
    result = {
        "relation": RELATIONS[relation], "giftNow": amount, "priorGiftsWithin10Years": prior, "aggregated": total,
        "deduction": deduction, "deductionLimit": limit, "marriageBirthDeduction": marriage_birth,
        "taxBase": base, "topRatePct": rate, "computedTax": computed,
        "generationSkipSurcharge": surcharge, "priorTaxCredited": min(prior_tax, computed + surcharge),
        "filingCredit": credit, "taxDue": after_prior - credit,
        "taxFreeRoom": max(max(limit - deduction_used, 0) + marriage_birth - total, 0),
        "notes": ["공제 한도는 10년 동안 같은 관계의 사람들에게서 받은 것을 모두 합친 한도입니다.",
                  "부모는 부부를 한 사람으로 봅니다. 아버지와 어머니에게 따로 받아도 합칩니다.",
                  "이미 낸 증여세의 공제는 한도 계산을 생략한 단순 차감입니다. 실제 신고 때 달라질 수 있습니다.",
                  "세금이 0원이어도 신고해 두면 나중에 취득가액과 자금 출처를 증명하기 쉽습니다."],
    }
    if gift_date:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(gift_date)):
            raise HarnessError("증여일은 YYYY-MM-DD 형식으로 입력해 주세요.")
        try:
            result["filingDeadline"] = month_end(date.fromisoformat(gift_date), 3).isoformat()
        except ValueError:
            raise HarnessError("증여일은 달력에 있는 날로 입력해 주세요.") from None
    return envelope(document, result, "gift-deduction", "gift-marriage-birth", "gift-rates", "gift-aggregation",
                    "gift-skip", "gift-filing")


def gift_value(bars, gift_date):
    """Listed-share gift value: mean daily close for two months before and after the gift date."""
    document = rules()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", str(gift_date)):
        raise HarnessError("증여일은 YYYY-MM-DD 형식으로 입력해 주세요.")
    try:
        day = date.fromisoformat(gift_date)
    except ValueError:
        raise HarnessError("증여일은 달력에 있는 날로 입력해 주세요.") from None

    def shift(months):
        index = day.year * 12 + day.month - 1 + months
        year, month = divmod(index, 12)
        return date(year, month + 1, min(day.day, calendar.monthrange(year, month + 1)[1]))

    start, end = shift(-2) + timedelta(days=1), shift(2) - timedelta(days=1)
    window = [(when, close) for when, close in bars if start <= when <= end]
    if len(window) < 20:
        raise HarnessError("증여일 앞뒤 2개월의 일봉이 부족합니다. 그 기간이 들어 있는 CSV를 넣어 주세요.")
    last = max(when for when, _ in window)
    complete = last >= end - timedelta(days=6)
    return envelope(document, {
        "giftDate": day.isoformat(), "window": {"start": start.isoformat(), "end": end.isoformat()},
        "tradingDays": len(window), "averageClose": round(sum(close for _, close in window) / len(window), 4),
        "complete": complete,
        "notes": ["증여일 앞뒤 각 2개월 동안의 매일 종가를 평균한 값이 한 주의 평가액입니다.",
                  "수정주가가 아닌 실제 종가로 계산해야 합니다. 넣은 CSV가 수정주가라면 값이 달라질 수 있습니다.",
                  "해외 상장주식은 법에 명시된 방식이 아니라 실무상 같은 방식을 준용하며, 평가기준일 환율로 환산합니다."]
        + ([] if complete else ["증여일 뒤 2개월이 아직 지나지 않아 임시 값입니다. 기간이 끝난 뒤 다시 계산하세요."]),
    }, "gift-stock-value", "gift-stock-value-overseas")


def transaction_tax(market, amount):
    document = rules()
    if market not in MARKETS:
        raise HarnessError("시장은 " + ", ".join(MARKETS) + " 중에서 골라 주세요.")
    amount = won(amount, "매도 금액", allow_zero=False)
    rate = document["values"]["transactionTaxPct"][market]
    return envelope(document, {"market": MARKETS[market], "saleAmount": amount, "ratePct": rate,
                               "tax": math.floor(amount * rate / 100),
                               "notes": ["팔 때만 냅니다. 증권사가 매도 대금에서 떼고 줍니다.",
                                         "증권사 수수료는 따로입니다. 계좌 요율로 계산하려면 stock_harness.py sale-fee를 쓰세요."]},
                    "transaction-tax", "domestic-listed")


def dividend(amount, foreign_withheld_pct=None, other_financial_income=0):
    document = rules()
    values = document["values"]
    amount, other = won(amount, "배당금", allow_zero=False), won(other_financial_income, "다른 이자·배당")
    if foreign_withheld_pct is None:
        withheld, detail = math.floor(amount * values["withholdingPct"] / 100), "국내에서 15.4% 원천징수"
    else:
        if not 0 <= foreign_withheld_pct <= 100:
            raise HarnessError("외국에서 뗀 세율은 0~100으로 입력해 주세요.")
        domestic = max(14 - foreign_withheld_pct, 0) * 1.1
        withheld = math.floor(amount * (foreign_withheld_pct + domestic) / 100)
        detail = f"외국에서 {foreign_withheld_pct}% 원천징수, 국내에서 {round(domestic, 2)}% 추가 원천징수"
    total = amount + other
    over = total > values["financialIncomeThreshold"]
    return envelope(document, {
        "dividend": amount, "withheld": withheld, "received": amount - withheld, "detail": detail,
        "financialIncomeThisYear": total, "comprehensiveTaxation": over,
        "notes": [("이자와 배당 합계가 2천만 원을 넘어 다른 소득과 합쳐 종합과세됩니다. 다음 해 5월에 신고합니다."
                   if over else "이자와 배당 합계가 2천만 원 이하라 원천징수로 끝납니다."),
                  "요건을 갖춘 고배당 상장사의 배당은 2026년 수령분부터 분리과세를 신청할 수 있습니다."],
    }, "dividend-withholding", "dividend-foreign", "financial-income", "high-dividend")


def pension_credit(pension_savings, irp=0, lower_income=False):
    document = rules()
    values = document["values"]
    savings, irp = won(pension_savings, "연금저축 납입액"), won(irp, "IRP 납입액")
    eligible = min(min(savings, values["pensionSavingsLimit"]) + irp, values["pensionTotalLimit"])
    rate = values["pensionCreditPct"]["lower-income" if lower_income else "standard"]
    return envelope(document, {"contributed": savings + irp, "eligible": eligible, "ratePct": rate,
                               "taxCredit": math.floor(eligible * rate / 100),
                               "unusedRoom": values["pensionTotalLimit"] - eligible,
                               "notes": ["세액공제는 낸 세금을 돌려받는 것이라 결정세액이 그보다 적으면 다 받지 못합니다.",
                                         "55세 전에 해지하면 공제받은 금액과 수익에 16.5%가 붙습니다."]},
                    "pension-credit", "pension-withdraw")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("rules", help="확인한 세법 규칙과 근거 조문")
    gain = commands.add_parser("overseas-gain", help="해외주식 양도소득세")
    gain.add_argument("--gains", type=float, required=True, help="한 해 동안의 양도차익 합계 (원)")
    gain.add_argument("--losses", type=float, default=0, help="한 해 동안의 양도손실 합계 (원)")
    gain.add_argument("--domestic-taxable", type=float, default=0, help="국내 과세 대상 주식의 손익 (원, 손실은 음수)")
    gain.add_argument("--small-business", action="store_true", help="중소기업 주식")
    give = commands.add_parser("gift", help="증여세")
    give.add_argument("--amount", type=float, required=True, help="이번에 받는 금액 (원)")
    give.add_argument("--relation", required=True, help=", ".join(RELATIONS))
    give.add_argument("--prior", type=float, default=0, help="10년 안에 같은 사람에게 이미 받은 금액")
    give.add_argument("--prior-tax", type=float, default=0, help="그때 낸 증여세")
    give.add_argument("--deduction-used", type=float, default=0, help="같은 관계의 다른 사람에게서 이미 쓴 공제")
    give.add_argument("--marriage-birth", type=float, default=0, help="혼인·출산 공제로 쓸 금액 (최대 1억 원)")
    give.add_argument("--skip-generation", action="store_true", help="조부모가 손주에게 주는 경우")
    give.add_argument("--date", help="증여일. 주면 신고 기한을 계산합니다")
    value = commands.add_parser("gift-value", help="상장주식 증여 평가액 (앞뒤 2개월 종가 평균)")
    value.add_argument("csv", help="date, close 열이 있는 일봉 CSV (실제 종가)")
    value.add_argument("--date", required=True, help="증여일")
    trade = commands.add_parser("transaction-tax", help="국내 주식 매도 때 내는 증권거래세")
    trade.add_argument("--market", required=True, help=", ".join(MARKETS))
    trade.add_argument("--amount", type=float, required=True)
    payout = commands.add_parser("dividend", help="배당 원천징수와 금융소득종합과세 판정")
    payout.add_argument("--amount", type=float, required=True)
    payout.add_argument("--foreign-withheld-pct", type=float, help="해외 배당에서 외국이 뗀 세율. 미국은 보통 15")
    payout.add_argument("--other-financial-income", type=float, default=0, help="올해 다른 이자·배당 합계")
    pension = commands.add_parser("pension-credit", help="연금저축·IRP 세액공제")
    pension.add_argument("--pension-savings", type=float, required=True)
    pension.add_argument("--irp", type=float, default=0)
    pension.add_argument("--lower-income", action="store_true", help="종합소득 4,500만 원(총급여 5,500만 원) 이하")
    args = parser.parse_args()
    actions = {
        "rules": rules,
        "overseas-gain": lambda: overseas_gain(args.gains, args.losses, args.domestic_taxable, args.small_business),
        "gift": lambda: gift(args.amount, args.relation, args.prior, args.prior_tax, args.deduction_used,
                             args.marriage_birth, args.skip_generation, args.date),
        "gift-value": lambda: gift_value(read_bars(args.csv), args.date),
        "transaction-tax": lambda: transaction_tax(args.market, args.amount),
        "dividend": lambda: dividend(args.amount, args.foreign_withheld_pct, args.other_financial_income),
        "pension-credit": lambda: pension_credit(args.pension_savings, args.irp, args.lower_income),
    }
    try:
        print(json.dumps(actions[args.command](), ensure_ascii=False, indent=2, allow_nan=False))
    except HarnessError as exc:
        parser.exit(1, f"{exc}\n")
    except (OSError, ValueError):
        parser.exit(1, "입력값과 파일을 확인해 주세요.\n")


if __name__ == "__main__":
    main()
