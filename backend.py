"""One-shot JSON-lines process. No server, no credentials, no persistent worker."""
import json
import sys
from datetime import date
from uuid import UUID
from pathlib import Path,PureWindowsPath
from recruit.database import Database
from recruit.pipeline import run, AlreadyRunning, finish_interrupted

from recruit.runtime import data_root
ROOT=data_root()
def emit(value):print(json.dumps(value,ensure_ascii=False),flush=True)
def bridge(op,args):
    emit({'type':'bridge','op':op,'args':args})
    line=sys.stdin.readline()
    if not line:raise RuntimeError('DSH桥接已断开')
    result=json.loads(line)
    if not result.get('ok'):raise RuntimeError(result.get('error','DSH服务失败'))
    return result['result']
def dispatch(request):
    action=request.get('action')
    if action=='run':return run(ROOT,bridge,request.get('trigger','manual'),day=request.get('execution_date'),recheck=request.get('recheck') is True)
    if action=='fail_run':return finish_interrupted(ROOT,request.get('error_code','BACKEND_PROCESS_FAILED'))
    db=Database(ROOT/'data'/'recruitment.sqlite3')
    try:
        if action=='list':return db.list(**request.get('filters',{}))
        if action=='get':return db.get(request['id'])
        if action=='update':return db.update_user(request['id'],request['patch'])
        if action=='dashboard':
            runs=[dict(r) for r in db.conn.execute('SELECT * FROM runs ORDER BY started_at DESC LIMIT 40')]
            counts={r[0]:r[1] for r in db.conn.execute('SELECT status,count(*) FROM jobs GROUP BY status')}
            return {'runs':runs,'counts':counts,'integrity':db.conn.execute('PRAGMA quick_check').fetchone()[0]}
        if action=='report':
            row=db.conn.execute('SELECT report_path,execution_date FROM runs WHERE id=?',(request['id'],)).fetchone()
            if not row or not row[0]:raise ValueError('本次执行暂无日报')
            path=Path(row[0]).resolve()
            if not path.is_relative_to((ROOT/'reports').resolve()) or not path.is_file():
                # Preserve state when moving a DB to another machine. Never read
                # the old computer's absolute path outside the configured reports.
                filename=PureWindowsPath(row[0]).name if '\\' in row[0] else Path(row[0]).name
                UUID(Path(filename).stem);day=date.fromisoformat(row[1]).isoformat()
                path=(ROOT/'reports'/day/filename).resolve()
                if not path.is_relative_to((ROOT/'reports').resolve()):raise ValueError('无效报告路径')
            return {'report':path.read_text(encoding='utf-8')}
        raise ValueError('不支持的操作')
    finally:db.close()
def main():
    try:
        line=sys.stdin.readline(100000)
        request=json.loads(line)
        emit({'type':'result','ok':True,'result':dispatch(request)})
    except AlreadyRunning as e:emit({'type':'result','ok':False,'error':str(e),'code':'RUNNING'})
    except (ValueError,KeyError,TypeError) as e:emit({'type':'result','ok':False,'error':str(e),'code':'INVALID_REQUEST'})
    except Exception as e:emit({'type':'result','ok':False,'error':'后端失败：'+type(e).__name__,'code':'BACKEND_ERROR'})
if __name__=='__main__':main()
