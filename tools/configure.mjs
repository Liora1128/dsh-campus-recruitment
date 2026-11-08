import {readFileSync,existsSync,writeFileSync} from 'node:fs';
import {join} from 'node:path';
import {CODE_ROOT,resolveSettings} from '../plugin/settings.js';
const mapping={'--data-root':'dataRoot','--python':'python','--node':'node','--browser':'browser'};
try{
 const file=join(CODE_ROOT,'config.local.json');
 const config=JSON.parse(readFileSync(existsSync(file)?file:join(CODE_ROOT,'config.example.json'),'utf8').replace(/^\uFEFF/,''));
 const args=process.argv.slice(2);
 for(let i=0;i<args.length;i+=2){if(!mapping[args[i]]||!args[i+1])throw Error('Usage: configure.mjs [--data-root PATH] [--python PATH] [--node PATH] [--browser PATH]');config[mapping[args[i]]]=args[i+1]}
 // Validate before replacing the local file; no DSH profile or system settings are edited.
 resolveSettings(config);writeFileSync(file,JSON.stringify(config,null,2)+'\n',{encoding:'utf8'});
 console.log('Saved local configuration. Next: run tools/doctor.mjs, then install this directory using DSH Plugins.');
}catch(error){console.error(error.message);process.exitCode=1}
