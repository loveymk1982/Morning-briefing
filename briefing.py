import json
import os
import datetime
from zoneinfo import ZoneInfo
import requests
import feedparser

KST = ZoneInfo("Asia/Seoul")

NEWS_CATEGORIES = [
    ("글로벌주식", "https://news.google.com/rss/search?q=%EB%AF%B8%EA%B5%AD%EC%A6%9D%EC%8B%9C+OR+%EA%B8%80%EB%A1%9C%EB%B2%8C+%EC%A6%9D%EC%8B%9C+OR+%EB%82%98%EC%8A%A4%EB%8B%A5+when:1d&hl=ko&gl=KR&ceid=KR:ko"),
    ("경제", "https://news.google.com/rss/headlines/section/topic/BUSINESS?hl=ko&gl=KR&ceid=KR:ko"),
    ("연예", "https://news.google.com/rss/headlines/section/topic/ENTERTAINMENT?hl=ko&gl=KR&ceid=KR:ko"),
    ("스포츠", "https://news.google.com/rss/headlines/section/topic/SPORTS?hl=ko&gl=KR&ceid=KR:ko"),
    ("정치", "https://news.google.com/rss/search?q=%EC%A0%95%EC%B9%98+OR+%EA%B5%AD%ED%9A%8C+OR+%EB%8C%80%ED%86%B5%EB%A0%B9+when:1d&hl=ko&gl=KR&ceid=KR:ko"),
]


def fetch_weather(lat: float = 37.3800, lon: float = 126.8030) -> dict:
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


def fetch_categorized_news(limit_per_cat: int = 5) -> dict[str, list[dict]]:
    result: dict[str, list[dict]] = {}
    for cat_name, rss_url in NEWS_CATEGORIES:
        try:
            feed = feedparser.parse(rss_url)
            items = []
            for entry in feed.entries[:limit_per_cat]:
                items.append({
                    "title": entry.get("title", ""),
                    "link": entry.get("link", ""),
                })
            result[cat_name] = items
        except Exception as exc:
            print(f"[WARN] {cat_name} 뉴스 조회 실패: {exc}")
            result[cat_name] = []
    return result


def build_smart_korean_briefing(
    date_str: str,
    weather: dict,
    news_by_cat: dict[str, list[dict]],
) -> str:
    t_now = weather.get("temp_now")
    t_min = weather.get("temp_min")
    t_max = weather.get("temp_max")
    rain = weather.get("rain_prob") or 0

    lines = [f"좋은 아침입니다! {date_str} 아침 브리핑입니다."]

    if t_now is not None and t_min is not None and t_max is not None:
        diff = round(t_max - t_min, 1)
        if t_min <= 5:
            outfit = "아침 공기가 꽤 쌀쌀하니 보온이 잘 되는 겉옷을 꼭 챙기세요."
        elif diff >= 8:
            outfit = "일교차가 크니 입고 벗기 편한 겉옷을 준비하시는 것이 좋겠습니다."
        elif t_max >= 26:
            outfit = "낮 동안 다소 더울 수 있으니 가벼운 옷차림을 추천합니다."
        else:
            outfit = "활동하기 쾌적한 기온이 예상됩니다."

        umbrella = (
            f"오늘 강수확률이 {rain}%로 예보되어 있으니 우산을 챙기세요."
            if rain >= 40
            else f"강수확률은 {rain}%로 비 소식 없이 맑은 하루가 예상됩니다."
        )
        lines.append(
            f"\n🌤️ [날씨 및 옷차림]\n현재 기온은 {t_now}°C이며, 오늘 최저 {t_min}°C / 최고 {t_max}°C입니다. {outfit} {umbrella}"
        )

    highlights = []
    for cat_name, _ in NEWS_CATEGORIES:
        cat_items = news_by_cat.get(cat_name, [])
        if cat_items:
            highlights.append(f"• [{cat_name}] {cat_items[0]['title']}")

    if highlights:
        lines.append("\n📰 [분야별 오늘의 1면 헤드라인]\n" + "\n".join(highlights))

    return "\n".join(lines)


def generate_ai_briefing(
    api_key: str,
    date_str: str,
    weather: dict,
    news_by_cat: dict[str, list[dict]],
) -> str:
    weather_text = (
        f"현재 {weather.get('temp_now')}°C "
        f"(최저 {weather.get('temp_min')}°C / 최고 {weather.get('temp_max')}°C, "
        f"강수확률 {weather.get('rain_prob')}%)"
    )

    news_sections = []
    for cat_name, _ in NEWS_CATEGORIES:
        items = news_by_cat.get(cat_name, [])
        if items:
            titles = "\n".join(f"  - {it['title']}" for it in items[:3])
            news_sections.append(f"[{cat_name}]\n{titles}")
    news_text = "\n".join(news_sections) if news_sections else "주요 뉴스가 없습니다."

    prompt = f"""오늘은 {date_str}입니다. 아래 정보를 바탕으로 활기차고 간결한 아침 모닝 브리핑을 한국어로 작성해 주세요.

[오늘 날씨]
{weather_text}

[분야별 주요 뉴스]
{news_text}

작성 지침:
1. 다정하고 깔끔한 인사말과 함께 오늘 날씨 및 옷차림/우산 팁을 1~2문장으로 알려주세요.
2. 글로벌주식·경제·정치 등 주요 이슈 흐름을 3~4줄 이내로 핵심만 짚어주세요.
"""

    if api_key.startswith("gsk_"):
        try:
            resp = requests.post(
                "https://api.groq.com/openai/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "llama-3.3-70b-versatile",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 900,
                },
                timeout=25,
            )
            resp.raise_for_status()
            return resp.json()["choices"][0]["message"]["content"].strip()
        except Exception as exc:
            print(f"[WARN] Groq 호출 실패: {exc}")
    elif api_key:
        for model_name in ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-flash-latest"]:
            url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
            try:
                resp = requests.post(
                    url,
                    headers={"x-goog-api-key": api_key},
                    json={"contents": [{"parts": [{"text": prompt}]}]},
                    timeout=25,
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

    return build_smart_korean_briefing(date_str, weather, news_by_cat)


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

    weather = fetch_weather()
    news_by_cat = fetch_categorized_news(limit_per_cat=5)
    summary = generate_ai_briefing(ai_api_key, date_str, weather, news_by_cat)

    send_telegram_message(telegram_token, telegram_chat_id, f"☀️ {date_str} 모닝 브리핑\n\n{summary}")

    os.makedirs("docs", exist_ok=True)
    web_data = {
        "updated_at": now_kst.strftime("%Y-%m-%d %H:%M KST"),
        "date_label": date_str,
        "weather": weather,
        "summary": summary,
        "news_categories": [name for name, _ in NEWS_CATEGORIES],
        "news_by_category": news_by_cat,
    }
    with open("docs/data.json", "w", encoding="utf-8") as f:
        json.dump(web_data, f, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
