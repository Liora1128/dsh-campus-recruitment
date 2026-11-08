"""Optional short-lived public-page rendering. No accounts or browser cookies reused."""
import json
import os
import subprocess
import threading
from pathlib import Path

from .runtime import render_executables

def render(url,authorize,root):
    node,browser=render_executables()
    if not browser or not node:raise ValueError('DYNAMIC_BROWSER_UNAVAILABLE：未找到独立渲染所需的现有浏览器或DSH Node')
    process=subprocess.Popen([str(node),str(Path(__file__).with_name('render.mjs'))],cwd=root,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,
        text=True,encoding='utf-8',creationflags=getattr(subprocess,'CREATE_NO_WINDOW',0))
    timer=threading.Timer(58,process.kill);timer.daemon=True;timer.start()
    result=None
    try:
        process.stdin.write(json.dumps({'url':url,'browser':str(browser),'profile_base':str(Path(root)/'data/browser-sessions')})+'\n');process.stdin.flush()
        for line in process.stdout:
            if len(line)>1500000:raise ValueError('DYNAMIC_OUTPUT_LIMIT')
            event=json.loads(line)
            if event.get('type')=='authorize':
                allow=False;reason='PUBLIC_ACCESS_NOT_ALLOWED'
                try:
                    if event.get('method') not in ('GET','POST','HEAD','OPTIONS'):raise ValueError('HTTP_METHOD_NOT_ALLOWED')
                    authorize(event['url'],event.get('resource_type',''));allow=True
                except Exception as e:reason=str(e)[:160]
                try:
                    process.stdin.write(json.dumps({'id':event['id'],'allow':allow,'reason':reason})+'\n');process.stdin.flush()
                except (OSError,BrokenPipeError):
                    # The bounded renderer may have already returned its terminal
                    # failure while authorization events were still buffered.
                    # Drain stdout so that original reason is preserved.
                    continue
            elif event.get('type')=='result':result=event;break
        if not result:raise ValueError('DYNAMIC_PROCESS_FAILED：动态渲染进程未返回结果')
        if not result.get('ok'):raise ValueError(result.get('error','DYNAMIC_CONTENT_UNAVAILABLE'))
        return result['page']
    finally:
        try:process.stdin.close()
        except (OSError,ValueError):pass
        try:process.wait(timeout=5)
        except subprocess.TimeoutExpired:process.kill();process.wait(timeout=3)
        timer.cancel();process.stdout.close()
