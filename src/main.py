# -*- coding: utf-8 -*-
import os
import json
import datetime
import requests
import time
from google import genai
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# 1. 초기 세팅 및 인증
# ---------------------------------------------------------
API_KEY = os.environ.get("GEMINI_API_KEY")
if not API_KEY:
    print("환경변수에 GEMINI_API_KEY가 없습니다!")
    exit(1)

client = genai.Client(api_key=API_KEY)
OUTPUT_FILE = "data/feed.json"
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
# 2. 일괄 요약 (Batch Summarization) 로직
# ---------------------------------------------------------
def summarize_batch(items):
    prompt = "선생님은 교육전문직을 위한 'AI 뉴스 큐레이터'입니다. 불필요한 수식어를 빼고 건조하고 담백하게 작성합니다.\n\n"
    for i, item in enumerate(items):
        desc = item.get('description', '')
        desc_text = f"\n- 부가 설명: {desc}" if desc else ""
        prompt += f"[기사 {i}]\n- 기사 제목: {item['title']}\n- 원문 URL: {item['url']}\n- 출처: {item['source']}{desc_text}\n\n"
        
    prompt += """
위 기사들을 각각 요약해주세요. [출력 형식]을 반드시 지키고, 각 기사의 요약은 '---' 로 구분해주세요.

[카테고리 분류 기준] (매우 엄격하게 적용할 것)
- 오픈소스: 깃허브 레포지토리, 코드가 공개된 AI 모델, 개발자용 오픈소스 도구 (단순 도구 소개는 무조건 여기로 분류)
- 뉴스: AI 관련 새로운 기술 소식, 기업 동향, 일반적인 정책 발표
- 정보: 비용 절감 꿀팁(할인 정책, 토큰 절약 노하우), 무료 프로모션 혜택(예: 특정 서비스 무료 제공 이벤트), 실생활/업무에 금전적·시간적 이득을 주는 실용적 팁
- 커뮤니티: 사람들의 의견, 토론, 후기, 질문, 자유로운 잡담

[출력 형식]
카테고리: [위 4가지 기준 중 가장 적합한 단 1개만 선택하여 작성 (예: 정보)]
> **[🔥AI/에이전트] {기사 제목}**
> - **한 줄 요약**: (비개발자도 이해하기 쉽게 1줄 요약)
> - **업무 시사점**: (단순 반복 행정, 업무 자동화 등에 대체 적용 가능한지 시사점 1줄)
> - **출처**: {출처} ({원문 URL})
---
"""
    for attempt in range(3):
        try:
            response = client.models.generate_content(
                model='gemini-3.6-flash',
                contents=prompt,
            )
            return [x.strip() for x in response.text.split('---') if x.strip()]
        except Exception as e:
            print(f"Error during batch summarization (Attempt {attempt+1}/3): {e}")
            time.sleep(3)
    return []

# ---------------------------------------------------------
# 3. 크롤링 함수 (Hacker News + TechCrunch + GitHub Trending)
# ---------------------------------------------------------
def scrape_hackernews():
    print("🔍 Hacker News 크롤링 시작...")
    url = "https://hn.algolia.com/api/v1/search?query=AI+agent&tags=story&hitsPerPage=12"
    try:
        data = requests.get(url).json()
        results = []
        for hit in data.get('hits', []):
            results.append({
                "title": hit.get("title"),
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "source": "Hacker News",
                "points": hit.get("points") or 0,
                "comments": hit.get("num_comments") or 0
            })
        return results
    except Exception as e:
        print(f"HN Scraping failed: {e}")
        return []

def scrape_techcrunch_ai():
    print("🔍 TechCrunch AI 크롤링 시작...")
    import xml.etree.ElementTree as ET
    import urllib.request
    url = "https://techcrunch.com/category/artificial-intelligence/feed/"
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        xml_data = urllib.request.urlopen(req).read()
        root = ET.fromstring(xml_data)
        results = []
        for item in root.findall('./channel/item')[:5]:
            title = item.find('title').text
            link = item.find('link').text
            results.append({
                "title": title,
                "url": link,
                "source": "TechCrunch AI",
                "points": 300, # 뉴스는 기본 300점으로 취급하여 중간 이상에 노출되도록 함
                "comments": "N/A"
            })
        return results
    except Exception as e:
        print(f"TechCrunch Scraping failed: {e}")
        return []

def scrape_github_trending():
    print("🔍 GitHub Trending 크롤링 시작...")
    url = "https://github.com/trending"
    headers = {"User-Agent": "Mozilla/5.0"}
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
            
            text_for_search = (title + " " + desc).lower()
            if "ai " not in text_for_search and "agent" not in text_for_search and "llm" not in text_for_search:
                continue
                
            # Star 개수 추출
            stars = 500
            for a in repo.select("a.Link--muted"):
                if "stargazers" in a.get("href", ""):
                    stars_text = a.text.strip().replace(',', '')
                    if stars_text.isdigit():
                        stars = int(stars_text)
                        break
                
            results.append({
                "title": title,
                "description": desc,
                "url": f"https://github.com/{title}",
                "source": "GitHub Trending",
                "points": stars,
                "comments": "N/A"
            })
            if len(results) >= 8: break
            
        return results
    except Exception as e:
        print(f"GH Scraping failed: {e}")
        return []

# ---------------------------------------------------------
# 4. 메인 실행 로직
# ---------------------------------------------------------
if __name__ == "__main__":
    feed = load_feed()
    
    new_items = scrape_hackernews() + scrape_github_trending() + scrape_techcrunch_ai()
    items_to_summarize = []
    
    for item in new_items:
        if any(f.get("url") == item["url"] for f in feed):
            print(f"⏩ 이미 처리됨 (스킵): {item['title']}")
        else:
            items_to_summarize.append(item)
            
    if items_to_summarize:
        print(f"✨ {len(items_to_summarize)}개의 뉴스 일괄 요약 시작...")
        summaries = summarize_batch(items_to_summarize)
        
        for i, item in enumerate(items_to_summarize):
            if i < len(summaries) and summaries[i]:
                summary_md = summaries[i]
            else:
                fallback_cat = "오픈소스" if "GitHub" in item["source"] else "뉴스"
                summary_md = f"카테고리: {fallback_cat}\n> **[🔥AI/에이전트] {item['title']}**\n> - **한 줄 요약**: 요약 실패 (API 통신 오류)\n> - **업무 시사점**: 없음\n> - **출처**: {item['source']} ({item['url']})"
            
            feed.insert(0, {
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "summary_md": summary_md,
                "fetched_at": datetime.datetime.now().isoformat()
            })
            
    feed = feed[:50]
    save_feed(feed)
    print("✅ 피드 업데이트 완료!")
