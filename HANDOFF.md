# AI Radar 핸드오프 (Hand-off) 문서

본 문서는 `ai-radar` 프로젝트의 인수인계 및 중점 검토 사항을 기록한 문서입니다. (작성일: 2026-09-13)

## 1. 현재까지 완료된 작업 내역 (v0.5)

### 📌 다중 모델 폴백(HA) 아키텍처 구축 (Backend)
- **주력 엔진 (GitHub Models)**: `gpt-4o-mini`를 사용하여 하루 150건의 넉넉한 한도로 쾌적한 AI 요약 수행 (`openai` SDK 활용).
- **보조 엔진 (Google Gemini)**: 깃허브 모델 토큰 만료나 서버 에러 시 즉시 `gemini-3.6-flash`로 우회(Fallback)하는 고가용성 루프(3회 재시도) 구축 완료. 구글의 일일 20건 쪼잔한 한도 문제를 완벽하게 회피했습니다.

### 📌 크롤링 볼륨 증가 및 타겟 소스 정밀화
- **Hacker News**: 최대 12개 추출 (Hot 순위)
- **GitHub Trending**: 최대 8개 추출 (Star 개수 파싱)
- **TechCrunch AI**: 신규 RSS 소스로 추가하여 기업 동향 및 공식 뉴스를 최대 5개 추출 (News 카테고리 보강). 총합 1회당 25개의 기사를 싹쓸이하여 Batch AI Summary 수행.

### 📌 프롬프트 엔지니어링 룰셋 엄격화
- **정보/꿀팁 카테고리 보호**: Gemini/GPT 프롬프트를 깐깐하게 수정하여, 단순 도구 소개는 강제로 `[오픈소스]`로 넘기고 오직 '무료 프로모션(예: 카카오 무료), 비용/토큰 절감 꿀팁' 등 금전적 이득을 주는 팁만 `[정보]` 칸에 할당되도록 강제.

### 📌 핫한 순위(Hotness Score) 기반의 정렬 UI 도입
- 기존의 수집 시간순(최신순) 렌더링을 폐기하고, GitHub Star 획득량과 Hacker News Upvote 숫자를 종합한 `points` 기반의 **내림차순 정렬 알고리즘** 적용.
- 프론트엔드 UI에 `🔥 [점수]` 형태의 오렌지색 뱃지를 부착하여 시각적 만족도 극대화. 다단(4열) 스크롤도 완벽 지원.

---

## 2. 중점적으로 검토해야 할 사항 (Review Focus)

다음 작업자(또는 선생님 본인)께서 추후 이 프로젝트를 유지보수하실 때 반드시 체크하셔야 할 핵심 포인트입니다.

### 🚨 A. GitHub Models 토큰 만료 관리
- `GH_MODELS_TOKEN`을 깃허브 Secrets에 저장하여 구동 중입니다. 만약 토큰 유효기간을 설정하셨다면, 만료 시 크롤러 봇이 보조 엔진(Gemini)으로 넘어가게 되며, Gemini마저 하루 20건 한도를 다 쓰면 완전히 뻗습니다. 토큰을 제때 갱신해 주세요!

### 🚨 B. GitHub Trending HTML 구조 변경 주의
- `scrape_github_trending()` 함수는 BeautifulSoup을 사용하여 DOM 구조(`article.Box-row`, `a.Link--muted`)를 직접 스크래핑합니다.
- 만약 깃허브 트렌딩 페이지의 UI/HTML 구조가 개편되면 해당 함수가 빈 배열 `[]`을 반환하게 됩니다. 오픈소스 란이 갑자기 텅 비기 시작한다면 가장 먼저 CSS Selector를 점검하셔야 합니다.

### 🚨 C. TechCrunch RSS 변경 주의
- `scrape_techcrunch_ai()` 함수는 `https://techcrunch.com/category/artificial-intelligence/feed/` RSS를 XML 파싱합니다. 테크크런치 측에서 URL이나 태그 구조를 변경하면 뉴스 란이 비어버릴 수 있습니다.

### 🚨 D. UI/UX 확장성 유지
- 현재 `index.html`은 CDN을 사용한 TailwindCSS를 불러오고 있습니다.
- 모바일(스마트폰)에서는 `grid-cols-1`, 태블릿 `grid-cols-2`, 데스크탑 `grid-cols-4`로 반응형이 꼼꼼하게 짜여 있습니다. Vibe-coding 스타일의 조잡한 그림자(Shadow)나 박스 테두리를 지양하고 심플한 밑줄(Border-bottom) 리스트로 깔끔하게 렌더링되도록 스타일을 엄격히 통제해 주시기 바랍니다.
