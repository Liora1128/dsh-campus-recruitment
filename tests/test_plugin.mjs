import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,cpSync,rmSync,readFileSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join,resolve} from 'node:path';
import {spawnSync} from 'node:child_process';
import vm from 'node:vm';
import {RecruitmentService,scheduleExecutionDate,MARKER,ROOT} from '../plugin/service.js';

test('official occurrence determines manual and missed dates without depending on boot time',()=>{
 const make=at=>[{source:{kind:'schedule'},content:[{type:'text',text:MARKER+'\noccurrence_at: '+at}]}];
 assert.equal(scheduleExecutionDate(make('2026-11-08T02:00:00Z')),'2026-11-08');
 assert.equal(scheduleExecutionDate(make('2026-11-07T11:00:00Z')),'2026-11-07');
 assert.equal(scheduleExecutionDate([{source:{kind:'user'},content:[{type:'text',text:MARKER}]}]),null);
 assert.throws(()=>scheduleExecutionDate(make('invalid')),/FORMAT_CHANGED/);
});

test('actual subprocess API persists user actions and exits after each operation',async()=>{
 const root=mkdtempSync(join(tmpdir(),'recruitment-api-'));
 try{
  cpSync(join(ROOT,'backend.py'),join(root,'backend.py'));cpSync(join(ROOT,'recruit'),join(root,'recruit'),{recursive:true});
  const service=new RecruitmentService({},{root,dataRoot:join(root,'user-store')});
  const script="from recruit.database import Database; import json; d=Database('user-store/data/recruitment.sqlite3'); i,n=d.upsert(dict(company='Fixture',title='PLC研发',city='上海',batch='2027届校招',application_url='https://example.org/job/1')); print(i); d.close()";
  const seed=spawnSync(service.python,['-X','utf8','-c',script],{cwd:root,encoding:'utf8',windowsHide:true});assert.equal(seed.status,0,seed.stderr);
  const id=seed.stdout.trim();const list=await service.request({action:'list'});assert.equal(list.total,1);
  const changed=await service.request({action:'update',id,patch:{version:0,status:'已投递',favorite:true,platform:'企业官网',notes:'明确手动操作',applied_date:'2026-11-08'}});
  assert.equal(changed.status,'已投递');assert.equal(service.children.size,0);await service.close();
  const fresh=new RecruitmentService({},{root,dataRoot:join(root,'user-store')});const read=await fresh.request({action:'get',id});assert.equal(read.notes,'明确手动操作');assert.equal(read.history.length,1);assert.equal(read.applied_date,'2026-11-08');
  const filtered=await fresh.request({action:'list',filters:{status:'已投递及后续',favorite:true}});assert.equal(filtered.total,1);
  const migration="from recruit.database import Database; from pathlib import Path; d=Database('user-store/data/recruitment.sqlite3'); i='11111111-1111-4111-8111-111111111111'; p=Path('user-store/reports/2026-11-08')/(i+'.md'); p.parent.mkdir(parents=True,exist_ok=True); p.write_text('migrated report',encoding='utf-8'); d.conn.execute('INSERT INTO runs(id,execution_date,trigger,started_at,status,report_path) VALUES(?,?,?,?,?,?)',(i,'2026-11-08','fixture','2026-11-08T19:00:00+08:00','success','Z:/old-computer/reports/2026-11-08/'+i+'.md')); d.conn.commit();d.close()";
  assert.equal(spawnSync(fresh.python,['-X','utf8','-c',migration],{cwd:root,encoding:'utf8',windowsHide:true}).status,0);
  assert.equal((await fresh.request({action:'report',id:'11111111-1111-4111-8111-111111111111'})).report,'migrated report');
  assert.equal((await fresh.request({action:'dashboard'})).integrity,'ok');assert.equal(fresh.children.size,0);await fresh.close();
 }finally{rmSync(root,{recursive:true,force:true})}
});

test('native UI registers additive sidebar/main slots and builds the initial control tree',()=>{
 // Host bundles React for browsers and does not ship it as a Node module.
 // This test checks registration/control construction; desktop rendering is a separate live check.
 const React={createElement:(type,props,...children)=>({type,props,children}),useState:v=>[v,()=>{}],useCallback:fn=>fn,useEffect:()=>{},Fragment:'fragment'};let entry;
 vm.runInNewContext(readFileSync(join(ROOT,'plugin/client.js'),'utf8'),{window:{__ModuleLoader__:{load:e=>entry=e}},setTimeout,clearTimeout,setInterval,clearInterval,fetch:()=>Promise.reject(Error('SSR does not fetch'))});
 assert.equal(entry.id,'dsh-campus-recruitment');const plugin=entry.factory(n=>{assert.equal(n,'react');return React});const registrations=[];
 plugin.apply({slots:{inject:(_owner,fn)=>fn(),register:(r,c)=>registrations.push({r,c})}});
 assert.equal(registrations[0].r.name,'sidebar.panellist');assert.equal(registrations[0].r.label(),'招聘管理');
 assert.equal(registrations[1].r.name,'main');assert.equal(registrations[1].r.key,'campus-recruitment');
 const tree=JSON.stringify(registrations[1].c());assert.match(tree,/立即运行/);assert.match(tree,/所有状态/);assert.match(tree,/日报与执行记录/);assert.match(tree,/关键词搜索/);
});
