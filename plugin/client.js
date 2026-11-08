window.__ModuleLoader__.load({id:'dsh-campus-recruitment',factory(require){
 const React=require('react'),h=React.createElement;
 const API='/api/campus-recruitment/';
 const states=['未投递','计划投递','已投递','测评中 / 笔试中','面试中','已录用 / Offer','未通过','不感兴趣','招聘已结束'];
 async function call(action,args={}){
  const response=await fetch(API+action,{method:'POST',headers:{'content-type':'application/json'},body:JSON.stringify(args)});
  let value;try{value=await response.json()}catch{throw Error('招聘插件暂未就绪，请重新加载DSH。')}
  if(!response.ok||!value.ok)throw Error(value.error||'操作失败');return value.result;
 }
 const CSS=`
 .cr-root{height:100%;overflow:auto;padding:24px;box-sizing:border-box;color:var(--dsw-alias-label-primary);background:var(--dsw-alias-bg-base);font:14px/1.6 var(--dsw-font-family,system-ui)}
 .cr-root *{box-sizing:border-box}.cr-header,.cr-toolbar,.cr-row{display:flex;align-items:center;gap:12px;flex-wrap:wrap}.cr-header{justify-content:space-between;margin-bottom:16px}.cr-header h1{font-size:23px;margin:0}.cr-muted{color:var(--dsw-alias-label-secondary);font-size:12px}.cr-root button,.cr-root select,.cr-root input,.cr-root textarea{font:inherit;color:inherit;border:1px solid var(--dsw-alias-border-l2);border-radius:7px;background:var(--dsw-alias-bg-elevated);padding:7px 10px}.cr-root button{cursor:pointer}.cr-root button:disabled{opacity:.5;cursor:wait}.cr-root button:focus-visible,.cr-root input:focus-visible,.cr-root select:focus-visible{outline:2px solid var(--dsw-alias-accent-primary);outline-offset:2px}.cr-root a{color:var(--dsw-alias-accent-primary);text-decoration:underline}.cr-panel{border:1px solid var(--dsw-alias-border-l2);border-radius:10px;padding:16px;margin:12px 0;background:var(--dsw-alias-bg-elevated)}.cr-toolbar{margin:16px 0}.cr-toolbar input{flex:1;min-width:200px}.cr-card-title{font-size:16px;margin:0}.cr-pill{font-size:12px;padding:2px 8px;border:1px solid var(--dsw-alias-border-l2);border-radius:20px}.cr-card-top{display:flex;justify-content:space-between;gap:12px}.cr-card-top>div:first-child{flex:1}.cr-favorite{min-width:40px}.cr-details{margin-top:12px;padding-top:10px;border-top:1px solid var(--dsw-alias-border-l2)}.cr-details label{display:block;margin:10px 0}.cr-details textarea{display:block;width:100%;min-height:75px}.cr-report{white-space:pre-wrap;word-break:break-word;font:13px/1.8 var(--dsw-font-family,system-ui);margin:0}.cr-error{border-left:3px solid currentColor;padding:10px 14px;margin:12px 0}.cr-root [role=tab][aria-selected=true]{font-weight:700;border-color:var(--dsw-alias-accent-primary)}.cr-history{border-left:2px solid var(--dsw-alias-border-l2);padding-left:12px;margin:10px 0}.cr-meta{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:8px;margin:14px 0}.cr-root small{display:block}.cr-inline-error{margin:8px 0}.cr-code{font:11px monospace;overflow-wrap:anywhere}.cr-root h2{font-size:17px;margin:10px 0}
 `;
 function Icon(){return h('svg',{viewBox:'0 0 24 24',width:17,height:17,fill:'none',stroke:'currentColor',strokeWidth:1.7,'aria-hidden':true},h('rect',{x:3,y:6,width:18,height:15,rx:3}),h('path',{d:'M8 6V3h8v3M3 12h18M9 12v4h6v-4'}))}
 function Job({job,onChange}){
  const [detail,setDetail]=React.useState(null),[error,setError]=React.useState(''),[busy,setBusy]=React.useState(false);
  const [notes,setNotes]=React.useState(job.notes),[platform,setPlatform]=React.useState(job.platform),[applied,setApplied]=React.useState(job.applied_date||'');
  async function save(patch){
   setBusy(true);setError('');try{const current=await call('update',{id:job.id,patch:{...patch,version:job.version}});onChange(current);if(detail)setDetail(current);setApplied(current.applied_date||'')}
   catch(e){setError(e.message)}finally{setBusy(false)}
  }
  async function expand(){if(detail){setDetail(null);return}try{setDetail(await call('get',{id:job.id}))}catch(e){setError(e.message)}}
  return h('article',{className:'cr-panel'},h('div',{className:'cr-card-top'},
   h('div',null,h('h2',{className:'cr-card-title'},job.company+' · '+job.title),h('div',{className:'cr-muted'},[job.city||'地点未知',job.batch,'发布日期 '+(job.published_date||'未知')].join(' ｜ '))),
   h('button',{className:'cr-favorite',onClick:()=>save({favorite:!job.favorite}),disabled:busy,'aria-pressed':Boolean(job.favorite),'aria-label':job.favorite?'取消收藏':'收藏岗位'},job.favorite?'★':'☆')),
   h('div',{className:'cr-row',style:{marginTop:12}},h('span',{className:'cr-pill'},job.score===null?'待分析':job.score+' 分'),
   h('label',null,'投递状态 ',h('select',{value:job.status,disabled:busy,onChange:e=>save({status:e.target.value}),'aria-label':'岗位投递状态'},states.map(s=>h('option',{key:s,value:s},s)))),
   h('a',{href:job.application_url,target:'_blank',rel:'noopener noreferrer'},'打开投递/来源页面 ↗'),h('button',{onClick:expand},detail?'收起详情':'备注与历史')),
   h('p',null,job.reason||'尚无有效的模型匹配结果。'),h('small',{className:'cr-muted'},job.verification+'；招聘状态：'+job.recruitment_status+(job.deadline?'；截止：'+job.deadline:'；截止日期未知')),
   job.change_note?h('p',null,job.change_note):null,error?h('div',{role:'alert',className:'cr-inline-error'},error):null,
   detail?h('div',{className:'cr-details'},
    h('label',null,'实际投递日期 ',h('input',{type:'date',value:applied,onChange:e=>setApplied(e.target.value)})),
    h('label',null,'投递平台 ',h('input',{value:platform,onChange:e=>setPlatform(e.target.value),placeholder:'例如：企业官网 / 智联'})),
    h('label',null,'备注 ',h('textarea',{value:notes,onChange:e=>setNotes(e.target.value),maxLength:5000})),
    h('button',{disabled:busy,onClick:()=>save({notes,platform,applied_date:applied||null})},'保存投递信息'),
    h('p',{className:'cr-muted'},'状态和收藏操作立即保存。系统不代投简历；标记“已投递”以你的操作为准。'),
    h('details',null,h('summary',null,'岗位原文与证据'),h('p',{style:{whiteSpace:'pre-wrap'}},detail.description),h('pre',{className:'cr-report'},detail.evidence)),
    h('h3',null,'来源记录'),detail.sources.map(s=>h('div',{key:s.url},h('a',{href:s.url,target:'_blank',rel:'noopener noreferrer'},s.url),h('small',null,'首次发现：'+s.first_seen))),
    h('h3',null,'投递修改历史'),detail.history.length?detail.history.map(x=>h('div',{className:'cr-history',key:x.id},h('small',null,x.at),h('pre',{className:'cr-report'},x.after_json))):h('p',null,'尚无手动修改记录。'),
    h('small',{className:'cr-code'},'岗位ID：'+detail.id)):null);
 }
 function Panel(){
  const [tab,setTab]=React.useState('jobs'),[items,setItems]=React.useState([]),[total,setTotal]=React.useState(0),[offset,setOffset]=React.useState(0);
  const [query,setQuery]=React.useState(''),[status,setStatus]=React.useState(''),[favorite,setFavorite]=React.useState(false),[dashboard,setDashboard]=React.useState(null),[error,setError]=React.useState(''),[report,setReport]=React.useState(''),[busy,setBusy]=React.useState(false);
  const load=React.useCallback(async()=>{
   setError('');try{const [list,state]=await Promise.all([call('list',{filters:{query,status,favorite,limit:40,offset}}),call('state')]);setItems(list.items);setTotal(list.total);setDashboard(state)}catch(e){setError(e.message)}
  },[query,status,favorite,offset]);
  React.useEffect(()=>{const timer=setTimeout(load,250);return()=>clearTimeout(timer)},[load]);
  React.useEffect(()=>{if(!dashboard?.running)return;const timer=setInterval(load,5000);return()=>clearInterval(timer)},[dashboard?.running,load]);
  async function run(){setBusy(true);setError('');try{const result=await call('run');setError(result.code?'DSH：'+result.code:'已交给DSH原生自动化。请在自动化会话查看执行，或稍后刷新记录。');await load()}catch(e){setError(e.message)}finally{setBusy(false)}}
  const changed=current=>setItems(old=>old.map(j=>j.id===current.id?current:j));
  const schedule=dashboard?.schedule;
  return h('main',{className:'cr-root'},h('style',null,CSS),h('header',{className:'cr-header'},h('div',null,h('h1',null,'招聘管理'),h('div',{className:'cr-muted'},String(dashboard?.graduationYear||2027)+' 届 · 研发方向 · SQLite 持久投递记录')),h('div',{className:'cr-row'},h('button',{onClick:load},'刷新'),h('button',{disabled:busy||dashboard?.running,onClick:run},dashboard?.running?'搜集中…':'立即运行'))),
   h('div',{className:'cr-panel'},schedule?h('div',null,'DSH原生自动化：',h('strong',null,schedule.status==='active'?'已启用':'已暂停'),' · 每天 19:00 Asia/Shanghai',h('small',null,'下次执行：'+new Date(schedule.scheduledAt).toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})+'（北京时间）')):h('div',null,'尚未确认自动化任务已建立。'),dashboard?.setupError?h('div',{role:'alert'},dashboard.setupError):null,
   h('small',{className:'cr-muted'},'电脑关机期间不会运行；DSH再次打开后由官方调度器补执行最近一次遗漏。Python仅在任务和操作期间启动。')),
   h('nav',{className:'cr-row',role:'tablist'},[['jobs','岗位列表'],['runs','日报与执行记录']].map(([id,label])=>h('button',{key:id,role:'tab','aria-selected':tab===id,onClick:()=>{setTab(id);setReport('')}},label))),
   error?h('div',{className:'cr-error',role:'status'},error):null,
   tab==='jobs'?h(React.Fragment,null,
    h('div',{className:'cr-toolbar'},h('input',{type:'search',placeholder:'搜索公司、岗位、城市或备注',value:query,onChange:e=>{setQuery(e.target.value);setOffset(0)},'aria-label':'关键词搜索'}),
    h('select',{value:status,onChange:e=>{setStatus(e.target.value);setOffset(0)},'aria-label':'按状态筛选'},h('option',{value:''},'所有状态'),h('option',{value:'已投递及后续'},'已投递及后续'),states.map(s=>h('option',{key:s,value:s},s))),
    h('label',null,h('input',{type:'checkbox',checked:favorite,onChange:e=>{setFavorite(e.target.checked);setOffset(0)}}),' 仅收藏')),
    h('div',{className:'cr-muted'},`共 ${total} 个岗位 · 状态与备注保留在独立数据库中`),
    items.length?items.map(j=>h(Job,{key:j.id,job:j,onChange:changed})):h('div',{className:'cr-panel'},'当前条件下暂无岗位。完成搜集后可刷新查看；搜索失败或资料不足时不会编造岗位。'),
    h('div',{className:'cr-row'},h('button',{disabled:offset===0,onClick:()=>setOffset(Math.max(0,offset-40))},'上一页'),h('button',{disabled:offset+40>=total,onClick:()=>setOffset(offset+40)},'下一页'))):
    h(React.Fragment,null,report?h('article',{className:'cr-panel'},h('h2',null,'完整 Markdown 日报'),h('pre',{className:'cr-report'},report)):null,
     ...(dashboard?.runs||[]).map(r=>h('article',{key:r.id,className:'cr-panel'},h('div',{className:'cr-row'},h('strong',null,r.execution_date),h('span',{className:'cr-pill'},({success:'完成',partial:'部分失败',skipped:'同日已完成，跳过',running:'执行中',interrupted:'上次中断'})[r.status]||r.status),h('button',{disabled:!r.report_path,onClick:async()=>{try{setReport((await call('report',{id:r.id})).report)}catch(e){setError(e.message)}}},'查看日报')),
      h('small',null,'开始 '+r.started_at+' · 结束 '+(r.finished_at||'尚未结束')),h('small',{className:'cr-code'},'执行ID '+r.id),r.errors!=='[]'?h('pre',{className:'cr-report'},r.errors):null)))
  );
 }
 return {inject:['slots'],apply(ctx){
  ctx.slots.inject('sidebar.panellist',()=>ctx.slots.register({name:'sidebar.panellist',id:'campus-recruitment',order:5,label:()=> '招聘管理'},Icon));
  ctx.slots.inject('main',()=>ctx.slots.register({name:'main',key:'campus-recruitment'},Panel));
 }};
}});
