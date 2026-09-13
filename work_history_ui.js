'use strict';
let workHistoryRead=null,workHistoryPerson=null;
async function workRecordRequest(action,payload){
 if(!token)await refresh();
 const response=await fetch('/api/work-history/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-ShiftBrief-Token':token},body:JSON.stringify(payload)});
 const result=await response.json();if(!response.ok){const error=Error(result.error||'Work record request failed.');error.definitive=response.status===400;throw error;}return result;
}
const historyRouteBase=routeEmployeeReply;
routeEmployeeReply=function(reply){
  if(reply.work_history){workHistoryRead=reply.work_history;workHistoryPerson=null;employerInsightRead=null;questionHelp=null;showScreen('comparison');renderComparison();return;}
  workHistoryRead=null;historyRouteBase(reply);
};
async function openWorkHistory(period=''){
  const read=await api('work-history/view',{team_id:state.current_production,period});
  if(read.team_id!==state.current_production)return;
  workHistoryRead=read;workHistoryPerson=null;employerInsightRead=null;questionHelp=null;showScreen('comparison');renderComparison();
}
function workTable(headers,rows){
  const table=node('table',undefined,'work-record-table'),head=node('thead'),hr=node('tr'),body=node('tbody');
  for(const title of headers)hr.append(node('th',title));head.append(hr);table.append(head,body);
  for(const cells of rows){const tr=node('tr');for(const text of cells){const td=node('td');td.append(text instanceof Node?text:document.createTextNode(String(text)));tr.append(td);}body.append(tr);}
  return table;
}
function clockText(minutes){return String(Math.floor(minutes/60)%24).padStart(2,'0')+':'+String(minutes%60).padStart(2,'0')+(minutes>=1440?' +1 day':'');}
const historyComparisonBase=renderComparison;
renderComparison=function(){
  const read=workHistoryRead;if(!read)return historyComparisonBase();
  const wrap=$('employee-comparison-body');wrap.replaceChildren();$('screen-title').textContent=read.title;$('week-badge').textContent=read.period||'Recorded work';
  if(read.team_id!==state.current_production){workHistoryRead=null;return historyComparisonBase();}
  const intro=node('div',undefined,'work-history-heading');intro.append(node('span',read.kind==='raises'?'DATED PAY HISTORY':'COMPLETED WORK','eyebrow'),node('p',read.summary));wrap.append(intro);
  if(read.source_sha256!==state.work_history_sha256){wrap.append(node('p','The saved records changed after this answer. Refresh to use the latest details.','insight-state'),btt('Refresh records',()=>read.kind==='raises'?askFromCenter('When was the last time each person got a raise?'):openWorkHistory(read.start_date?read.start_date+' to '+read.end_date:'')));return;}
  const actions=node('div',undefined,'work-history-actions');
  actions.append(btt('All recorded work',()=>openWorkHistory()),btt('Last month',()=>openWorkHistory('last month')),btt('Latest raises',()=>askFromCenter('When was the last time each person got a raise?')),btt('Record completed work',recordWorkDialog,'primary'));
  wrap.append(actions);
  if(read.kind==='clarification')return;
  if(read.kind==='raises'){
    const known=read.rows.filter(r=>r.days_since!==null),chart=node('div');
    if(known.length){ShiftBriefCharts.renderDimensionalBars(chart,{label:'Days since latest recorded raise · '+read.as_of_date,rows:known.map(r=>({id:r.employee_id,name:r.name,value:r.days_since,label:r.days_since+' days'})),onSelect:id=>{const e=read.rows.find(r=>r.employee_id===id);askFromCenter('Show '+e.name+' pay history');}});wrap.append(chart);}
    wrap.append(workTable(['Employee','Last raise effective','Hourly rate change','Reason'],read.rows.map(r=>[r.name,r.effective_date||'No recorded increase',r.rate?r.rate.currency+' '+r.previous_rate.amount+' → '+r.rate.amount:'—',r.reason])));return;
  }
  const dates=node('div',undefined,'work-history-actions');
  const from=node('input'),to=node('input');from.type=to.type='date';from.value=read.start_date||read.first_recorded_date||'';to.value=read.end_date||'';from.setAttribute('aria-label','First work date');to.setAttribute('aria-label','Last work date');
  dates.append(node('span','Work dates'),from,node('span','to'),to,btt('Compare dates',()=>{if(!from.value||!to.value)throw Error('Choose both work dates.');return openWorkHistory(from.value+' to '+to.value);}));wrap.append(dates);
  const stats=node('div',undefined,'work-history-stats');
  for(const [label,value] of [['RECORDED HOURS',(read.total_minutes/60).toFixed(2)],['COMPLETED RECORDS',read.record_count],['DATES AVAILABLE',read.first_recorded_date?read.first_recorded_date+' — '+read.last_recorded_date:'No records yet']]){const cell=node('div');cell.append(node('span',label,'eyebrow'),node('strong',String(value)));stats.append(cell);}wrap.append(stats);
  const late=read.kind==='attendance',key=late?'late_count':'minutes',known=read.rows.filter(r=>r[key]!==null),chart=node('div');
  if(known.length){ShiftBriefCharts.renderDimensionalBars(chart,{label:(late?'Recorded late arrivals':'Recorded hours worked')+' · '+read.period,rows:known.map(r=>({id:r.employee_id,name:r.name,value:late?r[key]:r[key]/60,label:late?r[key]+' late':(r[key]/60).toFixed(2)+' h'})),onSelect:id=>{workHistoryPerson=id;renderComparison();}});wrap.append(chart);}
  wrap.append(workTable(late?['Employee','Late arrivals','Recorded starts compared']:['Employee','Recorded hours','Completed records'],read.rows.map(r=>[btt(r.name,()=>{workHistoryPerson=r.employee_id;renderComparison();}),r[key]===null?'Not recorded':late?r[key]:(r[key]/60).toFixed(2)+' h',late?r.comparable_starts:r.record_count])));
  const shown=read.records.filter(r=>!workHistoryPerson||r.employee_id===workHistoryPerson).sort((a,b)=>b.date.localeCompare(a.date)||a.start-b.start);
  const details=node('details',undefined,'work-history-detail');details.open=!!workHistoryPerson;details.append(node('summary',(workHistoryPerson?read.rows.find(r=>r.employee_id===workHistoryPerson)?.name+' · ':'')+'Completed work details ('+shown.length+')'));
  if(workHistoryPerson)details.append(btt('Show all people',()=>{workHistoryPerson=null;renderComparison();}));
  details.append(workTable(['Work date','Employee','Clock-in','Clock-out','Unpaid break','Net work','Source'],shown.map(r=>[r.date,read.rows.find(e=>e.employee_id===r.employee_id)?.name||'Unknown',clockText(r.start),clockText(r.end),r.unpaid_minutes+' min',((r.end-r.start-r.unpaid_minutes)/60).toFixed(2)+' h',r.source])));wrap.append(details);
};
function recordWorkDialog(){
  const team=state.current_production,{d,body}=modal('Record completed work'),form=node('form'),fields={};
  body.append(node('p','Enter the actual clock-in and clock-out times. You will review the entry before saving it.'));
  for(const [key,label,type] of [['employee_id','Employee','select'],['date','Work date','date'],['start','Clock-in','time'],['end','Clock-out','time'],['unpaid_minutes','Unpaid break minutes','number'],['scheduled_start','Scheduled start (optional)','time'],['note','Note (optional)','text']]){
    const labelEl=node('label',label),input=node(type==='select'?'select':'input');input.id='work-entry-'+key;if(type!=='select')input.type=type;input.required=!['scheduled_start','note'].includes(key);
    if(type==='select')for(const e of state.staffing?.employees||[]){const opt=node('option',e.name);opt.value=e.id;input.append(opt);}
    if(key==='unpaid_minutes'){input.value='0';input.min='0';input.max='1439';}
    if(key==='note')input.maxLength=1000;labelEl.htmlFor=input.id;labelEl.append(input);form.append(labelEl);fields[key]=input;
  }
  const overnightLabel=node('label','Clock-out is the following day'),overnight=node('input');overnight.type='checkbox';overnightLabel.prepend(overnight);form.append(overnightLabel);
  const reviewBody=node('div'),button=node('button','Review this record','primary');button.type='submit';form.append(button);body.append(form,reviewBody);
  let review=null,pending=null,saving=false;
  const entryStatus=node('p');entryStatus.setAttribute('role','status');body.append(entryStatus);
  const close=d.querySelector('.dialog-head button');close.onclick=()=>{if(pending||saving){entryStatus.textContent='Check the pending save before closing this entry.';return;}d.close();};
  d.addEventListener('cancel',e=>{if(pending||saving)e.preventDefault();});
  const invalidate=()=>{if(pending)return;review=null;reviewBody.replaceChildren();};form.addEventListener('input',invalidate);
  function collect(){const minute=s=>s?Number(s.split(':')[0])*60+Number(s.split(':')[1]):null;return {team_id:team,employee_id:fields.employee_id.value,date:fields.date.value,start:minute(fields.start.value),end:minute(fields.end.value)+(overnight.checked?1440:0),unpaid_minutes:Number(fields.unpaid_minutes.value),scheduled_start:minute(fields.scheduled_start.value),note:fields.note.value};}
  form.onsubmit=e=>{e.preventDefault();act(async()=>{if(pending)throw Error('Resolve the pending save before changing this entry.');const payload=collect();review=await workRecordRequest('preview',payload);if(JSON.stringify(collect())!==JSON.stringify(payload)||state.current_production!==team){review=null;entryStatus.textContent='The entry changed while it was being reviewed. Review the current values again.';return;}reviewBody.replaceChildren(node('h3','Review completed work'),node('p',review.employee_name+' · '+review.record.date+' · '+clockText(review.record.start)+' to '+clockText(review.record.end)+' · '+review.net_minutes+' net minutes'),btt('Save reviewed work',async()=>{
    if(saving)return;
    if(!pending)pending={...payload,expected_preview_sha256:review.preview_sha256,request_id:crypto.randomUUID()};
    form.inert=true;saving=true;entryStatus.textContent='Saving completed work…';
    try{await workRecordRequest('save',pending);pending=null;d.close();await refresh();await openWorkHistory();status('Completed work saved.');}
    catch(error){if(error.definitive){pending=null;review=null;form.inert=false;reviewBody.replaceChildren();entryStatus.textContent=error.message+' Your values are intact. Review this record again.';}else{entryStatus.textContent='The response was interrupted. Use Save reviewed work again to check the same request.';}}finally{saving=false;}
  },'primary'));});};
}
const workNav=btt('◷ Recorded work',()=>openWorkHistory(),'nav-item');workNav.id='recorded-work-nav';document.querySelector('.desk-nav .nav-bottom').before(workNav);
