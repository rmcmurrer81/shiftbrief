'use strict';
// A portable copy contains one team's saved records. Opening is additive.
let teamFilePending=null,teamFileBusy=false;
const teamFileInert=new Map();
const teamFileName='Maple-Street-Fictional-Jun-Sep-2026.shiftbrief.json';
const teamFileScope='Employees, contacts, hourly rates and their history, dated availability, time off, operating settings, saved planned schedules and recorded actual work. Use Back up all businesses for every business, documents and chats.';
async function teamFileRequest(kind,body){const transport=window.shiftBriefBackend?.fetch||fetch;const response=await transport('/api/team-file/'+kind,{method:'POST',headers:{'Content-Type':'application/json','X-ShiftBrief-Token':token},body:JSON.stringify(body)});const value=await response.json();if(!response.ok){const error=Error(value.error||'The file request could not be completed.');error.definitive=[400,403].includes(response.status);throw error;}return value;}
function teamFileDraftGuard(){if(formDraft||payFormDraft||payProposal||employeeImport){throw Error('Finish or close the employee, pay or import draft before opening another team. Your draft is still here.');}}
function teamFileDownload(name,text){const url=URL.createObjectURL(new Blob([text],{type:'application/json;charset=utf-8'})),a=node('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),30000);}
function teamFileNotice(text){$('team-file-notice').textContent=text;}
function teamFileButtons(){document.querySelectorAll('[data-team-file]').forEach(b=>b.disabled=teamFileBusy);$('team-file-retry').hidden=!teamFilePending;$('team-file-retry').disabled=teamFileBusy;
 if(teamFileBusy){for(const el of document.querySelectorAll('header,.desk-nav,.sarah-desk,.desk-center > :not(.team-file-bar)')){if(!teamFileInert.has(el))teamFileInert.set(el,el.inert);el.inert=true;}}
 else{for(const [el,value] of teamFileInert)el.inert=value;teamFileInert.clear();}
}
async function teamFileRun(pending){
 if(teamFileBusy)return;teamFileDraftGuard();teamFileBusy=true;teamFilePending=pending;teamFileButtons();teamFileNotice('Opening your team records…');
 try{
  const result=await teamFileRequest(pending.kind,pending.body);
  teamFilePending=null;selectedDoc='';selectedBrief='';previewId=null;historyData=null;
  await refresh();showScreen('schedule');
  const s=result.summary;
  teamFileNotice((result.replayed?'This action was already saved. ':result.title+' opened. ')+(s?.employees??0)+' employees · '+(s?.schedule_dates??0)+' saved schedule dates.');
  status('Your other businesses are still available in the Business menu. Planned shifts and recorded actual work are stored separately. Open Recorded work for past completed hours.');
 }catch(error){if(error.definitive)teamFilePending=null;teamFileNotice(error.message+(teamFilePending?' Use Retry this action to check the same request.':''));}
 finally{teamFileBusy=false;teamFileButtons();}
}
function teamFileBegin(kind,extra){teamFileDraftGuard();if(teamFilePending)throw Error('Resolve the previous file action with Retry this action before starting another.');return teamFileRun({kind,body:{...extra,expected_team_id:state.current_production,request_id:crypto.randomUUID()}});}
function teamFileNew(){act(async()=>{teamFileDraftGuard();const {d,body}=modal('Create a business');body.append(node('p','Start with empty employee and schedule records. Your other saved businesses remain available.'));const label=node('label','Business name'),input=node('input');input.id='team-file-title';input.maxLength=100;label.htmlFor=input.id;body.append(label,input,btt('Create blank business',async()=>{if(!input.value.trim())throw Error('Enter a name for this business.');const name=input.value.trim();d.close();await teamFileBegin('new',{title:name});},'primary'));input.focus();});}
async function teamFileOpen(file){if(!file)return;teamFileDraftGuard();if(file.size>5000000)throw Error('Choose a ShiftBrief team file smaller than 5 MB.');const text=await file.text();await teamFileBegin('open',{text});}
function teamFileExample(){act(async()=>{teamFileDraftGuard();const {d,body}=modal('Load fictional demo');body.append(node('p','Maple Street has 8 fictional employees, saved hourly rates and raises, different start dates, a departure, and 122 saved schedule dates from June through September 2026.'),node('p','Includes 385 fictional completed work records from June 1 through September 7, plus separate planned shifts. All people and records are invented for testing. This opens as a separate team.'),node('p',teamFileScope,'muted'),btt('Load demo',async()=>{const response=await fetch('./'+teamFileName);if(!response.ok)throw Error('The example file could not be loaded.');const blob=await response.blob();d.close();await teamFileOpen(blob);},'primary'));});}
function teamFileQuestions(){const {d,body}=modal('Things to ask Sarah');body.append(node('p','Try these with Maple Street. Choose a question to show its answer and matching view. Changes use the employee and pay details you review.'));for(const text of ['Can you tell me who has worked the most?','When was the last time each person got a raise?','Who was late the most often?','Who has worked the most in August 2026?','Who makes the most money and how long has everyone been working here?','Who works the most in the week of 2026-07-05?','Show Ada Chen’s pay history','When did Jordan Lee leave?','Show team contacts','Who is available on 2026-09-08?'])body.append(btt(text,()=>{d.close();askFromCenter(text);},'quiet'));}
function setupTeamFiles(){
 const bar=node('div',undefined,'team-file-bar');bar.setAttribute('aria-label','Team files');const controls=node('div',undefined,'team-file-controls');
 for(const [id,label,action] of [['team-file-new','New business',teamFileNew],['team-file-open','Load saved business…',()=>act(async()=>{teamFileDraftGuard();$('team-file-input').click();})],['team-file-save','Save business copy',()=>act(async()=>{if(teamFileBusy)throw Error('Wait for the file action to finish.');const copy=await teamFileRequest('export',{expected_team_id:state.current_production});teamFileDownload(copy.filename,copy.text);teamFileNotice('Business copy prepared for download.');const {body}=modal('Business copy prepared');body.append(node('p','Keep the downloaded .shiftbrief.json file. On another computer, open ShiftBrief and choose Load saved business to add this business.'),node('p',teamFileScope,'muted'),node('p','For all businesses, documents and conversations, choose Back up all businesses instead.'));})],['team-file-example','Load demo',teamFileExample],['team-file-questions','Try questions',teamFileQuestions]]){const button=btt(label,action,'quiet');button.id=id;button.dataset.teamFile='';controls.append(button);}
 const info=btt('What is saved?',()=>{const {body}=modal('Your saved business file');body.append(node('p',teamFileScope),node('p','Loading a business file adds a separate business and preserves existing businesses. Saving prepares a downloadable copy; it does not send anything to employees. Planned shifts are distinct from actual hours worked.'));},'team-file-info');controls.append(info);
 const input=node('input');input.id='team-file-input';input.type='file';input.accept='.shiftbrief.json,.json';input.hidden=true;input.onchange=()=>{const file=input.files[0];input.value='';act(()=>teamFileOpen(file));};
 const notice=node('span',undefined,'team-file-notice');notice.id='team-file-notice';notice.setAttribute('role','status');notice.setAttribute('aria-live','polite');
 const retry=btt('Retry this action',()=>act(()=>teamFilePending&&teamFileRun(teamFilePending)),'quiet');retry.id='team-file-retry';retry.hidden=true;
 bar.append(controls,input,notice,retry);document.querySelector('.desk-center').prepend(bar);
 $('new-production').onclick=teamFileNew;$('staff-example').textContent='Load demo';$('staff-example').onclick=teamFileExample;
}
setupTeamFiles();
