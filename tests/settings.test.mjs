import test from 'node:test';
import assert from 'node:assert/strict';
import {mkdtempSync,writeFileSync,rmSync} from 'node:fs';
import {tmpdir} from 'node:os';
import {join} from 'node:path';
import {resolveSettings} from '../plugin/settings.js';
test('configurable data paths support Unicode/spaces and do not need the author machine',()=>{
 const root=mkdtempSync(join(tmpdir(),'campus-settings-'));
 try{
  writeFileSync(join(root,'config.local.json'),'\uFEFF'+JSON.stringify({dataRoot:'用户 数据',graduation_year:2028,region:'global',profile:'My own background'}));
  const c=resolveSettings({root},{PATH:'',CAMPUS_PYTHON:process.execPath});
  assert.equal(c.dataRoot,join(root,'用户 数据'));assert.equal(c.graduation_year,2028);assert.equal(c.apiOrigin,'https://api.minimax.io');
  assert.equal(c.python,process.execPath);
  writeFileSync(join(root,'config.local.json'),JSON.stringify({apiKey:'do-not-store-secrets-here'}));
  assert.throws(()=>resolveSettings({root},{PATH:''}),/UNKNOWN_CONFIG_FIELD/);
 }finally{rmSync(root,{recursive:true,force:true})}
});
