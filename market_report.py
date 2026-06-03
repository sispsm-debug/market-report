#!/usr/bin/env python3
import os, requests
from datetime import datetime, timezone, timedelta
from bs4 import BeautifulSoup
import anthropic

KST = timezone(timedelta(hours=9))
TODAY = datetime.now(KST).strftime("%Y-%m-%d")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/124.0.0.0"}

def fetch_indices():
    try:
        soup = BeautifulSoup(requests.get("https://finance.naver.com/sise/", headers=UA, timeout=10).text, "lxml")
        result = []
        for idx, chg in [("#KOSPI_now","#KOSPI_change"),("#KOSDAQ_now","#KOSDAQ_change")]:
            el = soup.select_one(idx)
            cel = soup.select_one(chg)
            if el:
                name = "코스피" if "KOSPI" in idx else "코스닥"
                result.append(f"{name}: {el.text.strip()} ({cel.text.strip() if cel else '-'})")
        return "\n".join(result) or "지수 수집 실패"
    except Exception as e:
        return f"오류: {e}"

def fetch_news(query, n=6):
    try:
        url = f"https://search.naver.com/search.naver?where=news&query={requests.utils.quote(query)}&sort=1"
        soup = BeautifulSoup(requests.get(url, headers=UA, timeout=10).text, "lxml")
        return [a.text.strip() for a in soup.select("a.news_tit")[:n]]
    except:
        return []

def fetch_hankyung():
    try:
        soup = BeautifulSoup(requests.get("https://www.hankyung.com/finance", headers=UA, timeout=10).text, "lxml")
        return [a.text.strip() for a in soup.select("h3.news-tit a")[:5] if len(a.text.strip()) > 5]
    except:
        return []

def generate_report(indices, kr_news, stock_news, hankyung):
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    prompt = f"""오늘({TODAY}) 증시 시황 보고서를 작성해주세요.

[국내 지수]
{indices}

[경제 뉴스]
{chr(10).join("- "+n for n in kr_news)}

[증시 뉴스]
{chr(10).join("- "+n for n in stock_news)}

[한경 헤드라인]
{chr(10).join("- "+h for h in hankyung)}

아래 형식으로 간결하게:
📊 [{TODAY}] 증시 시황 브리핑

▶ 국내 증시
(코스피/코스닥 동향 2줄)

▶ 오늘의 핵심 이슈
• 이슈1
• 이슈2
• 이슈3

▶ 주목 섹터
(1-2줄)

▶ 한 줄 전망
(1줄)

※ 투자 권유가 아닙니다."""
    return client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=1000,
        messages=[{"role": "user", "content": prompt}]
    ).content[0].text

def send_telegram(message):
    token = os.environ["TELEGRAM_BOT_TOKEN"]
    chat_id = os.environ["TELEGRAM_CHAT_ID"]
    res = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    )
    if res.status_code == 200:
        print("텔레그램 전송 성공")
    else:
        print(f"전송 실패: {res.status_code} {res.text}")

def main():
    print(f"[{TODAY}] 증시 보고서 생성 시작")
    indices = fetch_indices()
    kr_news = fetch_news("한국 경제 증시")
    stock_news = fetch_news("코스피 코스닥 주식")
    hankyung = fetch_hankyung()
    print("Claude 분석 중...")
    report = generate_report(indices, kr_news, stock_news, hankyung)
    print(report)
    print("---")
    send_telegram(report)

if __name__ == "__main__":
    main()
