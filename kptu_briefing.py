#!/usr/bin/env python3
"""
KPTU 공공운수노조 경북지역지부 노동·인권 일간 브리핑
매일 오전 9시 자동 실행 (GitHub Actions)
"""
import os, requests, math
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import anthropic

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
TODAY = now.strftime("%Y-%m-%d")
WEEKDAYS = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]
WEEKDAY = WEEKDAYS[now.weekday()]
DATE_KR = f"{now.year}년 {now.month}월 {now.day}일 {WEEKDAY}"
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

LABOR_KEYWORDS = [
    "민주노총", "고용노동부 발표", "중대재해처벌법",
    "민주노총 공공운수노조", "노란봉투법", "노동위원회 결정",
    "최저임금 심의", "산재", "부당해고", "직장내 괴롭힘",
    "비정규직", "파업 단체교섭", "공무직", "공공운수노조",
    "용역근로자", "노동"
]

def fetch_labor_news(query, n=8):
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={requests.utils.quote(query)}&sort=1&ds=&de="
        res = requests.get(url, headers=UA, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        items = []
        for a in soup.select("a.news_tit")[:n]:
            title = a.text.strip()
            # 날짜 추출
            parent = a.find_parent("div", class_="news_wrap") or a.find_parent("li")
            date_el = parent.select_one("span.info") if parent else None
            date_str = date_el.text.strip() if date_el else ""
            # 언론사
            press_el = parent.select_one("a.info.press") if parent else None
            press = press_el.text.strip() if press_el else ""
            # 요약
            desc_el = parent.select_one("div.dsc_wrap, div.news_dsc") if parent else None
            desc = desc_el.text.strip()[:120] if desc_el else ""
            items.append({"title": title, "press": press, "date": date_str, "desc": desc})
        return items
    except Exception as e:
        return []

def get_dday():
    """노동·인권 기념일 D-day 계산"""
    month, day = now.month, now.day
    messages = []
    # 노동절 (5/1)
    if month == 5 and day == 1:
        messages.append("🎖️ 오늘은 노동절(근로자의 날)입니다!")
    elif month < 5 or (month == 5 and day < 1):
        may1 = datetime(now.year, 5, 1, tzinfo=KST)
        diff = (may1 - now).days
        if diff <= 30:
            messages.append(f"🗓️ 노동절까지 D-{diff}")
    # 세계 산재노동자의 날 (4/28)
    if month == 4 and day == 28:
        messages.append("⚠️ 오늘은 세계 산재노동자의 날입니다!")
    # 광주민주화운동 기념일 (5/18)
    if month == 5 and day == 18:
        messages.append("🕊️ 오늘은 5·18 광주민주화운동 기념일입니다.")
    return " | ".join(messages) if messages else f"📅 {DATE_KR}"

def collect_all_news():
    """모든 키워드로 뉴스 수집 후 중복 제거"""
    all_items = []
    seen_titles = set()
    print(f"뉴스 수집 중... ({len(LABOR_KEYWORDS)}개 키워드)")
    for kw in LABOR_KEYWORDS:
        items = fetch_labor_news(kw, n=5)
        for item in items:
            t = item["title"]
            if t not in seen_titles and len(t) > 10:
                seen_titles.add(t)
                all_items.append(item)
    print(f"수집된 기사: {len(all_items)}건")
    return all_items

def generate_briefing(news_items):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    dday = get_dday()

    news_text = "\n".join(
        f"[{i+1}] {item['title']} | {item['press']} {item['date']}\n    {item['desc']}"
        for i, item in enumerate(news_items[:50])
    )

    prompt = f"""너는 공공운수노조 경북지역지부 일간 브리핑 작성 전문가다.
오늘 날짜: {DATE_KR} ({TODAY})
D-day 정보: {dday}

아래 수집된 뉴스 중에서 최근 2일 이내 기사를 선별해 조합원 관점의 브리핑을 작성하라.

[수집된 뉴스]
{news_text}

다음 형식을 정확히 지켜서 작성하라 (링크는 절대 포함하지 말 것):

━───── [ K P T U ] ─────━
📢 공공운수노조 경북지역지부
🗞️ 오늘의 노동·인권 브리핑
📍 {DATE_KR}
⏰ {dday}
━─────────────────────━

🔥 **오늘의 핵심 TOP 3**

🥇 **[카테고리]**
[헤드라인 한 줄]
— [핵심 한 줄 요약]

🥈 **[카테고리]**
[헤드라인]
— [핵심 한 줄 요약]

🥉 **[카테고리]**
[헤드라인]
— [핵심 한 줄 요약]

━─────────────────────━

📰 **주요 노동 이슈 TOP 10**

① **[카테고리] [헤드라인]**
[3~5문장 요약 — 배경/내용/조합원 영향/전망]
🔗 출처: [매체명] ({TODAY[:7].replace('-','.')})

② ~ ⑩ 동일 형식 반복

━─────────────────────━

🧭 **오늘의 흐름**

1️⃣ **[흐름1 제목]**
[2~3문장 분석]

2️⃣ **[흐름2 제목]**
[2~3문장 분석]

3️⃣ **[흐름3 제목]**
[2~3문장 분석]

━─────────────────────━

✊ **"[마무리 한 줄 — 노동·연대 정신]"**
📌 공공운수노조 경북지역지부

━─────────────────────━

주의사항:
- 법률·제도·판례 → 정책·행정 → 현장이슈 → 노조활동 순서로 배치
- 조합원 관점("우리 일터에 어떤 영향인가") 중심
- 어려운 법률용어는 풀어서 설명
- 링크 절대 금지, 출처는 매체명+날짜만"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def send_telegram_multipart(text):
    """4096자 초과 시 분할 전송"""
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"

    # 구분선 기준으로 분할
    MAX_LEN = 3500
    parts = []
    current = ""
    for line in text.split("\n"):
        if len(current) + len(line) + 1 > MAX_LEN and current:
            parts.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current:
        parts.append(current)

    success = 0
    for i, part in enumerate(parts):
        res = requests.post(url, json={
            "chat_id": chat_id,
            "text": part,
            "disable_web_page_preview": True
        })
        if res.status_code == 200:
            success += 1
        else:
            print(f"전송 실패 [{i+1}/{len(parts)}]: {res.text[:100]}")

    print(f"텔레그램 전송: {success}/{len(parts)}개 성공")
    return success == len(parts)

def main():
    print(f"[{TODAY}] KPTU 브리핑 생성 시작")

    news_items = collect_all_news()
    if not news_items:
        print("뉴스 수집 실패")
        return

    print("Claude 브리핑 작성 중...")
    briefing = generate_briefing(news_items)
    print(f"브리핑 작성 완료 ({len(briefing)}자)")
    print("---")
    print(briefing[:500] + "...")
    print("---")

    print("텔레그램 전송 중...")
    send_telegram_multipart(briefing)
    print("완료!")

if __name__ == "__main__":
    main()
