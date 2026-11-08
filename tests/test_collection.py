import gzip
import json
import sys
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recruit.search import Fetcher,access_challenge,structured_text,MAX_BYTES,MAX_DECODED_BYTES,SafeRedirect

class Headers(dict):
    def get_content_type(self):return 'text/html'
    def get_content_charset(self):return 'utf-8'
class Response(BytesIO):
    def __init__(self,body,encoding=None):super().__init__(body);self.url='https://example.org/job';self.headers=Headers({'Content-Encoding':encoding} if encoding else {})
    def __enter__(self):return self
    def __exit__(self,*args):self.close()
class Opener:
    def __init__(self,body,encoding=None):self.body=body;self.encoding=encoding
    def open(self,*args,**kwargs):return Response(self.body,self.encoding)

class CollectionTest(unittest.TestCase):
    def test_large_public_html_is_supported_without_removing_upper_bound(self):
        body=b'<html><script>'+b' '*1_600_000+b'</script><body>public job</body></html>'
        with patch('recruit.search.public_url'),patch('recruit.search.build_opener',return_value=Opener(body)):
            final,text=Fetcher().raw('https://example.org/job',page=True)
        self.assertIn('public job',text);self.assertGreater(len(text),1_200_000)
        with patch('recruit.search.public_url'),patch('recruit.search.build_opener',return_value=Opener(b'x'*(MAX_BYTES+1))):
            with self.assertRaisesRegex(ValueError,'PAGE_SIZE_LIMIT'):Fetcher().raw('https://example.org/job',page=True)
    def test_gzip_and_decompression_limit(self):
        with patch('recruit.search.public_url'),patch('recruit.search.build_opener',return_value=Opener(gzip.compress(b'<html>job</html>'),'gzip')):
            self.assertIn('job',Fetcher().raw('https://example.org/job',page=True)[1])
        oversized=gzip.compress(b'x'*(MAX_DECODED_BYTES+1))
        with patch('recruit.search.public_url'),patch('recruit.search.build_opener',return_value=Opener(oversized,'gzip')):
            with self.assertRaisesRegex(ValueError,'DECODED_SIZE_LIMIT'):Fetcher().raw('https://example.org/job',page=True)
    def test_real_challenge_is_blocked_but_public_job_with_private_contacts_is_not(self):
        self.assertTrue(access_challenge('安全验证 - BOSS直聘 请完成以下验证'))
        self.assertTrue(access_challenge('登录后查看职位详情'))
        self.assertFalse(access_challenge('请妥善保管短信验证码。188****3824（登录后查看联系方式）岗位职责：PLC开发'))
    def test_shell_uses_renderer_and_never_returns_login_page(self):
        events=[]
        def renderer(url,authorize,root):
            events.append(url);return {'url':url,'text':'岗位职责：PLC研发。'*30,'links':[],'jsonld':[],'method':'browser'}
        fetcher=Fetcher(renderer=renderer)
        with patch.object(fetcher,'check_robots'),patch.object(fetcher,'raw',return_value=('https://example.org/job','<html><div id="app"></div></html>')):
            page=fetcher.fetch('https://example.org/job')
        self.assertEqual(page['method'],'browser');self.assertEqual(len(events),1)
        fetcher=Fetcher(renderer=lambda *args:self.fail('must never render past a challenge'))
        with patch.object(fetcher,'check_robots'),patch.object(fetcher,'raw',return_value=('https://example.org/job','<body>安全验证 请完成验证</body>')):
            with self.assertRaisesRegex(ValueError,'CAPTCHA_OR_LOGIN_REQUIRED'):fetcher.fetch('https://example.org/job')
    def test_structured_dates_only_come_from_explicit_jobposting(self):
        data=[{'@type':'Organization','datePosted':'2026-11-08'},{'@type':'JobPosting','title':'PLC研发','datePosted':'2026-11-06','description':'<p>负责PLC控制系统设计。</p>'}]
        text=structured_text(data)
        self.assertIn('2026-11-06',text);self.assertNotIn('2026-11-08',text);self.assertIn('负责PLC控制系统设计。',text)
    def test_redirect_checks_destination_robots_before_following(self):
        def blocked(url):raise ValueError('ROBOTS_DISALLOW')
        with patch('recruit.search.public_url'):
            with self.assertRaisesRegex(ValueError,'ROBOTS_DISALLOW'):
                SafeRedirect(blocked).redirect_request(None,None,302,'',{},'https://example.org/disallowed')

if __name__=='__main__':unittest.main()
