import json
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import datetime
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from recruit.database import Database,CN,canonical_url
from recruit.pipeline import run,RunLock,AlreadyRunning,execution_day,finish_interrupted
from recruit.extract import validate_job,grounded_date

DAY='2026-11-08'
def fixture(title='电气研发工程师',**patch):
    j=dict(company='测试工业股份有限公司',title=title,city='上海',batch='2027届校招',application_url='https://example.org/jobs/42?utm_source=test',source_url='https://example.org/source/42',published_date=DAY,
           description='2027届硕士，负责PLC控制系统设计和软件研发。',verification='公开页面已核验',recruitment_status='未知',evidence={})
    j.update(patch);return j

class StorageTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.path=Path(self.tmp.name)/'test.sqlite';self.db=Database(self.path)
    def tearDown(self):self.db.close();self.tmp.cleanup()
    def test_cross_source_merge_and_distinct_positions(self):
        a,new=self.db.upsert(fixture());b,new2=self.db.upsert(fixture(application_url='https://another.org/job/7',source_url='https://another.org/job/7'))
        self.assertTrue(new);self.assertFalse(new2);self.assertEqual(a,b);self.assertEqual(len(self.db.get(a)['sources']),2)
        c,_=self.db.upsert(fixture(title='嵌入式软件研发工程师'));self.assertNotEqual(a,c)
    def test_user_state_survives_recollection_and_reopen_database(self):
        job_id,_=self.db.upsert(fixture());j=self.db.get(job_id)
        self.db.update_user(job_id,{'version':j['version'],'status':'已投递','platform':'官网','notes':'已完成申请','favorite':True,'applied_date':DAY})
        self.db.upsert(fixture(description='2027届硕士，研发设计。',recruitment_status='已结束'))
        self.db.close();self.db=Database(self.path);j=self.db.get(job_id)
        self.assertEqual(j['status'],'已投递');self.assertEqual(j['applied_date'],DAY);self.assertEqual(j['notes'],'已完成申请');self.assertTrue(j['favorite']);self.assertEqual(len(j['history']),1)
        self.assertEqual(self.db.conn.execute('PRAGMA integrity_check').fetchone()[0],'ok')
    def test_status_correction_history_filters_and_conflict(self):
        job_id,_=self.db.upsert(fixture());self.db.update_user(job_id,{'version':0,'status':'面试中'})
        self.assertEqual(self.db.list(status='已投递及后续')['total'],1)
        with self.assertRaises(ValueError):self.db.update_user(job_id,{'version':0,'status':'未通过'})
        self.db.update_user(job_id,{'version':1,'status':'计划投递','notes':'修正误标'})
        self.assertEqual(self.db.list(status='计划投递')['total'],1);self.assertEqual(len(self.db.get(job_id)['history']),2)
        with self.assertRaises(ValueError):self.db.update_user(job_id,{'version':2,'description':'非法覆盖'})
    def test_new_batch_is_linked(self):
        old,_=self.db.upsert(fixture(batch='2026届校招'));new,_=self.db.upsert(fixture())
        self.assertNotEqual(old,new);self.assertEqual(self.db.get(new)['related_id'],old)
    def test_reopening_is_linked_and_repeat_is_stable(self):
        old,_=self.db.upsert(fixture(published_date='2026-08-01'));new,is_new=self.db.upsert(fixture(description='新的研发岗位职责与技术要求'))
        again,is_new2=self.db.upsert(fixture(description='新的研发岗位职责与技术要求'))
        self.assertNotEqual(old,new);self.assertTrue(is_new);self.assertFalse(is_new2);self.assertEqual(new,again);self.assertEqual(self.db.get(new)['related_id'],old)
    def test_official_application_link_wins(self):
        job_id,_=self.db.upsert(fixture(official=True,application_url='https://official.example.org/42'))
        self.db.upsert(fixture(application_url='https://aggregator.example.org/42'))
        self.assertEqual(self.db.get(job_id)['application_url'],'https://official.example.org/42')
    def test_url_keeps_position_ids_and_hash_routes(self):
        self.assertEqual(canonical_url('https://EXAMPLE.org/job?id=42&utm_source=x'),'https://example.org/job?id=42')
        self.assertNotEqual(canonical_url('https://example.org/#/job/42'),canonical_url('https://example.org/#/job/43'))

class EvidenceTest(unittest.TestCase):
    def test_no_crawl_date_as_publication(self):
        page={'url':'https://example.org/1','text':'测试工业 电气研发工程师 2027届校园招聘 联系日期2026-11-08','links':[]}
        j={'company':'测试工业','title':'电气研发工程师','published_date':DAY,'evidence':{'company':'测试工业','title':'电气研发工程师'}}
        result=validate_job(j,page);self.assertIsNone(result['published_date']);self.assertEqual(result['batch'],'2027届校招')
        j['company']='虚构公司';self.assertIsNone(validate_job(j,page))
    def test_date_requires_literal_source(self):
        self.assertIsNone(grounded_date(DAY,'2026年招聘'));self.assertEqual(grounded_date(DAY,'发布日期2026年11月8日'),DAY)
    def test_null_dates_and_unverified_application_redirect(self):
        page={'url':'https://example.org/job/42','text':'测试工业 电气研发工程师 2027届校园招聘','links':['https://other.example.org/profile']}
        j={'company':'测试工业','title':'电气研发工程师','application_url':'https://other.example.org/profile','evidence':{'company':'测试工业','title':'电气研发工程师','published_date':None,'deadline':None}}
        result=validate_job(j,page);self.assertIsNone(result['published_date']);self.assertEqual(result['application_url'],page['url'])

class PipelineTest(unittest.TestCase):
    def setUp(self):self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.calls=[]
    def tearDown(self):self.tmp.cleanup()
    def bridge(self,op,args):
        self.calls.append(op)
        if op=='search':return {'sources':[{'url':'https://example.org/jobs/42'}]}
        if '结构化' in args['system']:
            return {'text':json.dumps({'jobs':[dict(page_index=0,company='测试工业',title='电气研发工程师',city='上海',published_date=DAY,description='负责PLC控制系统设计和软件研发。',evidence={'company':'测试工业','title':'电气研发工程师','published_date':'发布日期2026-11-08'})]},ensure_ascii=False)}
        items=json.loads(args['input']);return {'text':json.dumps({'matches':[dict(id=j['id'],score=90,eligible='是',rd='是',company_tier=3,reason='2027届硕士，PLC研发设计匹配') for j in items]},ensure_ascii=False)}
    class Fetch:
        def fetch(self,url):return {'url':url,'text':('测试工业 电气研发工程师 上海 2027届校园招聘 发布日期2026-11-08 负责PLC控制系统设计和软件研发。'+'岗位资料 '*30),'links':[],'jsonld':[]}
    def test_complete_repeat_and_no_applied_recommendation(self):
        result=run(self.root,self.bridge,day=DAY,fetcher=self.Fetch());self.assertEqual(result['status'],'success');self.assertEqual(result['stats']['verified_new'],1);self.assertEqual(result['stats']['worthy_today'],1)
        db=Database(self.root/'data/recruitment.sqlite3');job=db.list()['items'][0];db.update_user(job['id'],{'version':0,'status':'已投递','applied_date':DAY});db.close()
        count=len(self.calls);again=run(self.root,self.bridge,day=DAY,fetcher=self.Fetch());self.assertEqual(again['status'],'skipped');self.assertEqual(len(self.calls),count);self.assertEqual(again['stats']['worthy_today'] if 'stats' in again else 0,0)
        next_day=run(self.root,self.bridge,day='2026-11-09',fetcher=self.Fetch());self.assertEqual(next_day['stats']['worthy_today'],0)
        db=Database(self.root/'data/recruitment.sqlite3');self.assertEqual(db.list()['total'],1);self.assertEqual(db.list()['items'][0]['status'],'已投递');db.close()
    def test_failure_is_bounded_and_does_not_damage_state(self):
        count=0
        def broken(op,args):
            nonlocal count
            count+=1;raise RuntimeError('offline')
        result=run(self.root,broken,day=DAY,fetcher=self.Fetch());self.assertEqual(result['status'],'partial');self.assertLessEqual(count,14);self.assertIn('没有成功的联网搜索',result['report']);self.assertTrue(Path(result['report_path']).exists())
    def test_process_lock(self):
        with RunLock(self.root/'lock'):
            with self.assertRaises(AlreadyRunning):
                with RunLock(self.root/'lock'):pass
        with RunLock(self.root/'lock'):pass
    def test_recovery_execution_date(self):
        self.assertEqual(execution_day('schedule',datetime(2026,11,9,8,tzinfo=CN)),DAY)
        self.assertEqual(execution_day('schedule',datetime(2026,11,9,20,tzinfo=CN)),'2026-11-09')
        self.assertEqual(execution_day('manual',datetime(2026,11,9,8,tzinfo=CN)),'2026-11-09')
    def test_aborted_worker_has_durable_failure_report_without_losing_jobs(self):
        db=Database(self.root/'data/recruitment.sqlite3')
        with db.conn:db.conn.execute("INSERT INTO runs(id,execution_date,trigger,started_at,status) VALUES('crash',?,'schedule',?,'running')",(DAY,DAY+'T19:00:00+08:00'))
        job_id,_=db.upsert(fixture(),run_id='crash');db.update_user(job_id,{'version':0,'status':'面试中','notes':'重要记录'});db.close()
        result=finish_interrupted(self.root,'RUN_TIMEOUT');self.assertEqual(result['status'],'failed');self.assertIn('RUN_TIMEOUT',result['report'])
        db=Database(self.root/'data/recruitment.sqlite3');self.assertEqual(db.get(job_id)['status'],'面试中');self.assertEqual(db.get(job_id)['notes'],'重要记录');self.assertEqual(db.conn.execute('SELECT status FROM runs').fetchone()[0],'failed');db.close()

if __name__=='__main__':unittest.main()
