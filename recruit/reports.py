from datetime import datetime, date, timedelta
from pathlib import Path
import json
import re
from .database import APPLIED, now
from .runtime import settings

def cell(value): return str(value if value is not None else '未知').replace('|','\\|').replace('\n',' ')
def recommended(j):
    return (j['status'] in ('未投递','计划投递') and not j['applied_date'] and j['eligible']=='是'
        and j['rd']=='是' and (j['score'] or 0)>=65 and j['recruitment_status']!='已结束'
        and not j['related_id'])
def table(rows):
    lines=['| 公司名称 | 岗位名称 | 城市 | 发布日期 | 匹配度 | 岗位状态 | 投递链接 |',
           '|---|---|---|---|---|---|---|']
    for j in rows:
        lines.append('| '+' | '.join(cell(j[k]) for k in ('company','title','city','published_date','score','status'))+' | [打开](<'+j['application_url']+'>) |')
    return '\n'.join(lines)


def _save_report(root,run,content):
    content=re.sub(r'\n{3,}','\n\n',content)+'\n'
    directory=Path(root)/'reports'/run['execution_date'];directory.mkdir(parents=True,exist_ok=True)
    path=directory/(run['id']+'.md');tmp=path.with_suffix('.tmp');tmp.write_text(content,encoding='utf-8');tmp.replace(path)
    latest=directory/'latest.md';tmp=latest.with_suffix('.tmp');tmp.write_text(content,encoding='utf-8');tmp.replace(latest)
    return str(path),content

def skipped_report(db,run,stats,root,year=2027):
    total=db.conn.execute('SELECT count(*) FROM jobs').fetchone()[0]
    applied=db.conn.execute('SELECT count(*) FROM jobs WHERE applied_date IS NOT NULL OR status IN ('+','.join('?'*len(APPLIED))+')',APPLIED).fetchone()[0]
    stats['historical_applied']=applied
    stats['collection_performed']=False
    previous=db.conn.execute("SELECT * FROM runs WHERE execution_date=? AND status IN ('success','partial') AND id<>? ORDER BY started_at DESC LIMIT 1",(run['execution_date'],run['id'])).fetchone()
    lines=[f"# {run['execution_date']} · {year} 届校招执行记录",
           f"执行编号：`{run['id']}`  \n北京时间：{run['started_at']}  \n执行状态：**已跳过（同日防重）**",
           '该执行日已经处理完成。本次未进行联网搜索、岗位提取或 AI 分析，也没有重新推荐岗位。**这不表示搜索后没有新岗位，而是本次没有搜索。**',
           '## 当前数据库概况',f'已保存 **{total}** 条岗位记录；已投递及后续流程共 **{applied}** 条。请在 DSH 左侧“招聘管理”查看、筛选并修改状态。']
    if previous:
        old=json.loads(previous['stats']);state='完成' if previous['status']=='success' else '部分来源或处理阶段失败，已保留数据'
        lines+=['## 该执行日最近一次实际采集',f"执行编号：`{previous['id']}`  \n开始时间：{previous['started_at']}  \n执行结果：{state}",
                f"该次发现来源 {old.get('found',0)} 个，新增岗位 {old.get('verified_new',0)} 条，AI筛选通过 {old.get('ai_passed',0)} 条；上述数据属于该次采集，并非本次跳过执行的搜索结果。",
                '完整岗位、排除原因和来源异常，请在“招聘管理 → 日报与执行记录”选择上述执行编号查看。']
    lines+=['## 本次执行说明','联网搜索、信息提取、AI匹配：**未执行**。原有岗位、投递记录和备注保持；日常任务仍由 DSH 原生调度器管理。']
    return _save_report(root,run,'\n\n'.join(lines))

def generate(db,run_id,stats,errors,root,outcome=None):
    run=db.conn.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    if outcome=='skipped' or run['status']=='skipped':
        return skipped_report(db,run,stats,root,year=settings().get('graduation_year',2027))
    new=[dict(r) for r in db.conn.execute('SELECT j.* FROM jobs j JOIN run_jobs r ON r.job_id=j.id WHERE r.run_id=? AND r.is_new=1 ORDER BY published_date IS NULL,published_date DESC,company_tier,score DESC',(run_id,))]
    recent_start=(date.fromisoformat(run['execution_date'])-timedelta(days=7)).isoformat()
    good=[j for j in new if recommended(j) and j['published_date'] and recent_start<=j['published_date']<=run['execution_date']];stats['worthy_today']=len(good)
    stats['ai_passed']=sum(j['eligible']=='是' and j['rd']=='是' and (j['score'] or 0)>=65 for j in new)
    applied=db.conn.execute('SELECT count(*) FROM jobs WHERE applied_date IS NOT NULL OR status IN ('+','.join('?'*len(APPLIED))+')',APPLIED).fetchone()[0]
    stats['historical_applied']=applied
    focus=[dict(r) for r in db.conn.execute("SELECT * FROM jobs WHERE (favorite=1 OR status='计划投递' OR change_note<>'' OR (deadline IS NOT NULL AND deadline BETWEEN ? AND date(?,'+7 day'))) AND status NOT IN ('不感兴趣','未通过') ORDER BY deadline IS NULL,deadline,score DESC LIMIT 30",(run['execution_date'],run['execution_date']))]
    focus=[j for j in focus if j['eligible']!='否' or j['favorite'] or j['status']=='计划投递' or j['applied_date'] or j['status'] in APPLIED]
    lines=[f"# {run['execution_date']} · {settings().get('graduation_year',2027)} 届校招日报",f"\n执行编号：`{run_id}`  \n北京时间：{run['started_at']}  \n执行状态：{'部分失败，保留已获得的数据' if errors else '完成'}",
        '\n在 DSH 左侧打开 **招聘管理** 可修改投递状态、收藏、备注并查看历史。',
        '\n## 今日新增岗位',table(good[:15]) if good else '今日暂无符合条件的新岗位。']
    if len(good)>15:lines.append(f'另有 {len(good)-15} 个符合条件岗位可在招聘管理中查看。')
    lines+=['\n## 今日重点推荐']
    top=sorted(good,key=lambda j:(j['company_tier'],-(j['score'] or 0)))[:3]
    lines += [f"- **{cell(j['company'])} · {cell(j['title'])}**：{cell(j['reason'])}（{cell(j['verification'])}）" for j in top] or ['暂无已核实且符合条件的推荐，不用历史岗位凑数。']
    lines+=['\n## 已投递岗位',f'历史已投递及进入后续流程的岗位共 **{applied}** 个；请在招聘管理选择“已投递及后续”查看进展。',
            '\n## 需要关注的岗位',table(focus) if focus else '暂无收藏、计划投递、已知近期截止或招聘状态变化的岗位。']
    good_ids={j['id'] for j in good}
    pending=[j for j in new if j['id'] not in good_ids]
    if pending:
        lines+=['\n## 新发现但未进入推荐',f'共 {len(pending)} 个；资格、日期、研发职责或历史批次存在限制，保留在管理界面供人工核对。',table(pending[:15])]
        for j in pending[:15]:
            reasons=[]
            if not j['published_date']:reasons.append('未核实发布日期')
            elif not recent_start<=j['published_date']<=run['execution_date']:reasons.append('发布日期不在近7天内')
            if j['eligible']!='是':reasons.append('2027届硕士资格：'+j['eligible'])
            if j['rd']!='是':reasons.append('研发职责：'+j['rd'])
            if j['related_id']:reasons.append('与历史批次关联，需人工确认')
            if (j['score'] or 0)<65:reasons.append('匹配度未达到65分')
            if j['applied_date'] or j['status'] not in ('未投递','计划投递'):reasons.append('用户状态排除')
            if j['recruitment_status']=='已结束':reasons.append('招聘已结束')
            lines.append(f"- {cell(j['company'])} · {cell(j['title'])}：{'；'.join(reasons)}。")
    labels={'found':'本次搜索发现页面数','verified_new':'经页面核实的新岗位数','duplicates':'重复岗位数','ai_passed':'AI筛选通过数','historical_applied':'历史已投递岗位数','worthy_today':'今日值得投递数'}
    lines+=['\n## 数据统计']+[f'- {label}：{stats.get(k,0)}' for k,label in labels.items()]
    lines+=['\n说明：未知发布日期保持“未知”，检索时间不作为发布日期；检索时间条件只是提示，最终以招聘正文为准。未确认的官方入口、资格及截止日期不会补造。']
    if errors:lines+=['\n## 本次异常']+['- '+cell(e) for e in errors]
    return _save_report(root,run,'\n\n'.join(lines))
