#!/usr/bin/env python3
import os, re, json, requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import anthropic

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

def fetch_naver_indices():
    try:
        res = requests.get("https://finance.naver.com/sise/", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        result = []
        kospi = soup.select_one("#KOSPI_now")
        kospi_chg = soup.select_one("#KOSPI_change")
        if kospi:
            result.append(f"코스피: {kospi.text.strip()} ({kospi_chg.text.strip() if kospi_chg else '-'})")
        kosdaq = soup.select_one("#KOSDAQ_now")
        kosdaq_chg = soup.select_one("#KOSDAQ_change")
        if kosdaq:
            result.append(f"코스닥: {kosdaq.text.strip()} ({kosdaq_chg.text.strip() if kosdaq_chg else '-'})")
        return "\n".join(result) if result else "지수 데이터 수집 실패"
    except Exception as e:
        return f"오류: {e}"

def fetch_news(query, display=8):
    url = f"https://search.naver.com/search.naver?where=news&query={requests.utils.quote(query)}&sort=1"
    try:
        res = requests.get(url, headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        return [{"title": a.text.strip()} for a in soup.select("a.news_tit")[:display]]
    except:
        return []

def fetch_hankyung():
    try:
        res = requests.get("https://www.hankyung.com/finance", headers=HEADERS, timeout=10)
        soup = BeautifulSoup(res.text, "lxml")
        return [a.text.strip() for a in soup.select("h3.news-tit a, h2.tit a")[:8] if len(a.text.strip()) > 5]
    except:
        return []

def generate_report(indices, kr_news, stock_news, hankyung):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    kr = "\n".join(f"- {n['title']}" for n in kr_news[:6])
    st = "\n".join(f"- {n['title']}" for n in stock_news[:6])
    hk = "\n".join(f"- {h}" for h in hankyung[:6])
    prompt = f"""오늘({TODAY}) 증시 시황 보고서를 카카오톡 메시지 형식으로 작성해주세요.

[국내 지수]
{indices}

[경제 뉴스]
{kr}

[증시 뉴스]
{st}

[한경 헤드라인]
{hk}

아래 형식으로 간결하게 작성:
📊 [{TODAY}] 증시 시황 브리핑

▶ 국내 증시
(코스피/코스닥 동향 2줄)

▶ 오늘의 핵심 이슈
(주요 이슈 3가지)

▶ 주목 섹터
(1-2줄)

▶ 한 줄 전망
(1줄)

※ 투자 권유가 아닙니다."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    )
    return response.content[0].text

def send_kakao(message):
    token = os.environ["KAKAO_ACCESS_TOKEN"]
    if len(message) > 1900:
        message = message[:1900] + "\n(이하 생략)"
    template = json.dumps({
        "object_type": "text",
        "text": message,
        "link": {"web_url": "https://finance.naver.com", "mobile_web_url": "https://finance.naver.com"}
    }, ensure_ascii=False)
    res = requests.post(
        "https://kapi.kakao.com/v2/api/talk/memo/default/send",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/x-www-form-urlencoded"},
        data={"template_object": template}
    )
    if res.status_code == 200 and res.json().get("result_code") == 0:
        print("카카오톡 전송 성공")
    else:
        print(f"전송 실패: {res.status_code} {res.text}")

def main():
    print(f"[{TODAY}] 증시 보고서 생성 시작")
    indices = fetch_naver_indices()
    kr_news = fetch_news("한국 경제 증시")
    stock_news = fetch_news("코스피 코스닥 주식")
    hankyung = fetch_hankyung()
    print("Claude 분석 중...")
    report = generate_report(indices, kr_news, stock_news, hankyung)
    print(report)
    send_kakao(report)

if __name__ == "__main__":
    main()
