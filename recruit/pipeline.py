import json
import os
import time
import uuid
from datetime import datetime, timedelta, date
from pathlib import Path
from .database import Database, CN, now, digest
from .search import Fetcher, queries, FETCH_VERSION
from .extract import EXTRACTION_PROMPT, MATCH_PROMPT, json_object, validate_job
from .reports import generate
from .runtime import settings,DEFAULT_PROFILE

class AlreadyRunning(Exception):pass
class RunLock:
    def __init__(self,path):self.path=Path(path);self.file=None
    def __enter__(self):
        self.path.parent.mkdir(parents=True,exist_ok=True);self.file=self.path.open('a+b')
        self.file.seek(0);self.file.write(b'0');self.file.flush();self.file.seek(0)
        try:
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_NBLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)
        except OSError:self.file.close();raise AlreadyRunning('已有招聘任务正在执行')
        return self
    def __exit__(self,*args):
        if self.file:
            self.file.seek(0)
            if os.name=='nt':
                import msvcrt
                msvcrt.locking(self.file.fileno(),msvcrt.LK_UNLCK,1)
            else:
                import fcntl
                fcntl.flock(self.file.fileno(),fcntl.LOCK_UN)
            self.file.close()

def execution_day(trigger='manual',instant=None):
    current=instant or datetime.now(CN)
    current=current.astimezone(CN)
    # Scheduled recovery before 19:00 belongs to the preceding missed occurrence.
    if trigger=='schedule' and current.hour<19:current-=timedelta(days=1)
    return current.date().isoformat()

def run(root,bridge,trigger='manual',day=None,fetcher=None,recheck=False):
    root=Path(root);root.mkdir(parents=True,exist_ok=True)
    with RunLock(root/'data'/'collection.lock'):
        db=Database(root/'data'/'recruitment.sqlite3')
        try:return _run(db,root,bridge,trigger,day or execution_day(trigger),fetcher or Fetcher(root=root),recheck=recheck)
        finally:db.close()

def _run(db,root,bridge,trigger,day,fetcher,recheck=False):
    date.fromisoformat(day)
    run_id=str(uuid.uuid4());started=time.monotonic()
    with db.conn:
        db.conn.execute("UPDATE runs SET status='interrupted',finished_at=? WHERE status='running'",(now(),))
        db.conn.execute('INSERT INTO runs(id,execution_date,trigger,started_at,status) VALUES(?,?,?,?,?)',(run_id,day,trigger,now(),'running'))
    completed=db.conn.execute('SELECT r.* FROM completed_days d JOIN runs r ON d.run_id=r.id WHERE d.execution_date=?',(day,)).fetchone()
    if completed and not recheck:
        stats={'found':0,'verified_new':0,'duplicates':0}
        path,report=generate(db,run_id,stats,[],root,outcome='skipped')
        with db.conn:db.conn.execute("UPDATE runs SET status='skipped',finished_at=?,report_path=?,stats=? WHERE id=?",(now(),path,json.dumps(stats),run_id))
        write_log(root,run_id,day,'skipped',stats,[])
        return {'run_id':run_id,'status':'skipped','message':'该执行日已完成，未重复搜索、分析或推荐。','report':report,'report_path':path}
    errors=[];stats={'found':0,'verified_new':0,'duplicates':0};seen_urls=set();pages=[];new_ids=set();search_success=0;urls=[];audit=[]
    def budget():
        if time.monotonic()-started>840:raise TimeoutError('本次任务达到14分钟上限')
    def collect(query):
        budget();key='search:'+day+':'+digest(query)
        cached=db.cache_get(key)
        if cached is not None:return cached
        for attempt in range(2):
            try:
                result=bridge('search',{'query':query,'max_results':6})
                if not isinstance(result.get('sources'),list):raise ValueError('搜索接口未返回结构化来源')
                db.cache_set(key,result['sources']);return result['sources']
            except Exception:
                if attempt:raise
                time.sleep(1)
    try:
        explore=not db.cache_get('exploration-week:'+date.fromisoformat(day).strftime('%G-%V'))
        sources=[];search_success=0
        config=load_config(root);year=config.get('graduation_year',2027)
        match_prompt=MATCH_PROMPT.replace('2027',str(year))+(config.get('profile') or DEFAULT_PROFILE.replace('2027',str(year)))
        for query in queries(day,explore,year=year,keywords=config.get('keywords')):
            try:sources+=collect(query);search_success+=1
            except Exception as e:errors.append('搜索失败：'+type(e).__name__)
        for source in sources:
            url=source.get('url') or source.get('link')
            if not url or url in seen_urls:continue
            seen_urls.add(url)
        stats['found']=len(seen_urls)
        # Widen once to seven days when the near-window discovery is sparse.
        if len(seen_urls)<5 and search_success:
            start=(date.fromisoformat(day)-timedelta(days=7)).isoformat()
            try:
                extra=collect(f'{year} 校园招聘 自动化 电气 嵌入式 研发 after:{start}')
                sources+=extra;seen_urls.update(x.get('url') or x.get('link') for x in extra)
                stats['found']=len(seen_urls)
            except Exception as e:errors.append('扩展七天搜索失败：'+type(e).__name__)
        urls=list(dict.fromkeys(x.get('url') or x.get('link') for x in sources if x.get('url') or x.get('link')))[:36]
        for url in urls:
            budget();key='page:'+FETCH_VERSION+':'+day+':'+digest(url);page_started=time.monotonic()
            try:
                page=db.cache_get(key)
                if page is None:page=fetcher.fetch(url);db.cache_set(key,page)
                if len(page['text'])>=120:
                    pages.append(page);audit.append({'url':url,'final_url':page['url'],'ok':True,'method':page.get('method','http'),'text_chars':len(page['text']),'html_bytes':page.get('html_bytes'),'seconds':round(time.monotonic()-page_started,2)})
                else:
                    errors.append('页面内容不足，未推断岗位：'+url);audit.append({'url':url,'ok':False,'reason':'页面内容不足'})
            except Exception as e:
                errors.append('页面跳过：'+url+'（'+str(e)[:160]+'）');audit.append({'url':url,'ok':False,'reason':str(e)[:300],'seconds':round(time.monotonic()-page_started,2)})
        for offset in range(0,len(pages),4):
            budget();batch=pages[offset:offset+4]
            payload=[{'page_index':i,'url':p['url'],'text':p['text'][:16000],'links':p['links'][:40]} for i,p in enumerate(batch)]
            key='extraction:v1:'+digest(json.dumps(payload,ensure_ascii=False))
            try:
                result=db.cache_get(key)
                if result is None:
                    result=json_object(bridge('llm',{'system':EXTRACTION_PROMPT,'input':json.dumps(payload,ensure_ascii=False),'max_tokens':7000})['text'])
                    db.cache_set(key,result)
                items=result.get('jobs',[])
                if not isinstance(items,list):raise ValueError('岗位提取结构错误')
                for j in items[:20]:
                    i=j.get('page_index')
                    if not isinstance(i,int) or not 0<=i<len(batch):continue
                    job=validate_job(j,batch[i],config.get('official_domains',[]),graduation_year=year)
                    if not job:continue
                    job_id,is_new=db.upsert(job,run_id)
                    if is_new:stats['verified_new']+=1;new_ids.add(job_id)
                    else:stats['duplicates']+=1
            except Exception as e:errors.append('批量提取失败：'+type(e).__name__)
        candidates=[dict(r) for r in db.conn.execute("SELECT DISTINCT j.* FROM jobs j JOIN run_jobs r ON r.job_id=j.id WHERE r.run_id=? AND j.applied_date IS NULL AND j.status IN ('未投递','计划投递')",(run_id,))]
        for offset in range(0,len(candidates),10):
            budget();batch=candidates[offset:offset+10];pending=[]
            for j in batch:
                projection={k:j[k] for k in ('id','company','title','city','batch','description','recruitment_status')}
                h=digest('matching:v2:'+match_prompt+str(config.get('model',''))+json.dumps(projection,sort_keys=True,ensure_ascii=False))
                cached=db.cache_get('match:'+h)
                if cached:db.analyze(j['id'],cached,h)
                else:pending.append((projection,h))
            if not pending:continue
            try:
                result=json_object(bridge('llm',{'system':match_prompt,'input':json.dumps([x[0] for x in pending],ensure_ascii=False),'max_tokens':4000})['text'])
                expected={p['id']:(p,h) for p,h in pending};returned=set()
                for a in result.get('matches',[]):
                    if a.get('id') not in expected or a['id'] in returned:continue
                    p,h=expected[a['id']];returned.add(a['id'])
                    if p['batch']!=str(year)+'届校招' and a.get('eligible')=='是':a['eligible']='未知'
                    db.analyze(a['id'],a,h);db.cache_set('match:'+h,a)
                if returned!=set(expected):errors.append('部分岗位未收到有效匹配结果，保留待分析')
            except Exception as e:errors.append('MiniMax 批量匹配失败：'+type(e).__name__)
        if not search_success:errors.append('没有成功的联网搜索；不能将失败冒充无新岗位')
        if explore and search_success and pages and not errors:db.cache_set('exploration-week:'+date.fromisoformat(day).strftime('%G-%V'),{'run_id':run_id})
    except Exception as e:errors.append('任务中断：'+type(e).__name__)
    path,report=generate(db,run_id,stats,errors,root)
    stats['pages_readable']=sum(x['ok'] for x in audit);stats['pages_unavailable']=sum(not x['ok'] for x in audit)
    stats['browser_pages']=sum(x.get('method')=='browser' and x['ok'] for x in audit)
    status='partial' if errors else 'success'
    with db.conn:
        db.conn.execute('UPDATE runs SET finished_at=?,status=?,stats=?,errors=?,report_path=? WHERE id=?',(now(),status,json.dumps(stats),json.dumps(errors,ensure_ascii=False),path,run_id))
        # Individual inaccessible sites are recorded but need not cause a new
        # collection every time run-now is clicked. Real stage failures remain retryable.
        failed_stage=any(e.startswith(('批量提取失败','MiniMax 批量匹配失败','部分岗位未收到','任务中断','搜索失败','没有成功的联网搜索')) for e in errors)
        if search_success and (not urls or pages) and not failed_stage:
            db.conn.execute('INSERT OR IGNORE INTO completed_days VALUES(?,?)',(day,run_id))
    write_log(root,run_id,day,status,stats,errors)
    (Path(root)/'logs'/(run_id+'.sources.json')).write_text(json.dumps({'run_id':run_id,'fetch_version':FETCH_VERSION,'sources':audit},ensure_ascii=False,indent=2),encoding='utf-8')
    return {'run_id':run_id,'status':status,'stats':stats,'errors':errors,'report':report,'report_path':path}

def write_log(root,run_id,day,status,stats,errors,finished_at=None):
    directory=Path(root)/'logs';directory.mkdir(exist_ok=True)
    (directory/(run_id+'.json')).write_text(json.dumps({'run_id':run_id,'execution_date':day,'finished_at':finished_at or now(),'status':status,'stats':stats,'errors':errors},ensure_ascii=False,indent=2),encoding='utf-8')

def load_config(root):
    return settings()

def finish_interrupted(root,error_code):
    """Called after a worker has exited; never mark a different live worker failed."""
    root=Path(root)
    with RunLock(root/'data'/'collection.lock'):
        db=Database(root/'data'/'recruitment.sqlite3')
        try:
            records=db.conn.execute("SELECT * FROM runs WHERE status='running' ORDER BY started_at").fetchall()
            result={'status':'failed','message':'任务已停止，未发现待收尾执行记录。'}
            for record in records:
                counts=db.conn.execute('SELECT count(*),coalesce(sum(is_new),0) FROM run_jobs WHERE run_id=?',(record['id'],)).fetchone()
                stats={'verified_new':counts[1],'duplicates':counts[0]-counts[1]}
                errors=['Python工作进程异常结束：'+str(error_code)[:100]+'；部分统计未完成，已保存的数据与投递记录保留。']
                path,report=generate(db,record['id'],stats,errors,root)
                with db.conn:db.conn.execute("UPDATE runs SET status='failed',finished_at=?,stats=?,errors=?,report_path=? WHERE id=?",(now(),json.dumps(stats),json.dumps(errors,ensure_ascii=False),path,record['id']))
                write_log(root,record['id'],record['execution_date'],'failed',stats,errors)
                result={'run_id':record['id'],'status':'failed','report':report,'report_path':path}
            return result
        finally:db.close()
