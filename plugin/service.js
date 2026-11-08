import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {fileURLToPath} from 'node:url';
import {dirname,resolve,join} from 'node:path';
import {readFileSync,writeFileSync,mkdirSync} from 'node:fs';
import {resolveSettings} from './settings.js';

export const ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
export const TITLE='校招日报 · 每日19:00';
export const MARKER='[DSH_CAMPUS_RECRUITMENT_V1]';
export const PROMPT=MARKER+' 运行已安装的招聘管理固定流程并展示完整日报。该提示由招聘管理插件识别执行，不修改程序、不自动投递简历。';

function code(error){return /^[A-Z][A-Z0-9_]{2,80}$/.test(error?.code||'')?error.code:'DSH_SERVICE_FAILED'}
export class RecruitmentService {
 constructor(ctx,options={}){
  const {spawnProcess=spawn}=options;this.settings=resolveSettings(options);
  this.ctx=ctx;this.root=this.settings.root;this.dataRoot=this.settings.dataRoot;this.python=this.settings.python;
  if(!this.python)throw Error('PYTHON_NOT_FOUND: set python in config.local.json or CAMPUS_PYTHON');
  this.spawnProcess=spawnProcess;this.running=null;this.children=new Set();this.quotaVerified=false;this.task=null;this.stopping=false;
 }
 async subscriptionSearch(args,signal){
  // Credentials stay inside DSH's managed Host. Never sent to Python, files, logs or UI.
  if(!this.quotaVerified){
   const credential=await this.ctx.credentials.resolve(this.settings.credentialRef);if(!credential)throw Object.assign(Error('MINIMAX_CREDENTIAL_MISSING'),{code:'MINIMAX_CREDENTIAL_MISSING'});
   const response=await fetch(this.settings.quotaOrigin+'/v1/token_plan/remains',{headers:{Authorization:'Bearer '+credential.value},signal:AbortSignal.any([signal,AbortSignal.timeout(15000)])});
   const quota=await response.json();
   if(!response.ok||quota.base_resp?.status_code!==0||!Array.isArray(quota.model_remains))throw Object.assign(Error('SUBSCRIPTION_NOT_VERIFIED'),{code:'SUBSCRIPTION_NOT_VERIFIED'});
   this.quotaVerified=true;
  }
  const directory=join(this.dataRoot,'data');mkdirSync(directory,{recursive:true});const path=join(directory,'search-budget.json');
  const month=new Date().toLocaleDateString('en-CA',{timeZone:'Asia/Shanghai'}).slice(0,7);
  let budget={month,count:0};try{const saved=JSON.parse(readFileSync(path,'utf8'));if(saved.month===month)budget=saved}catch{}
  if(budget.count>=this.settings.monthlySearchLimit)throw Object.assign(Error('LOCAL_MONTHLY_SEARCH_CAP'),{code:'LOCAL_MONTHLY_SEARCH_CAP'});
  budget.count++;writeFileSync(path,JSON.stringify(budget));
  const credential=await this.ctx.credentials.resolve(this.settings.credentialRef);if(!credential)throw Error('MINIMAX_CREDENTIAL_MISSING');
  const response=await fetch(this.settings.apiOrigin+'/v1/coding_plan/search',{
   method:'POST',headers:{Authorization:'Bearer '+credential.value,'Content-Type':'application/json'},body:JSON.stringify({q:String(args.query).slice(0,300)}),
   signal:AbortSignal.any([signal,AbortSignal.timeout(25000)])});
  const result=await response.json();
  if(!response.ok||result.base_resp?.status_code!==0||!Array.isArray(result.organic))throw Object.assign(Error('MINIMAX_SEARCH_UNAVAILABLE'),{code:'MINIMAX_SEARCH_UNAVAILABLE'});
  return {sources:result.organic.slice(0,Math.min(args.max_results||6,8)).map(s=>({url:s.link,title:s.title||'',snippet:s.snippet||'',provider_date:s.date||null}))};
 }
 async bridge(op,args,signal){
  if(op==='search')return this.subscriptionSearch(args,signal);
  if(op!=='llm')throw Error('INVALID_BRIDGE_OPERATION');
  let text='',finish='';
  for await(const chunk of this.ctx.llm.stream({provider:this.settings.provider,model:this.settings.model,reasoningEffort:this.settings.reasoningEffort,
   system:args.system,messages:[{role:'user',content:[{type:'text',text:args.input}]}],maxTokens:Math.min(args.max_tokens||4000,8000),
   signal:AbortSignal.any([signal,AbortSignal.timeout(120000)])})){
   if(chunk.type==='text-delta'){text+=chunk.text;if(text.length>100000)throw Error('MODEL_OUTPUT_LIMIT')}
   if(chunk.type==='finish')finish=chunk.reason.kind;
  }
  if(finish!=='stop')throw Object.assign(Error('MODEL_INCOMPLETE'),{code:'MODEL_INCOMPLETE'});
  return {text};
 }
 request(request,{signal,timeoutMs=request.action==='run'?900000:20000}={}){
  if(this.stopping)return Promise.reject(Error('PLUGIN_STOPPING'));
  return new Promise((resolvePromise,reject)=>{
   const controller=new AbortController();const combined=signal?AbortSignal.any([signal,controller.signal]):controller.signal;
   const child=this.spawnProcess(this.python,['-u',join(this.root,'backend.py')],{cwd:this.root,windowsHide:true,stdio:['pipe','pipe','pipe'],env:{...process.env,PYTHONUTF8:'1',PYTHONDONTWRITEBYTECODE:'1',CAMPUS_DATA_ROOT:this.dataRoot,CAMPUS_CONFIG_FILE:this.settings.configFile,CAMPUS_NODE:this.settings.node,CAMPUS_BROWSER:this.settings.browser}});
   this.children.add(child);let result=null,settled=false;let serial=Promise.resolve();let size=0;
   const finish=(error,value)=>{if(settled)return;settled=true;clearTimeout(deadline);combined.removeEventListener('abort',abort);this.children.delete(child);if(error)reject(error);else resolvePromise(value)};
   const abort=()=>{child.kill();};combined.addEventListener('abort',abort,{once:true});
   const deadline=setTimeout(()=>controller.abort(),timeoutMs);deadline.unref?.();
   const lines=createInterface({input:child.stdout,crlfDelay:Infinity});
   lines.on('line',line=>{
    size+=line.length;if(size>3000000){child.kill();finish(Error('BACKEND_OUTPUT_LIMIT'));return}
    serial=serial.then(async()=>{
     let event;try{event=JSON.parse(line)}catch{throw Error('BACKEND_PROTOCOL_ERROR')}
     if(event.type==='result'){result=event;return}
     if(event.type!=='bridge')throw Error('BACKEND_PROTOCOL_ERROR');
     try{const value=await this.bridge(event.op,event.args,combined);if(!child.stdin.destroyed)child.stdin.write(JSON.stringify({ok:true,result:value})+'\n')}
     catch(e){if(!child.stdin.destroyed)child.stdin.write(JSON.stringify({ok:false,error:code(e)})+'\n')}
    }).catch(e=>{child.kill();finish(e)});
   });
   child.stderr.on('data',()=>{});child.stdin.on('error',()=>{});
   child.on('error',()=>finish(Error('PYTHON_UNAVAILABLE')));
   child.on('close',async(exitCode)=>{await serial;if(combined.aborted)finish(Error('RUN_CANCELLED_OR_TIMEOUT'));else if(exitCode!==0||!result)finish(Error('BACKEND_PROCESS_FAILED'));else if(!result.ok)finish(Object.assign(Error(result.error),{code:result.code}));else finish(null,result.result)});
   if(combined.aborted){abort();return}
   child.stdin.write(JSON.stringify(request)+'\n');
  });
 }
 run(trigger='manual',signal,executionDate){
  if(this.running)return Promise.resolve({status:'running',message:'已有招聘任务执行中，请稍后刷新运行记录。'});
  this.running=this.request({action:'run',trigger,...(executionDate?{execution_date:executionDate}:{})},{signal}).catch(async error=>{
   if(!this.stopping&&error.code!=='RUNNING'){
    const recovered=await this.request({action:'fail_run',error_code:code(error)}).catch(()=>null);
    if(recovered?.report)return recovered;
   }
   throw error;
  }).finally(()=>{this.running=null});return this.running;
 }
 async ensureSchedule(){
  const entries=(await this.ctx.schedule.catalog()).filter(t=>t.title===TITLE||t.prompt?.includes(MARKER));
  if(entries.length>1)throw Error('DUPLICATE_RECRUITMENT_SCHEDULES');
  if(entries.length){
   const t=entries[0];if(t.kind!=='daily'||t.timeZone!=='Asia/Shanghai'||!t.time.startsWith('19:00'))throw Error('RECRUITMENT_SCHEDULE_MISMATCH');
   this.task=t;return t; // Respect a deliberate user pause; never silently resume it.
  }
  this.task=await this.ctx.schedule.create({title:TITLE,prompt:PROMPT,timing:{kind:'daily',daily:{time:'19:00:00',time_zone:'Asia/Shanghai'}},target:{kind:'new',create:{cwd:this.root}}});
  return this.task;
 }
 async state(){
  const data=await this.request({action:'dashboard'});
  const tasks=(await this.ctx.schedule.catalog()).filter(t=>t.prompt?.includes(MARKER));
  return {...data,running:Boolean(this.running),schedule:tasks[0]||null,workerCount:this.children.size,python:this.python,dataRoot:this.dataRoot,graduationYear:this.settings.graduation_year};
 }
 async close(){this.stopping=true;for(const child of this.children)child.kill();await this.running?.catch(()=>{});}
}

export function reportStream(report){
 return (async function*(){
  yield {type:'block-start',index:0,blockType:'text'};
  yield {type:'text-delta',index:0,text:report};
  yield {type:'block-end',index:0,block:{type:'text',text:report}};
  yield {type:'finish',reason:{kind:'stop'}};
 })();
}

export function scheduleExecutionDate(messages){
 for(const message of messages){
  if(message.source?.kind!=='schedule')continue;
  const text=(message.content||[]).filter(b=>b.type==='text').map(b=>b.text).join('\n');
  if(!text.includes(MARKER))continue;
  const match=/^occurrence_at:\s*(\d{4}-\d\d-\d\dT[^\s]+)$/m.exec(text);
  if(!match||!Number.isFinite(Date.parse(match[1])))throw Error('SCHEDULE_OCCURRENCE_FORMAT_CHANGED');
  return new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Shanghai',year:'numeric',month:'2-digit',day:'2-digit'}).format(new Date(match[1]));
 }
 return null;
}
