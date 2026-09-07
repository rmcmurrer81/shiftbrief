import {PythonBridge} from './runtime/python-rpc.mjs';
import {BrowserStore} from './runtime/browser-store.mjs';
const byId=id=>document.getElementById(id),loading=byId('browserLoading'),stage=byId('browserStage');
const databaseName='shiftbrief-browser-workspace-v1';
let db, revision=null, loaded=false, queue=Promise.resolve();
const bridge=new PythonBridge(new URL('./runtime/python-rpc-worker.mjs',import.meta.url),{onStage:message=>stage.textContent=message});
function calendar(){const d=new Date(),pad=n=>String(n).padStart(2,'0'),day=d.getFullYear()+'-'+pad(d.getMonth()+1)+'-'+pad(d.getDate()),offset=-d.getTimezoneOffset(),zone=(offset<0?'-':'+')+pad(Math.floor(Math.abs(offset)/60))+':'+pad(Math.abs(offset)%60);return {local_date:day,local_timestamp:day+'T'+pad(d.getHours())+':'+pad(d.getMinutes())+':'+pad(d.getSeconds())+zone,timezone:Intl.DateTimeFormat().resolvedOptions().timeZone};}
const call=payload=>bridge.call({...payload,...calendar()});
function lock(fn){const action=()=>navigator.locks.request(databaseName,fn),p=queue.then(action,action);queue=p.catch(()=>{});return p;}
async function sync(){const saved=await db.get('workspace'),savedRevision=saved?.revision||null;if(!loaded||savedRevision!==revision){await call({operation:'restore',snapshot:saved?.snapshot||null});revision=savedRevision;loaded=true;}return saved;}
function bytesFromBase64(value){const s=atob(value),out=new Uint8Array(s.length);for(let i=0;i<s.length;i++)out[i]=s.charCodeAt(i);return out;}
function base64FromBytes(bytes){let value='';for(let i=0;i<bytes.length;i+=16384)value+=String.fromCharCode(...bytes.subarray(i,i+16384));return btoa(value);}
async function commit(){const {snapshot}=await call({operation:'snapshot'}),id=crypto.randomUUID();await db.put('workspace',{schema:1,revision:id,snapshot,saved_at:new Date().toISOString()});revision=id;}
async function request(path,options={}){
 const expectedTeam=window.shiftBriefTeam?.();
 return lock(async()=>{const previous=await sync(),headers=new Headers(options.headers||{}),body=options.body?JSON.parse(options.body):{};let result;
  try{result=await call({operation:'request',path,method:options.method||'GET',body,token:headers.get('X-ShiftBrief-Token'),expected_team:expectedTeam});if(result.changed)await commit();}
  catch(error){await call({operation:'restore',snapshot:previous?.snapshot||null});throw Error('Your change could not be saved. Your previous workspace is intact. '+error.message);}
  const output=result.base64?bytesFromBase64(result.base64):result.content_type==='application/json'?JSON.stringify(result.body):result.body;
  return new Response(output,{status:result.status,headers:{'Content-Type':result.content_type||'application/json'}});
 });
}
function download(name,bytes,mime='application/zip'){const url=URL.createObjectURL(new Blob([bytes],{type:mime})),a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
async function downloadAPI(path,name){try{const response=await request(path);if(!response.ok)throw Error((await response.json()).error);download(name,new Uint8Array(await response.arrayBuffer()),response.headers.get('Content-Type'));}catch(error){window.shiftBriefStatus?.(error.message);}}
async function workspaceSnapshot(){return lock(async()=>{await sync();return (await call({operation:'snapshot'})).snapshot;});}
async function restoreCopy(encoded){return lock(async()=>{const previous=await sync();try{await call({operation:'restore',snapshot:encoded});await commit();}catch(error){await call({operation:'restore',snapshot:previous?.snapshot||null});throw error;}});}
function workspaceFiles(){
 const button=document.createElement('button');button.className='quiet workspace-file-button';button.textContent='⋯';button.setAttribute('aria-label','Workspace copies and browser information');document.querySelector('.header-actions').prepend(button);
 const dialog=document.createElement('dialog');dialog.id='browserFilesDialog';dialog.innerHTML='<div class="dialog-body"><h2>Workspace copies</h2><p class="browser-copy-summary">Your teams and sources stay in this browser. Save a copy before clearing browser data or moving computers.</p><button id="saveWorkspaceCopy" class="primary">Save a workspace copy</button><label for="openWorkspaceCopy">Open a saved copy</label><input id="openWorkspaceCopy" type="file" accept=".zip"><div id="copyReview" hidden><p>Opening this replaces the current browser workspace. Save your current copy first.</p><button id="confirmWorkspaceCopy" class="primary">Open this copy</button></div><p id="browserFileStatus" role="status"></p><button id="browserAbout" class="quiet">How this edition works</button><button id="closeWorkspaceFiles" class="quiet">Back to workspace</button></div>';document.body.append(dialog);
 button.onclick=()=>dialog.showModal();byId('closeWorkspaceFiles').onclick=()=>dialog.close();
 byId('browserAbout').onclick=()=>window.shiftBriefReadPages('Browser edition','Scheduling, source comparison and written Sarah replies run in this browser without installed Python, a model, a key or credits. Sarah uses structured rules and your saved facts; this is not a general-purpose language model. Save a workspace copy to keep a separate backup. This browser edition does not execute Strands or satisfy that hackathon requirement by itself. The Desktop source retains the separate actual Strands integration. Optional Desktop voice and local file watching are not connected here. Runtime and PDF library license notices: ./runtime/licenses/NOTICE.txt');
 byId('saveWorkspaceCopy').onclick=async()=>{try{byId('browserFileStatus').textContent='Preparing your copy…';download('ShiftBrief-workspace-'+calendar().local_date+'.zip',bytesFromBase64(await workspaceSnapshot()));byId('browserFileStatus').textContent='Workspace copy prepared for download.';}catch(error){byId('browserFileStatus').textContent=error.message;}};
 byId('openWorkspaceCopy').onchange=()=>{byId('copyReview').hidden=!byId('openWorkspaceCopy').files.length;byId('browserFileStatus').textContent='';};
 byId('confirmWorkspaceCopy').onclick=async()=>{const file=byId('openWorkspaceCopy').files[0];if(!file)return;byId('confirmWorkspaceCopy').disabled=true;try{if(file.size>50*1024*1024)throw Error('Choose a copy smaller than 50 MB.');await restoreCopy(base64FromBytes(new Uint8Array(await file.arrayBuffer())));location.reload();}catch(error){byId('browserFileStatus').textContent='Copy could not be opened: '+error.message;}finally{byId('confirmWorkspaceCopy').disabled=false;}};
}
async function script(name){await new Promise((resolve,reject)=>{const el=document.createElement('script');el.src=new URL(name,import.meta.url);el.onload=resolve;el.onerror=()=>reject(Error('Could not open '+name));document.body.append(el);});}
try{
 if(!navigator.locks||!globalThis.indexedDB)throw Error('Use a current browser with local storage enabled to save your workspace.');
 db=new BrowserStore(databaseName);await db.ready;
 const manifest=await(await fetch(new URL('browser-files.json',import.meta.url))).json();
 await bridge.initialize({runtimeURL:new URL('./runtime/pyodide/',import.meta.url).href,entrypoint:'browser_adapter',files:manifest.files.map(f=>({...f,url:new URL(f.url,import.meta.url).href})),extraPaths:['/app/vendor/pypdf.zip']});
 await lock(()=>sync());
 window.shiftBriefBackend={fetch:request,download:downloadAPI,snapshot:workspaceSnapshot,restore:restoreCopy};
 window.SarahVoice={configure(){},read(){},stop(){}};
 for(const name of ['app.js','staffing_ui.js','operating_ui.js','source_handoff_ui.js'])await script(name);
 document.querySelectorAll('#engine-mode option').forEach(o=>{if(o.value!=='sarah_local')o.remove()});byId('engine-mode').value='sarah_local';
 byId('source-form').querySelector('details').hidden=true;
 byId('voice-toggle').hidden=true;document.querySelector('.voice-player').hidden=true;
 document.querySelector('.local').textContent='Browser · no setup';document.querySelector('.nav-bottom p').innerHTML='Saved in this browser.<br>No messages sent.';
 await window.shiftBriefRefresh();workspaceFiles();loading.remove();window.shiftBriefBrowserReady=true;
}catch(error){stage.textContent='The workspace could not open: '+error.message;byId('browserRetry').hidden=false;byId('browserRetry').onclick=()=>location.reload();}
