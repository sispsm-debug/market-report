#!/usr/bin/env python3
"""
KPTU 공공운수노조 경북지역지부 노동·인권 일간 브리핑
Google News RSS + 노동전문매체 RSS로 안정적 수집
"""
import os, re, requests, xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
import anthropic

KST = timezone(timedelta(hours=9))
now = datetime.now(KST)
TODAY = now.strftime("%Y-%m-%d")
YESTERDAY = (now - timedelta(days=1)).strftime("%Y-%m-%d")
WEEKDAYS = ["월요일","화요일","수요일","목요일","금요일","토요일","일요일"]
DATE_KR = f"{now.year}년 {now.month}월 {now.day}일 {WEEKDAYS[now.weekday()]}"
UA = {"User-Agent": "Mozilla/5.0 (compatible; RSS/2.0)"}

# ── 우선 출처 RSS ─────────────────────────────────────────
PRIORITY_RSS = [
    ("매일노동뉴스",    "https://www.labortoday.co.kr/rss/allArticle.xml"),
    ("참여와혁신",      "https://www.laborplus.co.kr/rss/allArticle.xml"),
    ("미디어오늘",      "https://www.mediatoday.co.kr/rss/allArticle.xml"),
    ("참세상",          "https://www.newscham.net/rss/rss.php"),
    ("한겨레",          "https://www.hani.co.kr/rss/society/"),
    ("경향신문",        "https://www.khan.co.kr/rss/rssdata/kh_labor.xml"),
    ("연합뉴스",        "https://www.yna.co.kr/rss/society.xml"),
    ("오마이뉴스",      "https://www.ohmynews.com/ohmynews/rss/0000000.xml"),
    ("MBC뉴스",         "https://imnews.imbc.com/rss/news/news_00.xml"),
]

# ── Google 뉴스 RSS (키워드별) ────────────────────────────
KEYWORDS = [
    "민주노총", "공공운수노조", "중대재해처벌법",
    "고용노동부", "노란봉투법", "최저임금",
    "산재 사망", "부당해고", "직장내 괴롭힘",
    "비정규직", "파업", "공무직",
]

def parse_date(date_str):
    """날짜 문자열을 datetime으로 변환"""
    try:
        return parsedate_to_datetime(date_str).astimezone(KST)
    except:
        try:
            for fmt in ["%Y-%m-%dT%H:%M:%S%z", "%a, %d %b %Y %H:%M:%S %z"]:
                return datetime.strptime(date_str[:25], fmt[:len(date_str[:25])]).astimezone(KST)
        except:
            return now  # 파싱 실패 시 오늘로 처리

def is_recent(date_str):
    """최근 2일 이내 기사인지 확인"""
    try:
        dt = parse_date(date_str)
        diff = (now - dt).days
        return diff <= 2
    except:
        return True  # 날짜 불명 시 포함

def fetch_rss(url, press_name, n=15):
    """RSS 피드에서 최근 기사 수집"""
    try:
        res = requests.get(url, headers=UA, timeout=10)
        root = ET.fromstring(res.content)
        items = []
        ns = {"atom": "http://www.w3.org/2005/Atom"}
        
        for item in root.findall(".//item")[:n]:
            title = item.findtext("title", "").strip()
            desc = item.findtext("description", "").strip()
            pub_date = item.findtext("pubDate", "")
            # HTML 태그 제거
            title = re.sub(r"<[^>]+>", "", title)
            desc = re.sub(r"<[^>]+>", "", desc)[:150]
            
            if title and is_recent(pub_date):
                items.append({
                    "title": title,
                    "desc": desc,
                    "press": press_name,
                    "date": pub_date[:16] if pub_date else TODAY,
                })
        return items
    except Exception as e:
        return []

def fetch_google_news(keyword, n=8):
    """Google 뉴스 RSS로 키워드 검색"""
    try:
        import urllib.parse
        q = urllib.parse.quote(keyword)
        url = f"https://news.google.com/rss/search?q={q}&hl=ko&gl=KR&ceid=KR:ko"
        res = requests.get(url, headers=UA, timeout=10)
        root = ET.fromstring(res.content)
        items = []
        for item in root.findall(".//item")[:n]:
            title = item.findtext("title", "").strip()
            title = re.sub(r"\s*-\s*[^-]+$", "", title)  # 매체명 제거
            source_el = item.find("source")
            press = source_el.text if source_el is not None else "구글뉴스"
            pub_date = item.findtext("pubDate", "")
            desc = item.findtext("description", "")
            desc = re.sub(r"<[^>]+>", "", desc)[:150]
            
            if title and is_recent(pub_date):
                items.append({
                    "title": title,
                    "desc": desc,
                    "press": press,
                    "date": pub_date[:16] if pub_date else TODAY,
                })
        return items
    except Exception as e:
        return []

def collect_all_news():
    """우선 출처 RSS + Google 뉴스 키워드 검색 통합"""
    all_items = []
    seen = set()
    
    # 1차: 노동전문매체 RSS
    print("노동전문매체 RSS 수집 중...")
    for press, url in PRIORITY_RSS:
        items = fetch_rss(url, press, n=15)
        for item in items:
            t = item["title"]
            if t not in seen and len(t) > 8:
                seen.add(t)
                all_items.append(item)
        if items:
            print(f"  {press}: {len(items)}건")
    
    # 2차: Google 뉴스 키워드 검색
    print("Google 뉴스 키워드 검색 중...")
    for kw in KEYWORDS:
        items = fetch_google_news(kw, n=5)
        for item in items:
            t = item["title"]
            if t not in seen and len(t) > 8:
                seen.add(t)
                all_items.append(item)
    
    print(f"총 수집: {len(all_items)}건")
    return all_items

def get_dday():
        m, d = now.month, now.day
        items = []
        # 고정 기념일
    if m == 5 and d == 1: return "🎖️ 오늘은 노동절(근로자의 날)입니다!"
            if m == 4 and d == 28: return "⚠️ 오늘은 세계 산재노동자의 날입니다!"
                    if m == 5 and d == 18: return "🕊️ 오늘은 5·18 광주민주화운동 기념일입니다."
                            if m == 6 and d == 6: return "🇰🇷 오늘은 현충일입니다."
                                    # 주요 D-day 계산
    targets = [
                (6, 6,  "현충일"),
                (6, 29, "최저임금 법정 심의 시한"),
                (5, 1,  "노동절"),
    ]
    for tm, td, label in targets:
                target = datetime(now.year, tm, td, tzinfo=KST)
                diff = (target - now).days
                if 0 < diff <= 30:
                                items.append(f"{label}까지 D-{diff}")
                        if items:
                                    return "📅 " + " | ".join(items)
                                return f"📅 {DATE_KR}"

def generate_briefing(news_items):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    dday = get_dday()
    
    news_text = "\n".join(
        f"[{i+1}] {item['title']} | {item['press']} | {item['date']}\n    {item['desc']}"
        for i, item in enumerate(news_items[:60])
    )

    prompt = f"""너는 공공운수노조 경북지역지부 일간 브리핑 작성 전문가다.
오늘 날짜: {DATE_KR} ({TODAY})
D-day: {dday}

[수집된 뉴스 — 최근 2일 이내 기사만 사용]
{news_text}

아래 형식을 정확히 지켜서 브리핑을 작성하라.
링크는 절대 포함 금지. 출처는 매체명+날짜만.
주제 배치 순서: 1순위 법률·판례 → 2순위 정책·행정 → 3순위 현장이슈 → 4순위 노조활동

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
🔗 출처: [매체명] ({now.year}.{now.month:02d}.{now.day:02d})

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

작성 원칙:
- 조합원 관점("우리 일터에 어떤 영향인가") 중심
- 어려운 법률용어 풀어서 설명
- 객관적 사실 + 전망/주의사항 포함
- 정치적 편향 없이 노동자 권리 관점에서"""

    res = client.messages.create(
        model="claude-sonnet-4-6",
            max_tokens=6000,
                    messages=[{"role": "user", "content": prompt}]
    )
    return res.content[0].text

def send_telegram(text):
    token = os.environ["KPTU_BOT_TOKEN"]
    chat_id = os.environ["KPTU_CHAT_ID"]
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    SEP = "━─────────────────────━"
        # 구분선 기준으로 섹션 분리 후 4096자 초과 시에만 분할
    sections = text.split(SEP)
        parts, cur = [], ""
    for i, sec in enumerate(sections):
                chunk = (SEP if i > 0 else "") + sec
                if len(cur) + len(chunk) > 4000 and cur:
                                parts.append(cur.strip())
                                cur = chunk
                else:
                                cur += chunk
                        if cur.strip():
                                    parts.append(cur.strip())

    ok = 0
    for part in parts:
                r = requests.post(url, json={"chat_id": chat_id, "text": part, "disable_web_page_preview": True})
        if r.status_code == 200: ok += 1
        else: print(f"전송 실패: {r.text[:100]}")
    print(f"텔레그램 전송: {ok}/{len(parts)}개 성공")

def main():
    print(f"[{TODAY}] KPTU 브리핑 생성 시작")
    news = collect_all_news()
    if not news:
        print("뉴스 수집 실패 - 텔레그램으로 오류 알림")
        send_telegram(f"⚠️ [{TODAY}] KPTU 브리핑 수집 실패\nRSS 피드 점검 필요")
        return
    print("Claude 브리핑 작성 중...")
    briefing = generate_briefing(news)
    print(f"작성 완료 ({len(briefing)}자)")
    send_telegram(briefing)
    print("완료!")

if __name__ == "__main__":
    main()
