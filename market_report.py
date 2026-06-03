#!/usr/bin/env python3
"""
증시 주도섹터 & 주도주 분석 → 노션 저장 → 텔레그램 발송
매일 오전 9시 자동 실행 (GitHub Actions)
"""
import os, json, requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import anthropic

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

# ── 1. 데이터 수집 ────────────────────────────────────────

def fetch_news(query, n=8):
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={requests.utils.quote(query)}&sort=1"
        soup = BeautifulSoup(requests.get(url, headers=UA, timeout=10).text, "lxml")
        items = []
        for a in soup.select("a.news_tit")[:n]:
            desc_el = a.find_next("div", class_="dsc_wrap")
            desc = desc_el.text.strip() if desc_el else ""
            items.append({"title": a.text.strip(), "desc": desc[:100]})
        return items
    except Exception as e:
        return [{"title": f"수집 오류: {e}", "desc": ""}]

def fetch_indices():
    try:
        soup = BeautifulSoup(requests.get("https://finance.naver.com/sise/", headers=UA, timeout=10).text, "lxml")
        result = []
        for idx, chg_id, name in [("#KOSPI_now","#KOSPI_change","코스피"), ("#KOSDAQ_now","#KOSDAQ_change","코스닥")]:
            el = soup.select_one(idx)
            chg = soup.select_one(chg_id)
            if el:
                result.append(f"{name}: {el.text.strip()} ({chg.text.strip() if chg else '-'})")
        return "\n".join(result)
    except:
        return "지수 수집 실패"

def fetch_hankyung():
    try:
        soup = BeautifulSoup(requests.get("https://www.hankyung.com/finance", headers=UA, timeout=10).text, "lxml")
        return [a.text.strip() for a in soup.select("h3.news-tit a, h2.tit a")[:6] if len(a.text.strip()) > 5]
    except:
        return []

# ── 2. Claude 분석 ────────────────────────────────────────

def analyze_market(indices, news1, news2, news3, hankyung):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    news_text = "\n".join(f"- {n['title']}" for n in news1[:6])
    sector_text = "\n".join(f"- {n['title']}" for n in news2[:6])
    stock_text = "\n".join(f"- {n['title']}" for n in news3[:6])
    hk_text = "\n".join(f"- {h}" for h in hankyung)

    prompt = f"""오늘({TODAY}) 한국 증시를 분석하고 JSON 형식으로 응답해주세요.

[국내 지수]
{indices}

[시황 뉴스]
{news_text}

[섹터/테마 뉴스]
{sector_text}

[급등/주도주 뉴스]
{stock_text}

[한경 헤드라인]
{hk_text}

다음 JSON 형식으로만 응답 (다른 텍스트 없이):
{{
  "market_summary": "코스피/코스닥 흐름 요약 (150자 이내)",
  "leading_sectors": ["섹터1", "섹터2", "섹터3"],
  "sector_reason": "각 섹터 선정 이유 (200자 이내)",
  "leading_stocks": [
    {{"name": "종목명", "code": "종목코드", "rate": "+X.X%", "reason": "선정이유"}},
    {{"name": "종목명", "code": "종목코드", "rate": "+X.X%", "reason": "선정이유"}},
    {{"name": "종목명", "code": "종목코드", "rate": "+X.X%", "reason": "선정이유"}}
  ],
  "stock_reason": "주도주 선정 종합 근거 (150자 이내)",
  "tomorrow_watch": "내일 주목할 이슈 또는 주의사항 (150자 이내)"
}}"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    text = response.content[0].text.strip()
    # JSON 추출
    if "```" in text:
        text = text.split("```")[1].replace("json","").strip()
    return json.loads(text)

# ── 3. 노션 저장 ──────────────────────────────────────────

def save_to_notion(data):
    token = os.environ["NOTION_TOKEN"]
    db_id = os.environ["NOTION_DATABASE_ID"]
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Notion-Version": "2022-06-28"
    }

    sectors_str = ", ".join(data["leading_sectors"])
    stocks_str = ", ".join(f"{s['name']}({s['code']}) {s['rate']}" for s in data["leading_stocks"])

    # 페이지 본문
    content_blocks = [
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"📊 오늘의 시장 요약"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":data["market_summary"]}}]}},
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"🏆 주도 섹터"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":sectors_str + "\n\n" + data["sector_reason"]}}]}},
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"💹 오늘의 주도주"}}]}},
    ]
    for s in data["leading_stocks"]:
        content_blocks.append({
            "object":"block","type":"bulleted_list_item",
            "bulleted_list_item":{"rich_text":[{"text":{"content":f"{s['name']}({s['code']}) {s['rate']} - {s['reason']}"}}]}
        })
    content_blocks += [
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":data["stock_reason"]}}]}},
        {"object":"block","type":"heading_2","heading_2":{"rich_text":[{"text":{"content":"📌 투자 참고 사항"}}]}},
        {"object":"block","type":"paragraph","paragraph":{"rich_text":[{"text":{"content":data["tomorrow_watch"]}}]}},
    ]

    payload = {
        "parent": {"type": "database_id", "database_id": db_id},
        "icon": {"type": "emoji", "emoji": "📊"},
        "properties": {
            "작성일": {"rich_text": [{"text": {"content": TODAY}}]},
            "주도 섹터": {"rich_text": [{"text": {"content": sectors_str}}]},
            "주도주": {"rich_text": [{"text": {"content": stocks_str}}]},
            "시장 요약": {"rich_text": [{"text": {"content": data["market_summary"]}}]},
            "섹터 선정 근거": {"rich_text": [{"text": {"content": data["sector_reason"]}}]},
            "주도주 선정 근거": {"rich_text": [{"text": {"content": data["stock_reason"]}}]},
        },
        "children": content_blocks
    }

    # 타이틀 필드 찾기
    db_res = requests.get(f"https://api.notion.com/v1/databases/{db_id}", headers=headers).json()
    title_field = next((k for k,v in db_res.get("properties",{}).items() if v["type"]=="title"), "이름")
    payload["properties"][title_field] = {"title": [{"text": {"content": f"[{TODAY}] 증시 주도섹터 분석"}}]}

    # 날짜 필드
    date_field = next((k for k,v in db_res.get("properties",{}).items() if v["type"]=="date"), None)
    if date_field:
        payload["properties"][date_field] = {"date": {"start": TODAY}}

    r = requests.post("https://api.notion.com/v1/pages", headers=headers, json=payload)
    if r.status_code == 200:
        page = r.json()
        return page.get("url", "").replace("https://www.notion.so/", "https://notion.so/")
    else:
        print(f"노션 오류: {r.status_code} {r.text[:200]}")
        return None

# ── 4. 텔레그램 발송 ──────────────────────────────────────

def send_telegram(data, notion_url):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]

    sectors = " | ".join(data["leading_sectors"])
    stocks = "\n".join(f"• {s['name']}({s['code']}) {s['rate']}" for s in data["leading_stocks"])

    msg = f"""📊 [{TODAY}] 증시 주도섹터 & 주도주

🏆 주도섹터: {sectors}

💹 주도주:
{stocks}

📈 {data['market_summary'][:80]}

📌 내일 주목: {data['tomorrow_watch'][:60]}"""

    if notion_url:
        msg += f"\n\n📝 노션: {notion_url}"

    msg += "\n\n#주도주 #증시분석"

    res = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": msg}
    )
    print("텔레그램 전송 성공" if res.status_code == 200 else f"전송 실패: {res.text}")

# ── 메인 ─────────────────────────────────────────────────

def main():
    print(f"[{TODAY}] 증시 분석 시작")

    print("데이터 수집 중...")
    indices = fetch_indices()
    news1 = fetch_news("코스피 코스닥 시황 오늘")
    news2 = fetch_news("오늘 강세 섹터 테마 주도주")
    news3 = fetch_news("급등주 상한가 주도 종목")
    hankyung = fetch_hankyung()

    print("Claude 분석 중...")
    data = analyze_market(indices, news1, news2, news3, hankyung)
    print(f"주도섹터: {data['leading_sectors']}")
    print(f"주도주: {[s['name'] for s in data['leading_stocks']]}")

    print("노션 저장 중...")
    notion_url = save_to_notion(data)
    print(f"노션 URL: {notion_url}")

    print("텔레그램 발송 중...")
    send_telegram(data, notion_url)
    print("완료!")

if __name__ == "__main__":
    main()
