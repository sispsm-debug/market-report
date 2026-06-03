#!/usr/bin/env python3
"""
전일 미국 시장 분석 + 국내 주도주 영향 분석
매일 평일 오전 8시 자동 실행 → 노션 저장 → 텔레그램(증시보고서봇) 발송
"""
import os, json, requests
from datetime import datetime, timezone, timedelta
import yfinance as yf
import anthropic

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
TODAY = now.strftime("%Y-%m-%d")
WEEKDAYS = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]
DATE_KR = f"{now.year}년 {now.month}월 {now.day}일 {WEEKDAYS[now.weekday()]}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

# ── 1. 미국 시장 데이터 수집 ─────────────────────────────

def fetch_us_market():
    """yfinance로 미국 주요 지수·섹터·종목 수집"""
    result = {}

    # 주요 지수
    indices = {
        "S&P500": "^GSPC", "나스닥": "^IXIC", "다우존스": "^DJI",
        "VIX(공포지수)": "^VIX", "달러인덱스": "DX-Y.NYB",
        "미국10년물국채": "^TNX", "원달러환율": "USDKRW=X"
    }
    idx_data = {}
    for name, ticker in indices.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="3d")
            if not hist.empty:
                last = hist.iloc[-1]
                prev = hist.iloc[-2] if len(hist) > 1 else last
                chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
                vol = last.get('Volume', 0)
                idx_data[name] = {
                    "price": round(last['Close'], 2),
                    "change": round(chg, 2),
                    "high": round(last['High'], 2),
                    "low": round(last['Low'], 2),
                }
        except:
            pass
    result["indices"] = idx_data

    # 주요 기술주 (한국 증시 연관)
    tech_stocks = {
        "엔비디아(NVDA)": "NVDA", "AMD": "AMD", "인텔(INTC)": "INTC",
        "마이크론(MU)": "MU", "ASML": "ASML", "TSMC(TSM)": "TSM",
        "애플(AAPL)": "AAPL", "마이크로소프트(MSFT)": "MSFT",
        "테슬라(TSLA)": "TSLA", "아마존(AMZN)": "AMZN",
    }
    stocks_data = {}
    for name, ticker in tech_stocks.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="2d")
            if not hist.empty and len(hist) >= 2:
                last = hist.iloc[-1]
                prev = hist.iloc[-2]
                chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
                stocks_data[name] = {"price": round(last['Close'], 2), "change": round(chg, 2)}
        except:
            pass
    result["tech_stocks"] = stocks_data

    # 섹터 ETF
    sector_etfs = {
        "반도체(SOXX)": "SOXX", "기술(QQQ)": "QQQ",
        "에너지(XLE)": "XLE", "금융(XLF)": "XLF",
        "헬스케어(XLV)": "XLV", "2차전지(LIT)": "LIT",
        "로봇·AI(ROBT)": "ROBT",
    }
    sector_data = {}
    for name, ticker in sector_etfs.items():
        try:
            tk = yf.Ticker(ticker)
            hist = tk.history(period="2d")
            if not hist.empty and len(hist) >= 2:
                last = hist.iloc[-1]
                prev = hist.iloc[-2]
                chg = (last['Close'] - prev['Close']) / prev['Close'] * 100
                sector_data[name] = {"price": round(last['Close'], 2), "change": round(chg, 2)}
        except:
            pass
    result["sectors"] = sector_data

    return result

def fetch_yahoo_news():
    """Yahoo Finance RSS로 주요 뉴스 수집"""
    import xml.etree.ElementTree as ET
    import re
    urls = [
        "https://finance.yahoo.com/rss/topfinstories",
        "https://finance.yahoo.com/rss/headline?s=^GSPC",
        "https://finance.yahoo.com/rss/headline?s=NVDA",
    ]
    news = []
    seen = set()
    for url in urls:
        try:
            res = requests.get(url, headers=UA, timeout=10)
            root = ET.fromstring(res.content)
            for item in root.findall(".//item")[:8]:
                title = re.sub(r"<[^>]+>", "", item.findtext("title","")).strip()
                desc = re.sub(r"<[^>]+>", "", item.findtext("description","")).strip()[:150]
                if title and title not in seen:
                    seen.add(title)
                    news.append({"title": title, "desc": desc})
        except:
            pass
    return news[:20]

def fetch_recent_kr_leaders():
    """최근 국내 주도주 뉴스 수집"""
    import xml.etree.ElementTree as ET
    import re
    url = "https://news.google.com/rss/search?q=코스피+주도주+반도체+AI&hl=ko&gl=KR&ceid=KR:ko"
    try:
        res = requests.get(url, headers=UA, timeout=10)
        root = ET.fromstring(res.content)
        news = []
        for item in root.findall(".//item")[:10]:
            title = re.sub(r"\s*-\s*[^-]+$", "", item.findtext("title","")).strip()
            if title and len(title) > 8:
                news.append(title)
        return news
    except:
        return []

# ── 2. Claude 분석 ────────────────────────────────────────

def analyze_us_market(market_data, yahoo_news, kr_news):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    # 지수 요약
    idx_text = "\n".join(
        f"{k}: {v['price']} ({v['change']:+.2f}%)"
        for k, v in market_data["indices"].items()
    )
    # 기술주 요약
    tech_text = "\n".join(
        f"{k}: {v['price']} ({v['change']:+.2f}%)"
        for k, v in market_data["tech_stocks"].items()
    )
    # 섹터 요약
    sector_text = "\n".join(
        f"{k}: {v['price']} ({v['change']:+.2f}%)"
        for k, v in market_data["sectors"].items()
    )
    # 뉴스
    yahoo_text = "\n".join(f"- {n['title']}" for n in yahoo_news[:10])
    kr_text = "\n".join(f"- {n}" for n in kr_news[:8])

    prompt = f"""너는 한국 주식시장 전문 애널리스트다.
오늘 날짜: {DATE_KR} ({TODAY}) — 국내 장 개장 전 분석

[전일 미국 주요 지수]
{idx_text}

[주요 기술주 (한국 증시 연관)]
{tech_text}

[섹터 ETF 등락]
{sector_text}

[Yahoo Finance 주요 뉴스]
{yahoo_text}

[최근 국내 주도주 동향]
{kr_text}

아래 형식으로 분석 보고서를 작성하라. JSON으로만 응답 (다른 텍스트 없이):
{{
  "us_summary": "미국 시장 전반 흐름 요약 (200자 이내)",
  "key_issues": ["핵심이슈1", "핵심이슈2", "핵심이슈3"],
  "sector_analysis": "강세/약세 섹터 분석 및 이유 (200자 이내)",
  "kr_impact": "국내 증시 개장 전 예상 영향 분석 (200자 이내)",
  "leading_stocks_impact": [
    {{"stock": "종목명(코드)", "impact": "긍정/부정/중립", "reason": "이유 (50자)"}},
    {{"stock": "종목명(코드)", "impact": "긍정/부정/중립", "reason": "이유 (50자)"}},
    {{"stock": "종목명(코드)", "impact": "긍정/부정/중립", "reason": "이유 (50자)"}},
    {{"stock": "종목명(코드)", "impact": "긍정/부정/중립", "reason": "이유 (50자)"}}
  ],
  "watch_points": "오늘 장 중 주목할 포인트 3가지 (200자 이내)",
  "overall_outlook": "국내 증시 전반 전망 한 줄"
}}"""

    res = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    text = res.content[0].text.strip()
    if "```" in text:
        text = text.split("```")[1].replace("json","").strip()
    return json.loads(text)

# ── 3. 노션 저장 ──────────────────────────────────────────

def save_to_notion(market_data, analysis):
    token = os.environ["NOTION_TOKEN"]
    db_id = os.environ["NOTION_DATABASE_ID"]
    notion_headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    # 지수 요약 텍스트
    idx_summary = " | ".join(
        f"{k} {v['change']:+.2f}%"
        for k, v in list(market_data["indices"].items())[:5]
    )

    # 페이지 본문
    children = [
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"🌏 전일 미국 시장 요약"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":analysis["us_summary"]}}]}},
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"📊 주요 지수"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":"\n".join(f"{k}: {v['price']} ({v['change']:+.2f}%)" for k,v in market_data["indices"].items())}}]}},
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"🔑 핵심 이슈"}}]}},
    ]
    for issue in analysis["key_issues"]:
        children.append({"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"text":{"content":issue}}]}})

    children += [
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"📈 주요 기술주"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":"\n".join(f"{k}: {v['price']} ({v['change']:+.2f}%)" for k,v in market_data["tech_stocks"].items())}}]}},
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"🇰🇷 국내 주도주 영향 분석"}}]}},
    ]
    for s in analysis["leading_stocks_impact"]:
        icon = "✅" if s["impact"]=="긍정" else "❌" if s["impact"]=="부정" else "➡️"
        children.append({"object":"block","type":"bulleted_list_item","bulleted_list_item":{"rich_text":[{"text":{"content":f"{icon} {s['stock']}: {s['reason']}"}}]}})

    children += [
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"👀 오늘 주목 포인트"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":analysis["watch_points"]}}]}},
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"🔭 전망"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":analysis["overall_outlook"]}}]}},
    ]

    # DB 스키마 확인
    db_res = requests.get(f"https://api.notion.com/v1/databases/{db_id}", headers=notion_headers).json()
    title_field = next((k for k,v in db_res.get("properties",{}).items() if v["type"]=="title"), "이름")
    date_field = next((k for k,v in db_res.get("properties",{}).items() if v["type"]=="date"), None)

    props = {
        "작성일": {"title": [{"text": {"content": f"[{TODAY}] 미국시장 분석 & 국내 영향"}}]},
        "시장 요약": {"rich_text": [{"text": {"content": analysis["us_summary"][:200]}}]},
        "주도 섹터": {"rich_text": [{"text": {"content": analysis["sector_analysis"][:200]}}]},
        "주도주": {"rich_text": [{"text": {"content": " | ".join(s["stock"] for s in analysis["leading_stocks_impact"])}}]},
        "섹터 선정 근거": {"rich_text": [{"text": {"content": analysis["kr_impact"][:200]}}]},
        "주도주 선정 근거": {"rich_text": [{"text": {"content": analysis["watch_points"][:200]}}]},
        "날짜": {"date": {"start": TODAY}},
    }

    r = requests.post("https://api.notion.com/v1/pages", headers=notion_headers, json={
        "parent": {"type": "database_id", "database_id": db_id},
        "icon": {"type": "emoji", "emoji": "🌏"},
        "properties": props,
        "children": children
    })
    if r.status_code == 200:
        return r.json().get("url","").replace("https://www.notion.so/","https://notion.so/")
    else:
        print(f"노션 오류: {r.status_code} {r.text[:200]}")
        return None

# ── 4. 텔레그램 발송 ──────────────────────────────────────

def send_telegram(market_data, analysis, notion_url):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    # 지수 요약
    idx_lines = "\n".join(
        f"{'🔴' if v['change']<0 else '🟢'} {k}: {v['price']} ({v['change']:+.2f}%)"
        for k, v in list(market_data["indices"].items())[:6]
    )
    # 기술주 핵심
    tech_top = sorted(market_data["tech_stocks"].items(), key=lambda x: abs(x[1]["change"]), reverse=True)[:5]
    tech_lines = " | ".join(f"{k.split('(')[0]} {v['change']:+.2f}%" for k, v in tech_top)

    # 주도주 영향
    impact_lines = "\n".join(
        f"{'✅' if s['impact']=='긍정' else '❌' if s['impact']=='부정' else '➡️'} {s['stock']}: {s['reason']}"
        for s in analysis["leading_stocks_impact"]
    )

    issues = "\n".join(f"• {i}" for i in analysis["key_issues"])

    msg = f"""🌏 [{TODAY}] 미국시장 분석 & 국내 영향

📊 전일 미국 주요 지수
{idx_lines}

📰 핵심 이슈
{issues}

📈 주요 기술주 등락
{tech_lines}

🇰🇷 국내 주도주 예상 영향
{impact_lines}

👀 오늘 주목 포인트
{analysis['watch_points'][:150]}

🔭 {analysis['overall_outlook']}"""

    if notion_url:
        msg += f"\n\n📝 노션: {notion_url}"

    # 분할 전송
    MAX = 3500
    parts, cur = [], ""
    for line in msg.split("\n"):
        if len(cur)+len(line)+1 > MAX and cur:
            parts.append(cur.strip())
            cur = line+"\n"
        else:
            cur += line+"\n"
    if cur.strip(): parts.append(cur.strip())

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    ok = 0
    for part in parts:
        r = requests.post(url, json={"chat_id": chat_id, "text": part, "disable_web_page_preview": True})
        if r.status_code == 200: ok += 1
        else: print(f"전송 실패: {r.text[:100]}")
    print(f"텔레그램 전송: {ok}/{len(parts)}개 성공")

# ── 메인 ─────────────────────────────────────────────────

def main():
    print(f"[{TODAY}] 미국 시장 분석 시작")

    print("📡 시장 데이터 수집 중...")
    market_data = fetch_us_market()
    yahoo_news = fetch_yahoo_news()
    kr_news = fetch_recent_kr_leaders()
    print(f"  지수 {len(market_data['indices'])}개, 기술주 {len(market_data['tech_stocks'])}개, 뉴스 {len(yahoo_news)}건 수집")

    print("🤖 Claude 분석 중...")
    analysis = analyze_us_market(market_data, yahoo_news, kr_news)
    print(f"  전망: {analysis['overall_outlook']}")

    print("📝 노션 저장 중...")
    notion_url = save_to_notion(market_data, analysis)
    print(f"  URL: {notion_url}")

    print("📱 텔레그램 발송 중...")
    send_telegram(market_data, analysis, notion_url)
    print("완료!")

if __name__ == "__main__":
    main()
