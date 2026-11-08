from __future__ import annotations
import hashlib
import json
import re
import sqlite3
import unicodedata
import uuid
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode

CN = timezone(timedelta(hours=8), 'Asia/Shanghai')
STATES = ['未投递', '计划投递', '已投递', '测评中 / 笔试中', '面试中', '已录用 / Offer', '未通过', '不感兴趣', '招聘已结束']
APPLIED = STATES[2:7]
def now(): return datetime.now(CN).isoformat(timespec='seconds')
def norm(value): return re.sub(r'\s+', '', unicodedata.normalize('NFKC', value or '')).casefold()
def company_key(value): return re.sub(r'(股份有限公司|有限责任公司|有限公司)$', '', norm(value))
def canonical_url(url):
    p = urlsplit(url.strip())
    if p.scheme not in ('https', 'http') or not p.hostname or p.username or p.password:
        raise ValueError('投递链接必须是公开 HTTP(S) 地址')
    params = [(k,v) for k,v in parse_qsl(p.query, keep_blank_values=True)
              if not k.lower().startswith('utm_') and k.lower() not in ('spm','from','source','ref','trackingid')]
    # Hash routes sometimes contain the real position id. Preserve those routes.
    fragment = p.fragment if ('/' in p.fragment or '=' in p.fragment) else ''
    return urlunsplit((p.scheme.lower(), p.netloc.lower(), p.path.rstrip('/') or '/', urlencode(sorted(params)), fragment))
def digest(value): return hashlib.sha256(value.encode('utf-8')).hexdigest()

SCHEMA = '''
PRAGMA foreign_keys=ON;
CREATE TABLE IF NOT EXISTS jobs(
 id TEXT PRIMARY KEY, company TEXT NOT NULL, company_key TEXT NOT NULL,
 title TEXT NOT NULL, city TEXT NOT NULL DEFAULT '', batch TEXT NOT NULL DEFAULT '未知',
 official_id TEXT NOT NULL DEFAULT '', application_url TEXT NOT NULL, official INTEGER NOT NULL DEFAULT 0,
 published_date TEXT, deadline TEXT, description TEXT NOT NULL DEFAULT '', evidence TEXT NOT NULL DEFAULT '{}',
 verification TEXT NOT NULL DEFAULT '待核实', recruitment_status TEXT NOT NULL DEFAULT '未知',
 score INTEGER, reason TEXT NOT NULL DEFAULT '', eligible TEXT NOT NULL DEFAULT '未知', rd TEXT NOT NULL DEFAULT '未知',
 company_tier INTEGER NOT NULL DEFAULT 3, analysis_hash TEXT, related_id TEXT REFERENCES jobs(id),
 change_note TEXT NOT NULL DEFAULT '', first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
 status TEXT NOT NULL DEFAULT '未投递', applied_date TEXT, platform TEXT NOT NULL DEFAULT '',
 favorite INTEGER NOT NULL DEFAULT 0, notes TEXT NOT NULL DEFAULT '', version INTEGER NOT NULL DEFAULT 0,
 user_updated_at TEXT);
CREATE TABLE IF NOT EXISTS identities(key TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES jobs(id));
CREATE TABLE IF NOT EXISTS sources(job_id TEXT NOT NULL REFERENCES jobs(id), url TEXT NOT NULL,
 title TEXT NOT NULL DEFAULT '', first_seen TEXT NOT NULL, last_seen TEXT NOT NULL,
 PRIMARY KEY(job_id,url));
CREATE TABLE IF NOT EXISTS user_history(id INTEGER PRIMARY KEY AUTOINCREMENT,job_id TEXT NOT NULL REFERENCES jobs(id),
 at TEXT NOT NULL, before_json TEXT NOT NULL, after_json TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS runs(id TEXT PRIMARY KEY, execution_date TEXT NOT NULL, trigger TEXT NOT NULL,
 started_at TEXT NOT NULL, finished_at TEXT, status TEXT NOT NULL, stats TEXT NOT NULL DEFAULT '{}',
 errors TEXT NOT NULL DEFAULT '[]', report_path TEXT);
CREATE TABLE IF NOT EXISTS completed_days(execution_date TEXT PRIMARY KEY, run_id TEXT NOT NULL REFERENCES runs(id));
CREATE TABLE IF NOT EXISTS run_jobs(run_id TEXT REFERENCES runs(id),job_id TEXT REFERENCES jobs(id),is_new INTEGER NOT NULL,
 PRIMARY KEY(run_id,job_id));
CREATE TABLE IF NOT EXISTS cache(key TEXT PRIMARY KEY,value TEXT NOT NULL,created_at TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS jobs_status ON jobs(status);
CREATE INDEX IF NOT EXISTS jobs_fingerprint ON jobs(company_key,title,city,batch);
PRAGMA user_version=1;
'''

class Database:
    def __init__(self, path):
        path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
        self.conn = sqlite3.connect(path, timeout=15)
        self.conn.row_factory = sqlite3.Row
        if self.conn.execute('PRAGMA user_version').fetchone()[0]>1:
            self.conn.close();raise RuntimeError('数据库版本较新，拒绝降级写入')
        self.conn.execute('PRAGMA journal_mode=WAL')
        self.conn.execute('PRAGMA busy_timeout=15000')
        self.conn.executescript(SCHEMA)
    def close(self): self.conn.close()
    def get(self, job_id):
        r = self.conn.execute('SELECT * FROM jobs WHERE id=?', (job_id,)).fetchone()
        if not r: raise ValueError('岗位不存在')
        result = dict(r)
        result['sources'] = [dict(x) for x in self.conn.execute('SELECT * FROM sources WHERE job_id=?',(job_id,))]
        result['history'] = [dict(x) for x in self.conn.execute('SELECT * FROM user_history WHERE job_id=? ORDER BY id DESC',(job_id,))]
        return result
    def list(self, query='', status='', favorite=False, limit=200, offset=0):
        conditions, args = [], []
        if query:
            conditions.append('(company LIKE ? OR title LIKE ? OR city LIKE ? OR notes LIKE ?)')
            args += ['%'+query+'%']*4
        if status:
            if status == '已投递及后续':
                conditions.append('(applied_date IS NOT NULL OR status IN ('+','.join('?'*len(APPLIED))+'))');args+=APPLIED
            elif status in STATES: conditions.append('status=?'); args.append(status)
            else: raise ValueError('无效状态筛选')
        if favorite: conditions.append('favorite=1')
        where = ' WHERE '+' AND '.join(conditions) if conditions else ''
        total = self.conn.execute('SELECT count(*) FROM jobs'+where,args).fetchone()[0]
        rows=self.conn.execute('SELECT * FROM jobs'+where+' ORDER BY published_date IS NULL,published_date DESC,company_tier,score DESC,last_seen DESC LIMIT ? OFFSET ?',args+[min(max(int(limit),1),200),max(0,int(offset))]).fetchall()
        return {'items':[dict(r) for r in rows], 'total':total, 'states':STATES}
    def update_user(self, job_id, patch):
        allowed={'status','applied_date','platform','favorite','notes','version'}
        if not patch or set(patch)-allowed: raise ValueError('无效用户字段')
        before=self.get(job_id)
        if 'version' not in patch or patch['version'] != before['version']: raise ValueError('记录已变化，请刷新后保存')
        changes={k:v for k,v in patch.items() if k!='version'}
        if 'status' in changes and changes['status'] not in STATES: raise ValueError('无效岗位状态')
        if 'favorite' in changes:
            if not isinstance(changes['favorite'],bool): raise ValueError('收藏必须是布尔值')
            changes['favorite']=int(changes['favorite'])
        for field in ('notes','platform'):
            if field in changes and (not isinstance(changes[field],str) or len(changes[field])>5000): raise ValueError('备注或平台格式错误')
        if changes.get('applied_date'):
            datetime.strptime(changes['applied_date'],'%Y-%m-%d')
        if changes.get('status')=='已投递' and not changes.get('applied_date') and not before['applied_date']:
            changes['applied_date']=datetime.now(CN).date().isoformat()
        changes['version']=before['version']+1;changes['user_updated_at']=now()
        before_json={k:before[k] for k in ('status','applied_date','platform','favorite','notes','version')}
        with self.conn:
            updated=self.conn.execute('UPDATE jobs SET '+','.join(k+'=?' for k in changes)+' WHERE id=? AND version=?',list(changes.values())+[job_id,before['version']])
            if updated.rowcount!=1: raise ValueError('并发修改，请刷新')
            self.conn.execute('INSERT INTO user_history(job_id,at,before_json,after_json) VALUES(?,?,?,?)',
                (job_id,now(),json.dumps(before_json,ensure_ascii=False),json.dumps(changes,ensure_ascii=False)))
        return self.get(job_id)
    def upsert(self, job, run_id=None):
        j=dict(job);stamp=now();url=canonical_url(j['application_url'])
        j['application_url']=url;ck=company_key(j['company']);batch=j.get('batch') or '未知';city=j.get('city','')
        identity_base='|'.join((ck,norm(j['title']),norm(city),batch))
        keys=['fingerprint:'+identity_base]
        if j.get('official_id'): keys.insert(0,'official:'+'|'.join((ck,j['official_id'],norm(city),batch)))
        # Generic campaign URLs must never merge different positions.
        keys.append('url:'+url+'|'+ck+'|'+norm(j['title'])+'|'+norm(city)+'|'+batch)
        row=None
        for k in keys:
            row=self.conn.execute('SELECT j.* FROM identities i JOIN jobs j ON j.id=i.job_id WHERE i.key=?',(k,)).fetchone()
            if row: break
        related=None;change_note=''
        if row and row['published_date'] and j.get('published_date') and row['published_date']!=j['published_date']:
            distance=(datetime.fromisoformat(j['published_date'])-datetime.fromisoformat(row['published_date'])).days
            old_text=norm(row['description']);new_text=norm(j.get('description',''))
            if distance>=30 and old_text and new_text and old_text!=new_text:
                related=row['id'];change_note='可能重新开放：发布日期与岗位内容变化，需人工确认';row=None
                keys=[k+'|reopen:'+j['published_date'] for k in keys]
                hit=self.conn.execute('SELECT j.* FROM identities i JOIN jobs j ON j.id=i.job_id WHERE i.key=?',(keys[0],)).fetchone()
                if hit:row=hit
        if row is None and related is None:
            related_row=self.conn.execute('SELECT id FROM jobs WHERE company_key=? AND title=? AND city=? AND batch<>? ORDER BY first_seen DESC LIMIT 1',(ck,j['title'],city,batch)).fetchone()
            if related_row: related=related_row['id'];change_note='不同招聘批次，与历史岗位关联；请核对是否重新开放'
        is_new=row is None;job_id=str(uuid.uuid4()) if is_new else row['id']
        fields=['company','title','city','batch','official_id','application_url','published_date','deadline','description','verification','recruitment_status']
        values={k:j.get(k) for k in fields if j.get(k) is not None}
        values['evidence']=json.dumps(j.get('evidence',{}),ensure_ascii=False)
        values['last_seen']=stamp
        with self.conn:
            if is_new:
                values.update(id=job_id,company_key=ck,first_seen=stamp,related_id=related,change_note=change_note,official=int(j.get('official',False)))
                self.conn.execute('INSERT INTO jobs('+','.join(values)+') VALUES('+','.join('?'*len(values))+')',list(values.values()))
            else:
                # Never touch status, favorite, applied_date, notes, platform, user history.
                if row['official'] and not j.get('official'):
                    values.pop('application_url',None)
                elif j.get('official'):values['official']=1
                if row['recruitment_status']!=j.get('recruitment_status') and j.get('recruitment_status') not in (None,'未知'):
                    values['change_note']='招聘页面状态变化：'+str(j.get('recruitment_status'))+'（用户投递状态保持）'
                self.conn.execute('UPDATE jobs SET '+','.join(k+'=?' for k in values)+' WHERE id=?',list(values.values())+[job_id])
            for key in keys:self.conn.execute('INSERT OR IGNORE INTO identities VALUES(?,?)',(key,job_id))
            source=canonical_url(j.get('source_url',url))
            self.conn.execute('INSERT INTO sources VALUES(?,?,?,?,?) ON CONFLICT(job_id,url) DO UPDATE SET last_seen=excluded.last_seen',
                (job_id,source,j.get('source_title',''),stamp,stamp))
            if run_id:self.conn.execute('INSERT INTO run_jobs VALUES(?,?,?) ON CONFLICT(run_id,job_id) DO UPDATE SET is_new=max(is_new,excluded.is_new)',(run_id,job_id,int(is_new)))
        return job_id,is_new
    def cache_get(self,key):
        r=self.conn.execute('SELECT value FROM cache WHERE key=?',(key,)).fetchone()
        return json.loads(r[0]) if r else None
    def cache_set(self,key,value):
        with self.conn:self.conn.execute('INSERT OR REPLACE INTO cache VALUES(?,?,?)',(key,json.dumps(value,ensure_ascii=False),now()))
    def analyze(self,job_id,a,hash_value):
        if not isinstance(a.get('score'),int) or not 0<=a['score']<=100:raise ValueError('模型评分格式错误')
        if a.get('eligible') not in ('是','否','未知') or a.get('rd') not in ('是','否','未知'):raise ValueError('模型资格格式错误')
        with self.conn:self.conn.execute('UPDATE jobs SET score=?,reason=?,eligible=?,rd=?,company_tier=?,analysis_hash=? WHERE id=?',
            (a['score'],str(a.get('reason',''))[:600],a['eligible'],a['rd'],max(1,min(3,int(a.get('company_tier',3)))),hash_value,job_id))
