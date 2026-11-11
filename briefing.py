import json
import os
import datetime
from zoneinfo import ZoneInfo
import requests
import feedparser
import icalendar
import recurring_ical_events

KST = ZoneInfo("Asia/Seoul")


def fetch_weather(lat: float = 37.5665, lon: float = 126.9780) -> dict:
    url = (
        f"https://api.open-meteo.com/v1/forecast"
        f"?latitude={lat}&longitude={lon}"
        f"&current=temperature_2m,weather_code"
        f"&daily=temperature_2m_max,temperature_2m_min,precipitation_probability_max"
        f"&timezone=Asia%2FSeoul&forecast_days=1"
    )
    try:
        resp = requests.get(url, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        current = data.get("current", {})
        daily = data.get("daily", {})
        return {
            "temp_now": current.get("temperature_2m"),
            "temp_max": (daily.get("temperature_2m_max") or [None])[0],
            "temp_min": (daily.get("temperature_2m_min") or [None])[0],
            "rain_prob": (daily.get("precipitation_probability_max") or [0])[0],
        }
    except Exception as exc:
        print(f"[WARN] 날씨 조회 실패: {exc}")
        return {"temp_now": None, "temp_max": None, "temp_min": None, "rain_prob": 0}


def fetch_calendar_events(ics_url: str, target_date: datetime.date) -> list[dict]:
    if not ics_url:
        return []
    try:
        cleaned_url = ics_url.strip().replace("webcal://", "https://")
        resp = requests.get(cleaned_url, timeout=20)
        resp.raise_for_status()
        cal = icalendar.Calendar.from_ical(resp.content)
        raw_events = recurring_ical_events.of(cal).at(target_date)
        events = []
        for ev in raw_events:
            summary = str(ev.get("SUMMARY", "일정"))
            dtstart = ev.get("DTSTART").dt if ev.get("DTSTART") else None
            if isinstance(dtstart, datetime.datetime):
                dt_kst = dtstart.astimezone(KST)
                time_str = dt_kst.strftime("%H:%M")
            else:
                time_str = "종일"
            events.append({"time": time_str, "title": summary})
        events.sort(key=lambda x: x["time"])
        return events
    except Exception as exc:
        print(f"[WARN] 캘린더 일정 조회 실패: {exc}")
        return []


def fetch_top_news(limit: int = 5) -> list[dict]:
    rss_url = "https://news.google.com/rss?hl=ko&gl=KR&ceid=KR:ko"
    try:
        feed = feedparser.parse(rss_url)
        return [
            {"title": entry.get("title", ""), "link": entry.get("link", "")}
            for entry in feed.entries[:limit]
        ]
    except Exception as exc:
        print(f"[WARN] 뉴스 조회 실패: {exc}")
        return []


def generate_ai_briefing(api_key: str, date_str: str, weather: dict, events: list[dict], news: list[dict]) -> str:
    if not api_key:
        return "API 키가 설정되지 않아 기본 데이터만 표시합니다."

    events_text = "\n".join(f"- [{e['time']}] {e['title']}" for e in events) if events else "- 등록된 오늘 일정이 없습니다."
    news_text = "\n".join(f"- {n['title']}" for n in news) if news else "- 주요 뉴스가 없습니다."
    weather_text = f"현재 {weather.get('temp_now')}°C (최저 {weather.get('temp_min')}°C / 최고 {weather.get('temp_max')}°C, 강수확률 {weather.get('rain_prob')}%)"

    prompt = f"""오늘은 {date_str}입니다. 아래 정보를 바탕으로 활기차고 간결한 아침 모닝 브리핑을 한국어로 작성해 주세요.

[오늘 날씨]
{weather_text}

[오늘 일정]
{events_text}

[주요 뉴스 헤드라인]
{news_text}

작성 지침:
1. 다정하고 깔끔한 인사말과 함께 오늘 날씨 및 옷차림/우산 팁을 1~2문장으로 알려주세요.
2. 오늘 일정을 시간순으로 짚어주고, 일정이 없으면 여유로운 하루를 응원해 주세요.
3. 주요 뉴스 헤드라인 핵심을 3줄 이내로 요약해 주세요.
"""
    for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent?key={api_key}"
        try:
            resp = requests.post(
                url,
                json={"contents": [{"parts": [{"text": prompt}]}]},
                timeout=30,
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if candidates:
                parts = candidates[0].get("content", {}).get("parts", [])
                if parts and "text" in parts[0]:
                    return parts[0]["text"].strip()
        except Exception as exc:
            print(f"[WARN] Gemini 모델 {model_name} 호출 실패: {exc}")
    return "AI 요약을 생성하지 못했습니다. Google AI Studio API 키를 확인해 주세요."


def send_telegram_message(token: str, chat_id: str, text: str) -> None:
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        resp = requests.post(url, json={"chat_id": chat_id, "text": text}, timeout=15)
        resp.raise_for_status()
    except Exception as exc:
        print(f"[WARN] 텔레그램 발송 실패: {exc}")


def main() -> None:
    now_kst = datetime.datetime.now(KST)
    weekdays = ["월", "화", "수", "목", "금", "토", "일"]
    date_str = f"{now_kst.strftime('%Y년 %m월 %d일')} ({weekdays[now_kst.weekday()]})"

    telegram_token = os.environ.get("TELEGRAM_TOKEN", "").strip()
    telegram_chat_id = os.environ.get("TELEGRAM_CHAT_ID", "").strip()
    ai_api_key = (
        os.environ.get("GEMINI_API_KEY", "").strip()
        or os.environ.get("ANTHROPIC_API_KEY", "").strip()
    )
    ics_url = os.environ.get("ICS_URL", "").strip()
    publish_events_raw = os.environ.get("PUBLISH_EVENTS", "true").strip().lower()
    publish_events = publish_events_raw not in ("false", "0", "no")

    weather = fetch_weather()
    events = fetch_calendar_events(ics_url, now_kst.date())
    news = fetch_top_news(limit=5)
    summary = generate_ai_briefing(ai_api_key, date_str, weather, events, news)

    send_telegram_message(telegram_token, telegram_chat_id, f"☀️ {date_str} 모닝 브리핑\n\n{summary}")

    os.makedirs("docs", exist_ok=True)
    web_data = {
        "updated_at": now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "date_label": date_str,
        "weather": weather,
        "summary": summary,
        "events": events if publish_events else [],
        "events_hidden": not publish_events,
        "news": news,
    }
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(web_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
