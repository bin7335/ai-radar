"""Community curation before masking or ranking; no network or model dependency."""
import re
import unicodedata
from urllib.parse import parse_qs, urlparse


def is_community(item):
    host = (urlparse(item.get("url", "")).hostname or "").lower()
    return (
        "dcinside" in item.get("source", "").lower()
        or host == "gall.dcinside.com"
        or item.get("category") == "커뮤니티"
        or bool(re.search(r"카테고리\**\s*:\s*커뮤니티", item.get("summary_md", "")))
    )


def rejection_reason(item):
    if not is_community(item):
        return None
    url = urlparse(item.get("url", ""))
    query = parse_qs(url.query)
    if (url.hostname == "gall.dcinside.com"
            and query.get("id") == ["thesingularity"]
            and query.get("no") == ["1459400"]):
        return "신고된 성적 낚시글"
    title = unicodedata.normalize("NFKC", item.get("raw_title") or item.get("title", "")).lower()
    # Match explicit nouns, not normal verbs such as '써보지', '해보지', '자지 않음'.
    sexual = r"야짤|후방주의|노출짤|딸감|젖탱|(?:^|[\s\W])(?:보지)(?:$|[\s\W]|사진|그림|짤|를|가|는|도)|(?:^|[\s\W])자지(?:사진|그림|짤|를|가|는|도|\s*(?:사진|그림|짤))"
    policy_discussion = bool(re.search(r"차단|탐지|정책|필터|안전|규제|방지", title))
    if re.search(r"야동|섹스|포르노|\bnsfw\b", title) and not policy_discussion:
        return "성적 낚시/음란 콘텐츠"
    if re.search(sexual, title):
        return "성적 낚시/음란 콘텐츠"
    if re.search(r"개추|비추|보[고구]가|꼴리|특슬람|특까|갈드컵|안읽은.*많네", title):
        return "추천 유도/조롱/낚시"
    if re.search(r"그냥.*goat|죽어가는 사람들을 위해 가속|내\s*★\s*사진|이 스캠기업은 뭐지", title):
        return "정보 없는 잡담/논쟁"
    return None


def filter_feed(items):
    return [item for item in items if rejection_reason(item) is None]


def valid_evidence(row, item):
    evidence = row.get("evidence")
    return (row.get("decision") == "keep" and isinstance(evidence, str)
            and len(evidence.strip()) >= 15
            and evidence.strip() in item.get("description", "")[:5000])
