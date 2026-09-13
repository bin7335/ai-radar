# -*- coding: utf-8 -*-
import os
import json
import datetime
import requests
import time
from openai import OpenAI
from google import genai
from bs4 import BeautifulSoup

# ---------------------------------------------------------
# 1. 초기 세팅 및 인증
# ---------------------------------------------------------
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")

or_client = None
if OPENROUTER_API_KEY:
    or_client = OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=OPENROUTER_API_KEY, timeout=45.0
    )

gemini_client = None
if GEMINI_API_KEY:
    gemini_client = genai.Client(api_key=GEMINI_API_KEY)

OUTPUT_FILE = "data/feed.json"
os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

def clean_text(text):
    if not text: return text
    import re
    bad_words = ['좆', '존나', '씨발', '개새', '병신', '미친', '지랄', '새끼', '썅', '개소리', '씹', '자지', '보지', '섹스', '야동']
    for word in bad_words:
        text = re.sub(word, '★', text)
    return text

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
    prompt = "당신은 IT 및 AI 최신 동향을 분석하는 '수석 AI 큐레이터'입니다. 불필요한 수식어를 빼고 건조하고 담백하게 핵심만 작성합니다. **영어로 된 기사나 요약도 반드시 모두 자연스러운 한국어(Korean)로 번역해서 작성해주세요.**\n\n"
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
> - **한 줄 요약**: (비개발자도 이해하기 쉽게 핵심만 1줄 요약)
> - **인사이트**: (업무 생산성 향상, 자동화 적용, 또는 기술적 레퍼런스 관점에서의 가치를 1줄로 제시)
> - **출처**: {출처} ({원문 URL})
---
"""
    for attempt in range(3):
        # 1. 1순위: OpenRouter 무료 모델 로테이션 시도
        if or_client:
            free_models = [
                "google/gemma-4-31b-it:free",
                "google/gemma-4-26b-a4b-it:free",
                "nvidia/nemotron-3.5-lightning:free",
                "liquid/lfm-2.5-2.6b:free",
                "cohere/north-mini-code:free"
            ]
            success = False
            for model_name in free_models:
                try:
                    print(f"🤖 [엔진 1] OpenRouter ({model_name}) 시도 중... (Attempt {attempt+1}/3)")
                    response = or_client.chat.completions.create(
                        model=model_name,
                        messages=[{"role": "user", "content": prompt}], timeout=30.0
                    )
                    text = response.choices[0].message.content
                    parsed = [x.strip() for x in text.split('---') if x.strip()]
                    if len(parsed) >= len(items):
                        return parsed
                    else:
                        print(f"❌ OpenRouter ({model_name}) 구조적 오류: {len(parsed)}/{len(items)}개 출력")
                except Exception as e:
                    print(f"❌ OpenRouter ({model_name}) 통신 실패: {e}")
            
            # 모든 모델 실패 시 gemini로 넘어감

        # 2. 2순위: Google Gemini (gemini-3.6-flash) 폴백 시도
        if gemini_client:
            try:
                print(f"🤖 [엔진 2] Google Gemini 시도 중... (Attempt {attempt+1}/3)")
                response = gemini_client.models.generate_content(
                    model='gemini-3.6-flash',
                    contents=prompt,
                )
                parsed = [x.strip() for x in response.text.split('---') if x.strip()]
                if len(parsed) >= len(items):
                    return parsed
                else:
                    print(f"❌ Gemini 구조적 오류: {len(parsed)}/{len(items)}개 출력")
            except Exception as e:
                print(f"❌ Gemini 통신 실패: {e}")
                
        print("⚠️ 모든 AI 엔진이 실패했습니다. 3초 후 재시도...")
        time.sleep(3)
        
    return []

# ---------------------------------------------------------
# 3. 크롤링 함수 (Hacker News + TechCrunch + GitHub Trending)
# ---------------------------------------------------------

def scrape_dcinside():
    print("🕸️ 디시인사이드 (특이점이 온다 & AI 활용 갤러리) 크롤링 시작...")
    import requests
    from bs4 import BeautifulSoup
    import datetime
    
    galleries = [
        {"id": "thesingularity", "name": "특이점이 온다"},
        {"id": "ai_utilize", "name": "AI 활용"}
    ]
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
    final_posts = []
    
    for gal in galleries:
        url = f"https://gall.dcinside.com/mgallery/board/lists/?id={gal['id']}&exception_mode=recommend"
        import time
        time.sleep(2)
        try:
            response = requests.get(url, headers=headers, timeout=10)
            soup = BeautifulSoup(response.text, 'html.parser')
            
            all_posts = []
            for tr in soup.select('tr.us-post'):
                num_tag = tr.select_one('.gall_num')
                if num_tag and not num_tag.text.strip().isdigit(): continue
                a_tag = tr.select_one('.gall_tit a:not(.reply_numbox)')
                if not a_tag: continue
                
                title = a_tag.text.strip()
                link = "https://gall.dcinside.com" + a_tag['href']
                
                points_tag = tr.select_one('.gall_recommend')
                points = int(points_tag.text.strip()) if points_tag and points_tag.text.strip().isdigit() else 0
                
                all_posts.append({
                    "title": title,
                    "url": link,
                    "source": f"DCInside ({gal['name']})",
                    "points": points,
                    "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
            
            # 각 갤러리별로 추천수(points)가 높은 상위 5개만 최종 리스트에 추가
            all_posts.sort(key=lambda x: x['points'], reverse=True)
            final_posts.extend(all_posts[:5])
            
        except Exception as e:
            print(f"DC Scraping failed for {gal['name']}: {e}")
            
    return final_posts

def scrape_hackernews():
    print("🔍 Hacker News 크롤링 시작...")
    # 50일 이내 필터링 추가
    fifty_days_ago = int(time.time()) - (50 * 24 * 60 * 60)
    url = f"https://hn.algolia.com/api/v1/search?query=AI+agent&tags=story&hitsPerPage=12&numericFilters=created_at_i>{fifty_days_ago}"
    try:
        data = requests.get(url, timeout=10).json()
        results = []
        for hit in data.get('hits', []):
            results.append({
                "title": hit.get("title"),
                "url": hit.get("url") or f"https://news.ycombinator.com/item?id={hit.get('objectID')}",
                "source": "Hacker News",
                "points": hit.get("points") or 0,
                "comments": hit.get("num_comments") or 0,
                "published_at": hit.get("created_at") or datetime.datetime.now(datetime.timezone.utc).isoformat()
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
        xml_data = urllib.request.urlopen(req, timeout=10).read()
        root = ET.fromstring(xml_data)
        results = []
        for item in root.findall('./channel/item')[:5]:
            title = item.find('title').text
            link = item.find('link').text
            pubDate = item.find('pubDate')
            pubDateStr = pubDate.text if pubDate is not None else datetime.datetime.now(datetime.timezone.utc).isoformat()
            results.append({
                "title": title,
                "url": link,
                "source": "TechCrunch AI",
                "points": 300, # 뉴스는 기본 300점으로 취급하여 중간 이상에 노출되도록 함
                "comments": "N/A",
                "published_at": pubDateStr
            })
        return results
    except Exception as e:
        print(f"TechCrunch Scraping failed: {e}")
        return []

def scrape_github_trending():
    print("🚀 GitHub Trending (Weekly) 크롤링 시작...")
    url = "https://github.com/trending?since=weekly"
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        html = requests.get(url, headers=headers, timeout=10).text
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
            import re
            is_ai = bool(re.search(r'\b(ai|agent|llm|gpt|model|machine learning|deep learning|diffusion|transformer|chatbot|genai|generative|openai|llama|vision|audio|tts|stt|skill|intelligence)\b', text_for_search))
            
            if not is_ai:
                continue
                
            # 생성일 4개월(120일) 경과 프로젝트 필터링
            repo_api_url = f"https://api.github.com/repos/{title}"
            api_headers = {"User-Agent": "Mozilla/5.0"}
            github_token = os.environ.get("GITHUB_TOKEN")
            if github_token:
                api_headers["Authorization"] = f"token {github_token}"
                
            try:
                import datetime
                repo_resp = requests.get(repo_api_url, headers=api_headers, timeout=10)
                if repo_resp.status_code == 200:
                    repo_data = repo_resp.json()
                    created_at_str = repo_data.get("created_at")
                    if created_at_str:
                        created_at = datetime.datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
                        four_months_ago = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=120)
                        if created_at < four_months_ago:
                            print(f"?? 필터링됨: {title} (생성일 {created_at_str}, 4개월 경과)")
                            continue
            except Exception as e:
                print(f"?? 생성일 확인 실패 {title}: {e}")
                
            stars_el = repo.select_one('a[href$="/stargazers"]')
            stars = 0
            if stars_el:
                stars = int(stars_el.text.strip().replace(',', ''))
                
            results.append({
                "title": title,
                "description": desc,
                "url": f"https://github.com{title_el['href']}",
                "source": "GitHub Trending",
                "points": stars,
                "published_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            if len(results) >= 8: break
            
        return results
    except Exception as e:
        print(f"GitHub Trending Scraping failed: {e}")
        return []

# ---------------------------------------------------------
# 4. 메인 실행 블록
# ---------------------------------------------------------
if __name__ == "__main__":
    feed = load_feed()
    
    new_items = scrape_hackernews() + scrape_github_trending() + scrape_techcrunch_ai() + scrape_dcinside()
    for item in new_items:
        item["title"] = clean_text(item["title"])
        
    items_to_summarize = []
    
    for item in new_items:
        if any(f.get("url") == item["url"] for f in feed):
            print(f"⏭️ 이미 처리됨(스킵): {item['title']}")
        else:
            items_to_summarize.append(item)
            
    if items_to_summarize:
        print(f"🚀 {len(items_to_summarize)}개의 뉴스 일괄 요약 시작...")
        
        # 출력 토큰 제한(Max Tokens)으로 인한 짤림을 방지하기 위해 8개씩 청크로 나눔
        summaries = []
        for i in range(0, len(items_to_summarize), 8):
            chunk = items_to_summarize[i:i+8]
            print(f"📦 청크 요약 중 ({i+1}~{i+len(chunk)} / {len(items_to_summarize)})")
            chunk_summaries = summarize_batch(chunk)
            
            # 실패 시 빈 문자열로 채워 길이 맞춤
            if not chunk_summaries or len(chunk_summaries) < len(chunk):
                chunk_summaries = [""] * len(chunk)
            summaries.extend(chunk_summaries)
        
        for i, item in enumerate(items_to_summarize):
            if i < len(summaries) and summaries[i]:
                summary_md = clean_text(summaries[i])
            else:
                fallback_cat = "오픈소스" if "GitHub" in item["source"] else "뉴스"
                summary_md = f"카테고리: {fallback_cat}\n> **[💡AI/에이전트] {item['title']}**\n> - **한줄요약**: 요약 실패 (API 통신 오류)\n> - **인사이트**: 없음\n> - **출처**: {item['source']} ({item['url']})"
            
            feed.insert(0, {
                "title": item["title"],
                "url": item["url"],
                "source": item["source"],
                "summary_md": summary_md,
                "points": item.get("points", 0),
                "published_at": item.get("published_at") or datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "fetched_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
            })
            

    # 50일 경과 데이터 필터링 및 포인트(핫한 순) 정렬
    fifty_days_ago_dt = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=50)
    valid_feed = []
    for item in feed:
        pub_str = item.get("published_at") or item.get("fetched_at")
        keep = True
        if pub_str:
            try:
                pub_date = datetime.datetime.fromisoformat(pub_str.replace("Z", "+00:00"))
                if pub_date.tzinfo is None:
                    pub_date = pub_date.replace(tzinfo=datetime.timezone.utc)
                if pub_date < fifty_days_ago_dt:
                    keep = False
            except Exception:
                pass
        if keep:
            valid_feed.append(item)
            
    def get_points(x):
        try: return int(x.get("points", 0))
        except: return 0
        
    valid_feed.sort(key=get_points, reverse=True)
    
    category_counts = {}
    new_feed = []
    
    for item in valid_feed:
        cat = "뉴스"
        summary_md = item.get("summary_md", "")
        for line in summary_md.split("\n"):
            if "카테고리:" in line:
                cat = line.split("카테고리:")[1].strip()
                break
                
        target = '뉴스'
        if '오픈소스' in cat: target = '오픈소스'
        elif '정보' in cat or '꿀팁' in cat: target = '정보'
        elif '커뮤니티' in cat: target = '커뮤니티'
        
        category_counts[target] = category_counts.get(target, 0) + 1
        if category_counts[target] <= 20:
            new_feed.append(item)
            
    feed = new_feed

    save_feed(feed)
    print("✅ 피드 업데이트 완료!")
