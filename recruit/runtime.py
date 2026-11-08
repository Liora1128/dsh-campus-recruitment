"""Portable settings; never loads credentials or creates data at import time."""
import json
import os
import shutil
from pathlib import Path
CODE_ROOT=Path(__file__).resolve().parents[1]
DEFAULT_PROFILE='示例求职背景：2027届自动化相关专业毕业生，关注电气控制、PLC、工业软件与嵌入式研发。请配置成你自己的学历、技能和偏好。'
def settings():
    path=Path(os.environ.get('CAMPUS_CONFIG_FILE',str(CODE_ROOT/'config.local.json')))
    value=json.loads(path.read_text(encoding='utf-8-sig')) if path.is_file() else {}
    if not isinstance(value,dict):raise ValueError('配置必须是JSON对象')
    return value
def data_root():
    value=os.environ.get('CAMPUS_DATA_ROOT') or settings().get('dataRoot') or str(Path.home()/'.dsh-campus-recruitment')
    path=Path(value).expanduser()
    return (CODE_ROOT/path).resolve() if not path.is_absolute() else path.resolve()
def render_executables():
    c=settings();home=Path(os.environ.get('DSH_HOME',str(Path.home()/'.dsh')))
    def choose(explicit,candidates,names):
        if explicit:
            p=Path(explicit).expanduser();p=p if p.is_absolute() else CODE_ROOT/p
            if not p.is_file():raise ValueError('配置的可执行程序不存在')
            return str(p)
        for p in candidates:
            if p.is_file():return str(p)
        return next((p for n in names if (p:=shutil.which(n))),None)
    node=choose(os.environ.get('CAMPUS_NODE') or c.get('node'),[home/'dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node.exe',home/'dsh-runtimes/dsh-primary-runtime/dependencies/node/node.exe'],['node'])
    browser=choose(os.environ.get('CAMPUS_BROWSER') or c.get('browser'),[Path(os.environ.get('ProgramFiles(x86)','C:/Program Files (x86)'))/'Microsoft/Edge/Application/msedge.exe',Path(os.environ.get('ProgramFiles','C:/Program Files'))/'Google/Chrome/Application/chrome.exe',Path(os.environ.get('LOCALAPPDATA',str(Path.home()/'AppData/Local')))/'Google/Chrome/Application/chrome.exe'],['msedge','chrome','chromium'])
    return node,browser
