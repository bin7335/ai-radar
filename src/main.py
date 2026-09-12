import os
import json
import datetime
import requests
import time
from google import genai

# ---------------------------------------------------------
# 1. 초기 세팅 및 인증
# ---------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("❌ 환경변수에 GEMINI_API_KEY가 없습니다!")
    exit(1)

# 최신 google-genai 라이브러리 클라이언트 생성
client = genai.Client(api_key=API_KEY)

OUTPUT_FILE = "data/feed.json"
# data 폴더가 없으면 에러가 나므로(빈 폴더는 git에 안 올라감) 명시적으로 생성
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

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
    prompt = f"""
선생님은 교육전문직을 위한 'AI 뉴스 큐레이터'입니다.
불필요한 수식어를 빼고 건조하고 담백하게(Concise & Objective) 작성합니다.

[원문 정보]
- 기사 제목: {title}
- 원문 URL: {url}
- 호응도(포인트): {points}, 댓글 수: {comments}

[출력 형식] (반드시 아래 형식을 그대로 지켜주세요)
카테고리: [여기에 '오픈소스', '뉴스', '정보', '커뮤니티' 중 가장 적절한 것 1개만 작성]
> **[🔥AI/에이전트] {title}**
> - **한 줄 요약**: (비개발자도 이해하기 쉽게 1줄 요약)
> - **업무 시사점**: (단순 반복 행정, 업무 자동화, 바이브코딩에 대체 적용 가능한지 시사점 1줄)
> - **출처**: {source} ({url})
"""
    try:
        response = client.models.generate_content(
            model='gemini-3.6-flash',
            contents=prompt,
        )
        return response.text
    except Exception as e:
        print(f"Error during summarization: {e}")
        fallback_cat = "오픈소스" if "GitHub" in source else "뉴스"
        return f"카테고리: {fallback_cat}\n> **[🔥AI/에이전트] {title}**\n> - **한 줄 요약**: 요약 실패 (API 한도 초과)\n> - **업무 시사점**: 없음\n> - **출처**: {source} ({url})"


from bs4 import BeautifulSoup

# ---------------------------------------------------------
# 3. 크롤링 함수 (Hacker News + GitHub Trending)
# ---------------------------------------------------------
def scrape_hackernews():
    print("🔍 Hacker News 크롤링 시작...")
    # 최신성보다 '핫한(Hot)' 순서를 위해 search 엔드포인트 유지
    url = "https://hn.algolia.com/api/v1/search?query=AI+agent&tags=story&hitsPerPage=7"
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

def scrape_github_trending():
    print("🔍 GitHub Trending 크롤링 시작...")
    url = "https://github.com/trending"
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    try:
        html = requests.get(url, headers=headers).text
        soup = BeautifulSoup(html, "html.parser")
        repos = soup.select("article.Box-row")
        results = []
        
        for repo in repos:
            title_el = repo.select_one("h2 a")
            desc_el = repo.select_one("p")
            
            if not title_el: continue
            title = title_el.text.strip().replace('\n', '').replace(' ', '')
            desc = desc_el.text.strip() if desc_el else ""
            
            # AI, Agent 관련 레포지토리만 필터링
            text_for_search = (title + " " + desc).lower()
            if "ai " not in text_for_search and "agent" not in text_for_search and "llm" not in text_for_search:
                continue
                
            results.append({
                "title": f"{title}: {desc}",
                "url": f"https://github.com/{title}",
                "source": "GitHub Trending",
                "points": "Hot",
                "comments": "N/A"
            })
            if len(results) >= 5: break # 최대 5개
            
        return results
    except Exception as e:
        print(f"GH Scraping failed: {e}")
        return []

# ---------------------------------------------------------
# 4. 메인 실행 로직
# ---------------------------------------------------------
if __name__ == "__main__":
    feed = load_feed()
    
    # 핫한 이슈들 조합 (HN 7개 + GitHub 5개 중 중복 제외하고 TOP 10개 추출)
    new_items = scrape_hackernews() + scrape_github_trending()
    
    for item in new_items:
        if any(f["url"] == item["url"] for f in feed):
            print(f"⏩ 이미 처리됨 (스킵): {item['title']}")
            continue
            
        # 구글 API 무료 티어 Rate Limit 방지용 딜레이 (429 에러 방지)
        time.sleep(6) 
        
        summary = summarize(
            title=item["title"], 
            url=item["url"], 
            source=item["source"],
            points=item["points"],
            comments=item["comments"]
        )
        
        feed.insert(0, {
            "title": item["title"],
            "url": item["url"],
            "summary_md": summary,
            "fetched_at": datetime.datetime.now().isoformat()
        })
        
    feed = feed[:50]
    save_feed(feed)
    print("✅ 피드 업데이트 완료!")
