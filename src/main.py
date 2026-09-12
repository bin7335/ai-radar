import os
import json
import datetime
import requests
import google.generativeai as genai
import time

# ---------------------------------------------------------
# 1. 초기 세팅 및 인증
# ---------------------------------------------------------
# GitHub Secrets에서 안전하게 주입받은 API 키 사용 (코드에 키 없음!)
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("❌ 환경변수에 GEMINI_API_KEY가 없습니다!")
    exit(1)

genai.configure(api_key=API_KEY)

OUTPUT_FILE = "data/feed.json"

def load_feed():
    if os.path.exists(OUTPUT_FILE):
        with open(OUTPUT_FILE, "r", encoding="utf-8") as f:
            try:
                return json.load(f)
            except:
                return []
    return []

def save_feed(feed_data):
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(feed_data, f, ensure_ascii=False, indent=2)

# ---------------------------------------------------------
# 2. Gemini AI 요약 함수 (PRD 반영)
# ---------------------------------------------------------
def summarize(title, url, source, points="N/A", comments="N/A"):
    model = genai.GenerativeModel('gemini-1.5-flash')
    prompt = f"""
선생님은 교육전문직을 위한 'AI 뉴스 큐레이터'입니다.
불필요한 수식어를 빼고 건조하고 담백하게(Concise & Objective) 작성합니다.

[원문 정보]
- 기사 제목: {title}
- 원문 URL: {url}
- 호응도(포인트): {points}, 댓글 수: {comments}

[출력 형식] (반드시 아래 마크다운 형식을 그대로 지켜주세요)
> **[🔥AI/에이전트] {title}**
> - **한 줄 요약**: (비개발자도 이해하기 쉽게 1줄 요약)
> - **커뮤니티 반응**: (호응도/댓글 수 기반으로 해외 반응 1줄 요약)
> - **업무 시사점**: (단순 반복 행정, 업무 자동화, 바이브코딩에 대체 적용 가능한지 시사점 1줄)
> - **출처**: {source} ({url})
"""
    try:
        response = model.generate_content(prompt)
        return response.text
    except Exception as e:
        print(f"Error during summarization: {e}")
        return f"요약 실패: {title}"

# ---------------------------------------------------------
# 3. 크롤링 함수 (현재 MVP 버전: Hacker News API)
# ---------------------------------------------------------
def scrape_hackernews():
    print("🔍 Hacker News 크롤링 시작...")
    # AI agent 키워드로 최신 3개 글 수집
    url = "https://hn.algolia.com/api/v1/search?query=AI+agent&tags=story&hitsPerPage=3"
    try:
        data = requests.get(url).json()
        results = []
        for hit in data.get('hits', []):
            results.append({
                "title": hit.get("title"),
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "source": "Hacker News",
                "points": hit.get("points"),
                "comments": hit.get("num_comments")
            })
        return results
    except Exception as e:
        print(f"HN Scraping failed: {e}")
        return []

# ---------------------------------------------------------
# 4. 메인 실행 로직
# ---------------------------------------------------------
if __name__ == "__main__":
    feed = load_feed()
    new_items = scrape_hackernews()
    
    for item in new_items:
        # 중복 방지: 이미 feed.json에 있는 URL이면 스킵
        if any(f["url"] == item["url"] for f in feed):
            print(f"⏩ 이미 처리됨 (스킵): {item['title']}")
            continue
            
        print(f"✨ 새로운 뉴스 요약 중: {item['title']}")
        
        # 15 RPM 한도를 피하기 위한 딜레이 (안전하게 4초)
        time.sleep(4) 
        
        summary = summarize(
            title=item["title"], 
            url=item["url"], 
            source=item["source"],
            points=item["points"],
            comments=item["comments"]
        )
        
        # 새 글을 리스트 맨 앞에 추가
        feed.insert(0, {
            "title": item["title"],
            "url": item["url"],
            "summary_md": summary,
            "fetched_at": datetime.datetime.now().isoformat()
        })
        
    # 데이터베이스 폭발 방지 (최신 50개만 유지)
    feed = feed[:50]
    save_feed(feed)
    print("✅ 피드 업데이트 완료!")

