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

def generate(db,run_id,stats,errors,root):
    run=db.conn.execute('SELECT * FROM runs WHERE id=?',(run_id,)).fetchone()
    new=[dict(r) for r in db.conn.execute('SELECT j.* FROM jobs j JOIN run_jobs r ON r.job_id=j.id WHERE r.run_id=? AND r.is_new=1 ORDER BY published_date IS NULL,published_date DESC,company_tier,score DESC',(run_id,))]
    recent_start=(date.fromisoformat(run['execution_date'])-timedelta(days=7)).isoformat()
    good=[j for j in new if recommended(j) and j['published_date'] and recent_start<=j['published_date']<=run['execution_date']];stats['worthy_today']=len(good)
    stats['ai_passed']=sum(j['eligible']=='是' and j['rd']=='是' and (j['score'] or 0)>=65 for j in new)
    applied=db.conn.execute('SELECT count(*) FROM jobs WHERE applied_date IS NOT NULL OR status IN ('+','.join('?'*len(APPLIED))+')',APPLIED).fetchone()[0]
    stats['historical_applied']=applied
    focus=[dict(r) for r in db.conn.execute("SELECT * FROM jobs WHERE (favorite=1 OR status='计划投递' OR change_note<>'' OR (deadline IS NOT NULL AND deadline BETWEEN ? AND date(?,'+7 day'))) AND status NOT IN ('不感兴趣','未通过') ORDER BY deadline IS NULL,deadline,score DESC LIMIT 30",(run['execution_date'],run['execution_date']))]
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
    content=re.sub(r'\n{3,}','\n\n','\n\n'.join(lines))+'\n'
    directory=Path(root)/'reports'/run['execution_date'];directory.mkdir(parents=True,exist_ok=True)
    path=directory/(run_id+'.md');tmp=path.with_suffix('.tmp');tmp.write_text(content,encoding='utf-8');tmp.replace(path)
    # Stable daily entry references the last actual attempt, preserving every run's immutable report.
    latest=directory/'latest.md';tmp=latest.with_suffix('.tmp');tmp.write_text(content,encoding='utf-8');tmp.replace(latest)
    return str(path),content
