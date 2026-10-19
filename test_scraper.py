import threading
import unittest
from unittest.mock import MagicMock, patch
import scraper


class TestScraper(unittest.TestCase):
    def test_extract_video_id(self):
        self.assertEqual(scraper.extract_video_id("jNQXAC9IVRw"), "jNQXAC9IVRw")
        self.assertEqual(scraper.extract_video_id("https://www.youtube.com/watch?v=jNQXAC9IVRw"), "jNQXAC9IVRw")
        self.assertEqual(scraper.extract_video_id("https://youtu.be/jNQXAC9IVRw?si=123"), "jNQXAC9IVRw")
        self.assertEqual(scraper.extract_video_id("https://www.youtube.com/shorts/jNQXAC9IVRw"), "jNQXAC9IVRw")
        self.assertEqual(scraper.extract_video_id("https://www.youtube.com/live/jNQXAC9IVRw"), "jNQXAC9IVRw")
        self.assertEqual(scraper.extract_video_id("youtube.com/watch?v=jNQXAC9IVRw"), "jNQXAC9IVRw")
        self.assertIsNone(scraper.extract_video_id(""))
        self.assertIsNone(scraper.extract_video_id("https://example.com/not-youtube"))

    def test_get_comment_date(self):
        self.assertEqual(scraper.get_comment_date({'timestamp': 1700000000}), "2023-11-14 22:13:20")
        self.assertIsNotNone(scraper.get_comment_date({'_time_text': '2 days ago (edited)'}))
        self.assertEqual(scraper.get_comment_date({'time_text': '2024-05-01 12:00:00'}), "2024-05-01 12:00:00")

    def test_get_comments_scraper_gen_ytdlp_only(self):
        fake_comments = [
            {
                'id': 'c1',
                'parent': 'root',
                'text': 'First top-level comment',
                'author': '@Alice',
                'author_id': 'UC1',
                'like_count': None,
                'timestamp': 1700000000,
            },
            {
                'id': 'c1.r1',
                'parent': 'c1',
                'text': 'Reply to first comment',
                'author': '@Bob',
                'author_id': 'UC2',
                'like_count': 5,
                'timestamp': 1700000100,
            },
            {
                'id': 'c2',
                'parent': 'root',
                'text': 'Second top-level comment',
                'author': '@Charlie',
                'author_id': 'UC3',
                'like_count': 12,
                'timestamp': 1700000200,
            },
        ]

        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__.return_value = mock_ydl_instance
        mock_ie = MagicMock()
        mock_ie._get_comments = lambda *a, **kw: iter(fake_comments)
        mock_ydl_instance.get_info_extractor.return_value = mock_ie

        def fake_extract_info(url, download=False, process=False):
            mock_ie._get_comments()
            return {'title': 'Test Video'}

        mock_ydl_instance.extract_info.side_effect = fake_extract_info

        with patch('scraper.yt_dlp.YoutubeDL', return_value=mock_ydl_instance) as mock_ydl_cls:
            # 1. With replies included
            chunks = list(scraper.get_comments_scraper_gen("jNQXAC9IVRw", sort_mode='recent', include_replies=True))
            opts = mock_ydl_cls.call_args[0][0]
            self.assertEqual(opts['extractor_args']['youtube']['comment_sort'], ['new'])
            self.assertEqual(opts['extractor_args']['youtube']['max_comments'], ['all', 'all', 'all', 'all'])

            result_chunk = [c for c in chunks if 'result' in c][0]
            results = result_chunk['result']
            self.assertEqual(len(results), 3)
            self.assertEqual(results[0]['votes'], '0')
            self.assertEqual(results[0]['reply_count'], 1)
            self.assertTrue(results[1]['is_reply'])
            self.assertEqual(results[1]['votes'], '5')

            # 2. Without replies (de-biased top-level only)
            mock_ie._get_comments = lambda *a, **kw: iter(fake_comments)
            chunks_no_replies = list(
                scraper.get_comments_scraper_gen("jNQXAC9IVRw", sort_mode='popular', include_replies=False)
            )
            opts2 = mock_ydl_cls.call_args[0][0]
            self.assertEqual(opts2['extractor_args']['youtube']['comment_sort'], ['top'])
            self.assertEqual(opts2['extractor_args']['youtube']['max_comments'], ['all', 'all', '0', '0'])

            res2 = [c for c in chunks_no_replies if 'result' in c][0]['result']
            self.assertEqual(len(res2), 2)
            self.assertTrue(all(not c['is_reply'] for c in res2))

    def test_stop_event_cancellation(self):
        stop_ev = threading.Event()
        stop_ev.set()
        mock_ydl_instance = MagicMock()
        mock_ydl_instance.__enter__.return_value = mock_ydl_instance
        mock_ydl_instance.get_info_extractor.return_value = MagicMock()

        with patch('scraper.yt_dlp.YoutubeDL', return_value=mock_ydl_instance):
            chunks = list(scraper.get_comments_scraper_gen("jNQXAC9IVRw", stop_event=stop_ev))
            res_chunk = [c for c in chunks if 'result' in c][0]
            self.assertTrue(res_chunk['aborted'])
            self.assertEqual(res_chunk['result'], [])


if __name__ == '__main__':
    unittest.main()
