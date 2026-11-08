import {existsSync,readFileSync,statSync} from 'node:fs';
import {homedir} from 'node:os';
import {dirname,join,resolve,isAbsolute,basename} from 'node:path';
import {fileURLToPath} from 'node:url';
export const CODE_ROOT=resolve(dirname(fileURLToPath(import.meta.url)),'..');
const allowed=new Set(['dataRoot','python','node','browser','provider','model','reasoningEffort','credentialRef','region','monthlySearchLimit','graduation_year','profile','keywords','official_domains']);
const file=p=>{try{return Boolean(p)&&statSync(p).isFile()}catch{return false}};
function onPath(names,env){
 for(const folder of (env.PATH||env.Path||'').split(process.platform==='win32'?';':':')){
  if(!folder||folder.toLowerCase().includes('windowsapps'))continue;
  for(const name of names){const path=join(folder,name);if(file(path))return path}
 }
 return '';
}
function executable(explicit,candidates,names,env,root){
 if(explicit){const p=isAbsolute(explicit)?explicit:resolve(root,explicit);if(!file(p))throw Error('EXECUTABLE_NOT_FOUND: '+explicit);return p}
 return candidates.find(file)||onPath(names,env)||'';
}
export function resolveSettings(overrides={},env=process.env){
 const root=resolve(overrides.root||CODE_ROOT),configFile=resolve(env.CAMPUS_CONFIG_FILE||join(root,'config.local.json'));
 const local=existsSync(configFile)?JSON.parse(readFileSync(configFile,'utf8').replace(/^\uFEFF/,'')):{};
 if(!local||Array.isArray(local)||typeof local!=='object')throw Error('INVALID_LOCAL_CONFIG');
 for(const key of Object.keys(local))if(!allowed.has(key))throw Error('UNKNOWN_CONFIG_FIELD: '+key);
 const c={...local,...overrides},home=env.DSH_HOME||join(homedir(),'.dsh');
 const python=executable(env.CAMPUS_PYTHON||c.python,[join(home,'dsh-runtimes/dsh-primary-runtime/dependencies/python/python.exe')],['python.exe','python3.exe','python3','python'],env,root);
 const node=executable(env.CAMPUS_NODE||c.node,[join(home,'dsh-runtimes/dsh-primary-runtime/dependencies/node/bin/node.exe'),join(home,'dsh-runtimes/dsh-primary-runtime/dependencies/node/node.exe'),...(!process.versions.electron?[process.execPath]:[])],['node.exe','node'],env,root);
 const browser=executable(env.CAMPUS_BROWSER||c.browser,[join(env['ProgramFiles(x86)']||'C:/Program Files (x86)','Microsoft/Edge/Application/msedge.exe'),join(env.ProgramFiles||'C:/Program Files','Google/Chrome/Application/chrome.exe'),join(env.LOCALAPPDATA||join(homedir(),'AppData/Local'),'Google/Chrome/Application/chrome.exe')],['msedge.exe','chrome.exe','chromium'],env,root);
 const dataRoot=resolve(root,env.CAMPUS_DATA_ROOT||c.dataRoot||join(homedir(),'.dsh-campus-recruitment'));
 if(dataRoot===root||dataRoot===join(root,'plugin')||dataRoot===join(root,'recruit'))throw Error('DATA_ROOT_MUST_BE_SEPARATE_FROM_SOURCE');
 const region=c.region||'cn';if(!['cn','global'].includes(region))throw Error('INVALID_MINIMAX_REGION');
 const limit=c.monthlySearchLimit??260;if(!Number.isInteger(limit)||limit<1||limit>1000)throw Error('INVALID_MONTHLY_SEARCH_LIMIT');
 const year=c.graduation_year??2027;if(!Number.isInteger(year)||year<2020||year>2100)throw Error('INVALID_GRADUATION_YEAR');
 if(c.profile!==undefined&&(typeof c.profile!=='string'||c.profile.length>8000))throw Error('INVALID_PROFILE');
 if(c.keywords!==undefined&&(!Array.isArray(c.keywords)||c.keywords.length>8||c.keywords.some(k=>typeof k!=='string'||!k.trim()||k.length>150)))throw Error('INVALID_KEYWORDS');
 if(c.official_domains!==undefined&&(!Array.isArray(c.official_domains)||c.official_domains.some(x=>typeof x!=='string'||!/^[a-z0-9.-]+$/i.test(x))))throw Error('INVALID_OFFICIAL_DOMAINS');
 for(const key of ['provider','model','reasoningEffort','credentialRef'])if(c[key]!==undefined&&(typeof c[key]!=='string'||!c[key]||c[key].length>150))throw Error('INVALID_'+key.toUpperCase());
 return {root,configFile,dataRoot,python,node,browser,provider:c.provider||'minimax',model:c.model||'MiniMax-M3.1-Flash',reasoningEffort:c.reasoningEffort||'low',credentialRef:c.credentialRef||'MINIMAX_API_KEY',region,monthlySearchLimit:limit,graduation_year:year,
  apiOrigin:region==='cn'?'https://api.minimaxi.com':'https://api.minimax.io',quotaOrigin:region==='cn'?'https://www.minimaxi.com':'https://www.minimax.io'};
}
