import {RecruitmentService,MARKER,reportStream,scheduleExecutionDate} from './service.js';
export const inject=['webServer','llm','credentials','schedule','tools'];
export function apply(ctx,config={}){
 mount(ctx,new RecruitmentService(ctx,config),config);
}
export function mount(ctx,service,config={}){
 let setupError='';
 const prepared=new Map();
 // Both are official lifecycle seams. Only this plugin's native Schedule inputs are intercepted.
 ctx.on('agent/pre-step',async(payload,next)=>{
  const decision=await next();
  if(decision.kind==='enter'){
   const day=scheduleExecutionDate(decision.messages);
   if(day)prepared.set(payload.agent.session.id,day);
  }
  return decision;
 });
 ctx.on('llm/stream',(options,next)=>{
  if(options.purpose||!options.sessionId||!prepared.has(options.sessionId))return next();
  const day=prepared.get(options.sessionId);prepared.delete(options.sessionId);
  return (async function*(){
   let report;try{const result=await service.run('schedule',options.signal,day);report=result.report||result.message||'任务已结束。'}catch(e){report='招聘搜集失败：'+e.message+'\n请在左侧招聘管理查看运行记录。'}
   yield* reportStream(report);
  })();
 });
 async function body(req){let value='';for await(const chunk of req){value+=chunk;if(value.length>24000)throw Error('请求过大')}return JSON.parse(value||'{}')}
 const reply=(res,status,result)=>{res.writeHead(status,{'content-type':'application/json; charset=utf-8','cache-control':'no-store'});res.end(JSON.stringify(result));};
 const actions=['state','list','get','update','report','run'];
 for(const action of actions)ctx.effect(()=>ctx.webServer.register({kind:'exact',path:'/api/campus-recruitment/'+action,handler:async(req,res)=>{
  if(req.method!=='POST'){reply(res,405,{ok:false,error:'仅支持POST'});return}
  // Same-origin JSON callers only; no permissive CORS or loopback bypass routes.
  if(!String(req.headers['content-type']||'').startsWith('application/json')){reply(res,415,{ok:false,error:'需要JSON请求'});return}
  const origin=req.headers.origin,host=req.headers.host;
  if(origin&&origin!=='null'&&new URL(origin).host!==host){reply(res,403,{ok:false,error:'拒绝跨域请求'});return}
  try{
   const request=await body(req);let result;
   if(action==='state')result={...await service.state(),setupError};
   else if(action==='run'){
    // Native run-now delivers the same managed task and records a DSH execution.
    const task=service.task||await service.ensureSchedule();result=await ctx.schedule.run({id:task.id});
   }else result=await service.request({...request,action});
   reply(res,200,{ok:true,result});
  }catch(e){reply(res,400,{ok:false,error:e.message})}
 }}),'campus-recruitment route '+action);
 // Read-only tool makes the same persisted state visible in ordinary DSH conversations.
 ctx.tools.register({name:'recruitment_view',description:'读取招聘管理的岗位、投递状态和运行记录。修改投递状态请使用左侧招聘管理的明确保存操作。',
  parameters:{type:'object',properties:{query:{type:'string'},status:{type:'string'}},additionalProperties:false},output:{schema:{type:'object'},render:(_args,value)=>[{type:'text',text:JSON.stringify(value)}]},
  execute:async(args)=>service.request({action:'list',filters:{query:args.query||'',status:args.status||''}})});
 ctx.effect(()=>()=>service.close(),'campus-recruitment subprocess lifetime');
 // Do not create a second timer: only DSH's durable schedule owns recurring execution.
 if(config.installSchedule!==false)service.ensureSchedule().catch(e=>{setupError=e.message});
}
