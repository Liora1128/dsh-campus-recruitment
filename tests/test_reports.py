import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recruit.database import Database
from recruit.reports import generate

class ReportTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.db=Database(self.root/'data/test.sqlite3')
        with self.db.conn:
            self.db.conn.execute("INSERT INTO runs(id,execution_date,trigger,started_at,status,stats) VALUES('previous','2026-11-08','fixture','2026-11-08T17:00:00+08:00','partial',?)",(json.dumps({'found':7,'verified_new':3,'ai_passed':2}),))
            self.db.conn.execute("INSERT INTO runs(id,execution_date,trigger,started_at,status) VALUES('current','2026-11-08','fixture','2026-11-08T19:00:00+08:00','running')")
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_skipped_report_does_not_claim_zero_search_results(self):
        stats={'found':0,'verified_new':0};path,report=generate(self.db,'current',stats,[],self.root,outcome='skipped')
        self.assertIn('已跳过（同日防重）',report);self.assertIn('本次未进行联网搜索',report)
        self.assertIn('previous',report);self.assertIn('新增岗位 3 条',report)
        self.assertNotIn('今日暂无符合条件的新岗位',report);self.assertNotIn('本次搜索发现页面数：0',report)
        self.assertFalse(stats['collection_performed']);self.assertTrue(Path(path).exists())
    def test_ineligible_automatic_alert_is_hidden_but_user_favorite_is_preserved(self):
        job_id,_=self.db.upsert({'company':'示例公司','title':'博士控制研发岗','city':'示例市','batch':'2027届校招','application_url':'https://example.org/job/1'})
        self.db.analyze(job_id,{'score':50,'eligible':'否','rd':'是','reason':'学历不符'},'fixture')
        with self.db.conn:self.db.conn.execute("UPDATE jobs SET change_note='招聘页面状态变化：招聘中' WHERE id=?",(job_id,))
        _,report=generate(self.db,'previous',{},[],self.root)
        self.assertNotIn('博士控制研发岗',report)
        self.db.update_user(job_id,{'version':0,'favorite':True})
        _,report=generate(self.db,'previous',{},[],self.root)
        self.assertIn('博士控制研发岗',report)

if __name__=='__main__':unittest.main()
