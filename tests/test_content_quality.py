import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'src'))
import main
from content_quality import filter_feed, rejection_reason


def community(title, **fields):
    return dict(title=title, source='DCInside (AI 활용)', url='https://gall.dcinside.com/mgallery/board/view/?id=ai_utilize&no=10', **fields)


class QualityTests(unittest.TestCase):
    def test_reported_post_and_masked_url_variants(self):
        self.assertIsNotNone(rejection_reason(community('GPT가 그려준 보지 보구가')))
        item = community('GPT가 그려준 ★')
        item['url'] = 'https://gall.dcinside.com/mgallery/board/view/?page=2&no=1459400&id=thesingularity'
        self.assertIsNotNone(rejection_reason(item))
        item['url'] = item['url'].replace('thesingularity', 'ai_utilize')
        self.assertIsNone(rejection_reason(item))

    def test_noise_and_high_points(self):
        for title in ['AI 위험 체감안되면 개추 ㅋㅋ', 'GPT 야짤 모음', '내 ★ 사진 넣어놓음', '이 모델 GOAT 보구가']:
            self.assertEqual(filter_feed([community(title, points=99999)]), [])

    def test_useful_posts_and_korean_verbs(self):
        for title in ['GPT 써보지 않고 비교하면 안 되는 이유', '에이전트는 자지 않음: 야간 자동화 실험',
                      'Claude API 비용 40% 절감 방법', 'NSFW 탐지 필터 구현 비교', '음란물 차단 정책 변경 분석']:
            self.assertIsNone(rejection_reason(community(title)))

    def test_source_and_category_scope(self):
        self.assertIsNone(rejection_reason(dict(title='추천 개추', source='TechCrunch AI')))
        self.assertIsNotNone(rejection_reason(dict(title='추천 개추', source='Other', category='커뮤니티')))
        self.assertIsNotNone(rejection_reason(community('정제된 제목', raw_title='GPT 야짤 모음')))

    def summarize(self, rows, items):
        response = SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(rows)))])
        client = SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kwargs: response)))
        with patch.object(main, 'or_client', client), patch.object(main, 'gemini_client', None), patch.dict(main.os.environ, {'OPENROUTER_MODELS': 'test'}):
            return main.summarize_batch(items)

    def test_indexed_keep_exclude_and_missing_evidence(self):
        body = '동일한 입력 100개로 비교한 결과 처리 시간이 30% 줄었습니다.'
        items = [community('잡담'), community('비교 실험', description=body)]
        row = dict(id=1, decision='keep', category='커뮤니티', evidence=body, one_line='30% 감소')
        result = self.summarize([row, dict(id=0, decision='exclude')], items)
        self.assertIsNone(result[0])
        self.assertTrue(result[1]['quality_reviewed'])
        self.assertEqual(self.summarize([dict(row, evidence='지어낸 일반적인 인사이트와 근거 없는 분석')], items), {})
        self.assertEqual(self.summarize([row, row], items), {})
        self.assertEqual(self.summarize([dict(row, decision='unknown')], items), {})

    def test_existing_unreviewed_post_is_queued_again(self):
        old = community('비교 실험', summary_status='ok')
        _, queued, _ = main.update_feed([old], [community('비교 실험', description='실제 본문')], main.now_iso())
        self.assertEqual(len(queued), 1)
        self.assertEqual(queued[0]['summary_status'], 'pending')

    def test_pipeline_excludes_failed_and_rejected_community_even_if_scraper_fails(self):
        for results in ({}, {0: None}):
            with self.subTest(results=results), tempfile.TemporaryDirectory() as folder:
                directory = Path(folder)
                with patch.object(main, 'OUTPUT_FILE', directory / 'feed.json'), \
                     patch.object(main, 'STATUS_FILE', directory / 'status.json'), \
                     patch.object(main, 'scrape_hackernews', return_value=[]), \
                     patch.object(main, 'scrape_github_trending', return_value=[]), \
                     patch.object(main, 'scrape_techcrunch_ai', return_value=[]), \
                     patch.object(main, 'scrape_dcinside', return_value=[community('비교 실험')]), \
                     patch.object(main, 'summarize_batch', return_value=results):
                    main.save_json(main.OUTPUT_FILE, [community('추천 개추')])
                    main.run_pipeline()
                    self.assertEqual(main.load_feed(), [])

    def test_scraper_filters_before_ranking_and_requires_body(self):
        listing = '<table>' + ''.join(
            f'<tr class="us-post"><td class="gall_num">{i}</td><td class="gall_tit"><a href="/mgallery/board/view/?id=ai_utilize&no={i}">{title}</a></td><td class="gall_recommend">{100-i}</td></tr>'
            for i, title in enumerate(['GPT 야짤', '비교 실험', '본문 없는 글'], 1)) + '</table>'
        urls = []
        def get(url, **kwargs):
            urls.append(url)
            if 'lists' in url:
                text = listing
            elif 'no=2' in url:
                text = '<div class="write_div">' + '같은 입력으로 모델을 비교하여 시간과 비용을 측정했습니다. ' * 3 + '</div>'
            else:
                text = '<div>차단 페이지</div>'
            return SimpleNamespace(text=text, raise_for_status=lambda: None)
        with patch.object(main.requests, 'get', side_effect=get), patch.object(main.time, 'sleep'):
            posts = main.scrape_dcinside()
        self.assertEqual(len(posts), 2)
        self.assertTrue(all(post['title'] == '비교 실험' for post in posts))
        self.assertFalse(any('no=1' in url for url in urls))


if __name__ == '__main__':
    unittest.main()
