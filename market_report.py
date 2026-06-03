#!/usr/bin/env python3
"""
증시 시황 보고서 자동 생성 + 카카오톡 나에게 보내기
필요 패키지: pip install anthropic requests beautifulsoup4 lxml
"""

import os
import re
import json
import requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import anthropic

# ── 환경변수 ──────────────────────────────────────────────
ANTHROPIC_API_KEY = os.environ["ANTHROPIC_API_KEY"]
KAKAO_ACCESS_TOKEN = os.environ["KAKAO_ACCESS_TOKEN"]

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    )
}


# ── 데이터 수집 ────────────────────────────────────────────

def fetch_naver_indices() -> str:
    """네이버 금융 - 코스피/코스닥/나스닥/S&P500"""
    url = "https://finance.naver.com/sise/"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")

        result = []
        # 코스피
        kospi = soup.select_one("#KOSPI_now")
        kospi_chg = soup.select_one("#KOSPI_change")
        if kospi:
            result.append(f"코스피: {kospi.text.strip()} ({kospi_chg.text.strip() if kospi_chg else '-'})")

        # 코스닥
        kosdaq = soup.select_one("#KOSDAQ_now")
        kosdaq_chg = soup.select_one("#KOSDAQ_change")
        if kosdaq:
            result.append(f"코스닥: {kosdaq.text.strip()} ({kosdaq_chg.text.strip() if kosdaq_chg else '-'})")

        return "\n".join(result) if result else "지수 데이터 수집 실패"
    except Exception as e:
        return f"네이버 금융 수집 오류: {e}"


def fetch_naver_news(query: str, display: int = 10) -> list[dict]:
    """네이버 뉴스 검색 API"""
    client_id = os.environ.get("NAVER_CLIENT_ID", "")
    client_secret = os.environ.get("NAVER_CLIENT_SECRET", "")

    if client_id and client_secret:
        url = "https://openapi.naver.com/v1/search/news.json"
        headers = {
            "X-Naver-Client-Id": client_id,
            "X-Naver-Client-Secret": client_secret,
        }
        params = {"query": query, "display": display, "sort": "date"}
        try:
            res = requests.get(url, headers=headers, params=params, timeout=10)
            items = res.json().get("items", [])
            return [
                {
                    "title": re.sub(r"<[^>]+>", "", item["title"]),
                    "description": re.sub(r"<[^>]+>", "", item["description"]),
                    "pubDate": item["pubDate"],
                }
                for item in items
            ]
        except Exception as e:
            print(f"네이버 뉴스 API 오류: {e}")

    # API 키 없을 때 - 네이버 뉴스 웹 크롤링 fallback
    return fetch_naver_news_web(query, display)


def fetch_naver_news_web(query: str, display: int = 8) -> list[dict]:
    """네이버 뉴스 웹 크롤링 (API 키 없을 때 fallback)"""
    url = f"https://search.naver.com/search.naver?where=news&query={requests.utils.quote(query)}&sort=1"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        items = []
        for a in soup.select("a.news_tit")[:display]:
            items.append({"title": a.text.strip(), "description": "", "pubDate": ""})
        return items
    except Exception as e:
        return [{"title": f"크롤링 오류: {e}", "description": "", "pubDate": ""}]


def fetch_hankyung_headlines() -> list[str]:
    """한국경제 증권 뉴스 헤드라인"""
    url = "https://www.hankyung.com/finance"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        headlines = []
        for a in soup.select("h3.news-tit a, h2.tit a")[:10]:
            title = a.text.strip()
            if title and len(title) > 5:
                headlines.append(title)
        return headlines[:8]
    except Exception as e:
        return [f"한경 수집 오류: {e}"]


def fetch_us_market() -> str:
    """미국 증시 데이터 (investing.com 간단 크롤링)"""
    try:
        url = "https://finance.naver.com/world/"
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        rows = []
        for item in soup.select("table.tb_world tbody tr")[:6]:
            cols = item.select("td")
            if len(cols) >= 3:
                name = cols[0].text.strip()
                price = cols[1].text.strip()
                chg = cols[2].text.strip()
                if name:
                    rows.append(f"{name}: {price} ({chg})")
        return "\n".join(rows) if rows else "미국 증시 데이터 수집 실패"
    except Exception as e:
        return f"미국 증시 수집 오류: {e}"


# ── Claude API 분석 ────────────────────────────────────────

def generate_report(indices: str, us_market: str, kr_news: list, stock_news: list, hankyung: list) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    kr_news_text = "\n".join(f"- {n['title']}" for n in kr_news[:8])
    stock_news_text = "\n".join(f"- {n['title']}" for n in stock_news[:8])
    hankyung_text = "\n".join(f"- {h}" for h in hankyung)

    prompt = f"""오늘({TODAY}) 증시 시황 보고서를 작성해주세요. 카카오톡 메시지 형식으로, 핵심만 간결하게 작성해주세요.

=== 수집 데이터 ===

[국내 지수]
{indices}

[미국 증시]
{us_market}

[주요 경제 뉴스]
{kr_news_text}

[증시 뉴스]
{stock_news_text}

[한경 헤드라인]
{hankyung_text}

=== 작성 형식 ===
📊 [{TODAY}] 증시 시황 브리핑

▶ 국내 증시
(코스피/코스닥 동향 2-3줄)

▶ 미국 증시 (전일)
(주요 지수 동향 2줄)

▶ 오늘의 핵심 이슈
(주요 이슈 3가지 bullet)

▶ 주목 섹터/종목
(오늘 주목할 내용 2-3줄)

▶ 한 줄 전망
(오늘 시장 전망 1줄)

※ 수집된 데이터 기반 분석이며 투자 권유가 아닙니다.
"""

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1500,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text


# ── 카카오톡 전송 ──────────────────────────────────────────

def send_kakao(message: str) -> bool:
    url = "https://kapi.kakao.com/v2/api/talk/memo/default/send"
    headers = {
        "Authorization": f"Bearer {KAKAO_ACCESS_TOKEN}",
        "Content-Type": "application/x-www-form-urlencoded",
    }
    # 2000자 초과 시 자르기
    if len(message) > 1900:
        message = message[:1900] + "\n\n(이하 생략)"

    template = json.dumps({
        "object_type": "text",
        "text": message,
        "link": {
            "web_url": "https://finance.naver.com",
            "mobile_web_url": "https://finance.naver.com"
        }
    }, ensure_ascii=False)

    res = requests.post(url, headers=headers, data={"template_object": template})
    if res.status_code == 200 and res.json().get("result_code") == 0:
        print("✅ 카카오톡 전송 성공")
        return True
    else:
        print(f"❌ 카카오톡 전송 실패: {res.status_code} {res.text}")
        return False


def refresh_kakao_token() -> str | None:
    """리프레시 토큰으로 액세스 토큰 갱신"""
    refresh_token = os.environ.get("KAKAO_REFRESH_TOKEN", "")
    app_key = os.environ.get("KAKAO_REST_APP_KEY", "")
    if not refresh_token or not app_key:
        return None

    res = requests.post(
        "https://kauth.kakao.com/oauth/token",
        data={
            "grant_type": "refresh_token",
            "client_id": app_key,
            "refresh_token": refresh_token,
        }
    )
    data = res.json()
    new_token = data.get("access_token")
    if new_token:
        print(f"🔄 액세스 토큰 갱신 완료")
        # 새 리프레시 토큰이 있으면 출력 (GitHub Secrets 수동 업데이트 필요)
        if data.get("refresh_token"):
            print(f"⚠️  리프레시 토큰 갱신됨 - GitHub Secrets 업데이트 필요: {data['refresh_token'][:20]}...")
    return new_token


# ── 메인 ──────────────────────────────────────────────────

def main():
    print(f"[{TODAY}] 증시 시황 보고서 생성 시작...")

    # 토큰 갱신 시도
    new_token = refresh_kakao_token()
    token = new_token or KAKAO_ACCESS_TOKEN

    # 데이터 수집 (병렬이 더 빠르지만 단순성 우선)
    print("📡 데이터 수집 중...")
    indices = fetch_naver_indices()
    us_market = fetch_us_market()
    kr_news = fetch_naver_news("한국 경제 증시")
    stock_news = fetch_naver_news("코스피 코스닥 주식")
    hankyung = fetch_hankyung_headlines()

    print("🤖 Claude 분석 중...")
    report = generate_report(indices, us_market, kr_news, stock_news, hankyung)

    print("📱 카카오톡 전송 중...")
    print("─" * 50)
    print(report)
    print("─" * 50)

    # 토큰을 갱신한 경우 새 토큰으로 전송
    if new_token:
        os.environ["KAKAO_ACCESS_TOKEN"] = new_token
        global KAKAO_ACCESS_TOKEN
        KAKAO_ACCESS_TOKEN = new_token

    send_kakao(report)
    print("완료!")


if __name__ == "__main__":
    main()
