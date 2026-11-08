// Short-lived, unauthenticated Chromium renderer using the official CDP pipe.
// No stealth patches, saved browser profile, captcha solving or login actions.
import {spawn} from 'node:child_process';
import {createInterface} from 'node:readline';
import {mkdtempSync,mkdirSync,rmSync} from 'node:fs';
import {resolve,join} from 'node:path';
import {StringDecoder} from 'node:string_decoder';

const emit=value=>process.stdout.write(JSON.stringify(value)+'\n');
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let browser,profile,base,closing=false,finished=false,sequence=0,buffer='',sessionId;
const calls=new Map(),admissions=new Map();
const decoder=new StringDecoder('utf8');
let pageError='',mainStatus=0,lastActivity=Date.now(),blockedRequests=0;
function send(method,params={},session=sessionId){
 return new Promise((resolveCall,reject)=>{
  const id=++sequence;const timer=setTimeout(()=>{calls.delete(id);reject(Error('CDP_TIMEOUT'))},method==='Page.navigate'?35000:7000);
  calls.set(id,{resolve:resolveCall,reject,timer});
  browser.stdio[3].write(JSON.stringify({id,method,params,...(session?{sessionId:session}:{})})+'\0');
 });
}
async function close(){
 if(closing)return;closing=true;
 for(const call of calls.values()){clearTimeout(call.timer);call.reject(Error('RENDER_CLOSED'))}calls.clear();
 if(browser&&browser.exitCode===null){
  try{browser.stdio[3].write(JSON.stringify({id:++sequence,method:'Browser.close'})+'\0')}catch{}
  await Promise.race([new Promise(r=>browser.once('exit',r)),sleep(1500)]);
  if(browser.exitCode===null)browser.kill();
 }
 // Delete only the new temporary profile created by this process, inside its approved base.
 if(profile&&base&&resolve(profile).startsWith(resolve(base)+'\\')){
  for(let attempt=0;attempt<3;attempt++){try{rmSync(profile,{recursive:true,force:true});break}catch{await sleep(200)}}
 }
}
async function finish(value){if(finished)return;finished=true;emit(value);await close();process.exit(0)}
function failure(error){void finish({type:'result',ok:false,error:error?.message||String(error)})}
async function event(message){
 if(message.method==='Fetch.requestPaused'){
  const p=message.params;lastActivity=Date.now();
  if(['Image','Media','Font','WebSocket'].includes(p.resourceType)||!/^(https?:)/i.test(p.request.url)){
   blockedRequests++;await send('Fetch.failRequest',{requestId:p.requestId,errorReason:'BlockedByClient'});return;
  }
  const id=p.requestId;admissions.set(id,p);emit({type:'authorize',id,url:p.request.url,method:p.request.method,resource_type:p.resourceType});
 }
 if(message.method==='Fetch.authRequired'){
  pageError='LOGIN_REQUIRED';await send('Fetch.continueWithAuth',{requestId:message.params.requestId,authChallengeResponse:{response:'CancelAuth'}});
 }
 if(message.method==='Network.responseReceived'){
  lastActivity=Date.now();const p=message.params;
  if(p.type==='Document'&&p.response.url.startsWith('http')){
   mainStatus=p.response.status;
   if([401,403,407,412,429].includes(mainStatus)){pageError='HTTP_ACCESS_RESTRICTED_'+mainStatus;void send('Page.stopLoading').catch(()=>{})}
  }
 }
 if(message.method==='Page.javascriptDialogOpening'){
  pageError='INTERACTIVE_DIALOG';await send('Page.handleJavaScriptDialog',{accept:false});
 }
}
const expression=`(() => ({url:location.href,title:document.title,text:(document.body?.innerText||'').slice(0,100000),
 links:Array.from(document.querySelectorAll('a[href]')).slice(0,200).map(a=>a.href),
 jsonld:Array.from(document.querySelectorAll('script[type="application/ld+json"]')).slice(0,12).map(s=>{try{return JSON.parse(s.textContent)}catch{return null}}).filter(Boolean)}))()`;
async function start(config){
 base=resolve(config.profile_base);mkdirSync(base,{recursive:true});profile=mkdtempSync(join(base,'render-'));
 browser=spawn(config.browser,['--headless=new','--remote-debugging-pipe','--user-data-dir='+profile,'--no-first-run','--no-default-browser-check','--disable-extensions','--disable-sync','--disable-background-networking','--disable-component-update','about:blank'],
  {windowsHide:true,stdio:['ignore','ignore','ignore','pipe','pipe']});
 browser.once('error',()=>failure(Error('BROWSER_UNAVAILABLE')));
 browser.stdio[4].on('data',data=>{
  buffer+=decoder.write(data);if(buffer.length>4000000){failure(Error('CDP_OUTPUT_LIMIT'));return}
  let at;while((at=buffer.indexOf('\0'))>=0){const line=buffer.slice(0,at);buffer=buffer.slice(at+1);if(!line)continue;
   let message;try{message=JSON.parse(line)}catch{continue}
   if(message.id&&calls.has(message.id)){const call=calls.get(message.id);calls.delete(message.id);clearTimeout(call.timer);if(message.error)call.reject(Error('CDP_'+message.error.code));else call.resolve(message.result||{})}
   else void event(message).catch(()=>{});
  }
 });
 browser.once('exit',()=>{if(!finished)failure(Error('BROWSER_EXITED'))});
 await send('Browser.getVersion',{},null);
 await send('Browser.setDownloadBehavior',{behavior:'deny'},null);
 const target=await send('Target.createTarget',{url:'about:blank'},null);
 const session=await send('Target.attachToTarget',{targetId:target.targetId,flatten:true},null);sessionId=session.sessionId;
 await send('Page.enable');await send('Runtime.enable');await send('Network.enable');
 await send('Network.setBypassServiceWorker',{bypass:true});
 await send('Fetch.enable',{patterns:[{urlPattern:'*',requestStage:'Request'}],handleAuthRequests:true});
 const nav=await send('Page.navigate',{url:config.url});if(nav.errorText)throw Error('NAVIGATION_FAILED');
 let last='',stable=0,latest=null;const begun=Date.now();
 while(Date.now()-begun<26000){
  if(pageError)throw Error(pageError);
  await sleep(650);
  const result=await send('Runtime.evaluate',{expression,returnByValue:true});latest=result.result?.value;
  const text=latest?.text||'';
  if(/人机验证|安全验证|访问过于频繁|请完成验证|just a moment|access denied|登录后.{0,8}(?:查看|浏览)(?!联系|电话|手机|邮箱)|扫码登录后|请先登录后.{0,4}查看/i.test(text.slice(0,6000)))throw Error('CAPTCHA_OR_LOGIN_REQUIRED');
  if(text===last)stable++;else stable=0;last=text;
  if(Date.now()-begun>3000&&text.length>=120&&/岗位职责|任职要求|招聘简章|岗位要求|职位描述|招聘详情|需求专业|招聘人数|职位要求|职位信息|需求人数/.test(text)&&stable>=2&&Date.now()-lastActivity>700)break;
 }
 if(!latest||latest.text.length<120)throw Error('DYNAMIC_CONTENT_UNAVAILABLE');
 await finish({type:'result',ok:true,page:{...latest,method:'browser',http_status:mainStatus,blocked_resources:blockedRequests}});
}
const input=createInterface({input:process.stdin,crlfDelay:Infinity});let started=false;
input.on('line',line=>{
 let value;try{value=JSON.parse(line)}catch{failure(Error('INVALID_RENDER_PROTOCOL'));return}
 if(!started){started=true;void start(value).catch(failure);return}
 const p=admissions.get(value.id);if(!p)return;admissions.delete(value.id);
 if(!value.allow){blockedRequests++;if(p.resourceType==='Document')pageError=value.reason||'DOCUMENT_NOT_ALLOWED'}
 void send(value.allow?'Fetch.continueRequest':'Fetch.failRequest',value.allow?{requestId:value.id}:{requestId:value.id,errorReason:'BlockedByClient'}).catch(()=>{});
});
input.on('close',()=>{if(!finished)failure(Error('RENDER_INPUT_CLOSED'))});
process.on('SIGTERM',()=>failure(Error('RENDER_CANCELLED')));
setTimeout(()=>failure(Error('RENDER_TIME_LIMIT')),48000).unref();
