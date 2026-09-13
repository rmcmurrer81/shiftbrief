 'use strict';
let generalPending=null,generalPolling=false;
try{generalPending=JSON.parse(sessionStorage.getItem('shiftbrief-general-pending')||'null');}catch{}
const generalSelect=node('select');generalSelect.id='conversation-mode';generalSelect.setAttribute('aria-label','Sarah conversation engine');
for(const [value,label] of [['records','Records · offline'],['ollama','AI · local Ollama'],['bedrock','AI · cloud Bedrock']])generalSelect.add(new Option(label,value));
if(generalPending&&['ollama','bedrock'].includes(generalPending.conversation_mode))generalSelect.value=generalPending.conversation_mode;
const generalLabel=node('label','Conversation engine');generalLabel.htmlFor=generalSelect.id;
const generalInfo=node('small');generalInfo.id='general-ai-notice';
const generalStatus=node('p');generalStatus.id='general-ai-status';generalStatus.setAttribute('role','status');
const generalRecover=btt('Check saved AI response',()=>recoverGeneralChat(),'quiet');generalRecover.id='general-ai-recover';generalRecover.hidden=true;
document.querySelector('.chat-compose').prepend(generalLabel,generalSelect,generalInfo,generalStatus,generalRecover);
generalSelect.onchange=()=>{
 const cloud=generalSelect.value==='bedrock',ai=generalSelect.value!=='records';
 generalInfo.textContent=cloud?'Cloud AI sends your question, recent conversation and selected saved facts to your configured AWS model. No keys are saved here.':ai?'Local AI uses your configured Ollama model on this computer. Changes still use review forms.':'Records stays offline. AI modes interpret read questions using saved facts; changes still use review forms.';
 const label=document.querySelector('header .local');if(label)label.textContent=cloud?'Cloud AI selected':ai?'Local AI selected':'Records · no model needed';
};
generalSelect.onchange();
function saveGeneralPending(){if(generalPending)sessionStorage.setItem('shiftbrief-general-pending',JSON.stringify(generalPending));else sessionStorage.removeItem('shiftbrief-general-pending');generalRecover.hidden=!generalPending;generalSelect.disabled=!!generalPending;}
const generalApiBase=api;
api=async function(route,body){
 if(route!=='assistant/message'||generalSelect.value==='records')return generalApiBase(route,body);
 const candidate={...body,conversation_mode:generalSelect.value};
 if(generalPending){const comparable={...generalPending};delete comparable.request_id;if(JSON.stringify(comparable)!==JSON.stringify(candidate))throw Error('Check the existing AI response before starting a different question. Your new text is still here.');}
 else generalPending={...candidate,request_id:crypto.randomUUID().replaceAll('-','')};
 saveGeneralPending();
 try{
  const response=await fetch('/api/'+route,{method:'POST',headers:{'Content-Type':'application/json','X-ShiftBrief-Token':token},body:JSON.stringify(generalPending)}),value=await response.json();
  if(!response.ok){const error=Error(value.error||'The selected AI request was rejected.');error.definitive=[400,403,422].includes(response.status);throw error;}
  if(value.kind!=='general_ai_job'){generalPending=null;saveGeneralPending();}
  return value;
 }catch(error){
  if(error.definitive){generalPending=null;saveGeneralPending();generalStatus.textContent=error.message;}
  else generalStatus.textContent='The AI request did not return a confirmed answer. Check its saved response; it will not be sent again automatically. '+error.message;
  throw error;
 }
};
function renderGeneralResult(row){
 if(row.status==='ready'){
  const result=row.result;
  if(result?.kind?.startsWith('general_ai_')){workHistoryRead=null;employerInsightRead=null;comparisonRead=null;questionHelp={team:state.current_production,answer:result.answer};showScreen('comparison');renderComparison();}
  else routeEmployeeReply(result);
  generalStatus.textContent='Answered with '+(row.provider==='bedrock'?'cloud Bedrock':'local Ollama')+' and exact saved-record tools.';
 }else{generalStatus.textContent=row.message;workHistoryRead=null;employerInsightRead=null;comparisonRead=null;questionHelp={team:state.current_production,answer:row.message};showScreen('comparison');renderComparison();}
}
async function watchGeneralChat(first,team,week){
 if(generalPolling)return;generalPolling=true;
 try{
  let row=first;
  for(;;){
   if(state.current_production!==team||state.staffing.selected_week!==week){generalStatus.textContent='The original team’s AI response is saved separately. Return to that team to check it.';return;}
   generalStatus.textContent=row.message||'Sarah is reading saved facts…';
   if(row.status!=='running')break;
   await new Promise(resolve=>setTimeout(resolve,450));
   row=await generalApiBase('assistant/general?team='+encodeURIComponent(team)+'&id='+encodeURIComponent(row.id));
  }
  if(generalPending?.request_id===row.id){generalPending=null;saveGeneralPending();}
  await refresh();
  if(state.current_production===team&&state.staffing.selected_week===week){
   const last=state.assistant?.messages?.at(-1);if(last?.general_request_id===row.id)renderGeneralResult(row);
  }
 }catch(error){generalStatus.textContent='The saved response could not be read. Use Check saved AI response; no new model request was sent. '+error.message;throw error;}
 finally{generalPolling=false;}
}
async function recoverGeneralChat(){
 const pending=generalPending;
 const last=state.assistant?.messages?.at(-1),rid=pending?.request_id||last?.general_request_id,team=pending?.production_id||state.current_production;
 if(!rid)throw Error('No exact saved AI request is selected.');
 if(team!==state.current_production)throw Error('Return to the original team to check that AI response.');
 const row=await generalApiBase('assistant/general?team='+encodeURIComponent(team)+'&id='+encodeURIComponent(rid));
 await watchGeneralChat(row,team,state.staffing.selected_week);
}
const generalRefreshBase=refresh;
refresh=async function(){const value=await generalRefreshBase();const last=state.assistant?.messages?.at(-1);generalRecover.hidden=!generalPending&&!last?.general_request_id;return value;};
saveGeneralPending();
