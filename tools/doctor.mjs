import {spawnSync} from 'node:child_process';
import {resolveSettings} from '../plugin/settings.js';
try{
 const c=resolveSettings();if(!c.python)throw Error('No Python found. Set python in config.local.json or CAMPUS_PYTHON.');
 const probe=spawnSync(c.python,['-X','utf8','-c','import sys,sqlite3,json;print(json.dumps({"version":list(sys.version_info[:3]),"sqlite":sqlite3.sqlite_version}))'],{windowsHide:true,encoding:'utf8',timeout:10000});
 if(probe.status!==0)throw Error('Python could not start');const p=JSON.parse(probe.stdout);
 if(p.version[0]!==3||p.version[1]<10)throw Error('Python 3.10+ is required');
 console.log(JSON.stringify({ok:true,python:c.python,pythonVersion:p.version.join('.'),sqlite:p.sqlite,node:c.node,browser:c.browser||'not found: static collection only',dataRoot:c.dataRoot,configFile:c.configFile,model:c.provider+'/'+c.model,
  note:'Local checks only. DSH credentials, subscription quota and live scheduling are verified inside DSH.'},null,2));
}catch(error){console.error(error.message);process.exitCode=1}
