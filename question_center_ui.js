'use strict';
// Saved answers choose the center view. Navigation never saves employee records.
let comparisonRead=null,comparisonTab='pay',comparisonCurrency='',comparisonPage=0;
let questionTeam=null,questionChatIndex=-1,questionChatSignature='',questionHelp=null,questionChatRenderKey='';
const questionViewBase=showScreen;
showScreen=function(name){questionViewBase(name);document.body.classList.toggle('question-insight',['comparison','hours'].includes(name));if(name==='comparison')$('screen-title').textContent='Your question. Your team. Your answer.';};
function askFromCenter(text){$('chat-message').value=text;$('chat-send').click();}
function comparisonCurrent(read){
 if(!read||read.team_id!==state.current_production)return false;
 if(read.status==='clarification')return true;
 const employees=state.staffing?.employees||[];
 return read.rows.length===employees.length&&read.rows.every(row=>employees.some(e=>e.id===row.employee_id&&e.revision===row.expected_revision));
}
function comparisonEmployee(id){const e=state.staffing?.employees.find(row=>row.id===id);if(!e)return;if(formDraft){status('Your open employee draft is preserved. Close it before opening another employee.');return;}openEmployee(e);}
function centerStat(label,value,note){const card=node('article',undefined,'question-stat');card.append(node('span',label),node('strong',String(value)),node('small',note));return card;}
function centerMessage(wrap,title,message,actions=[]){const card=node('div',undefined,'question-empty');card.append(node('span','YOUR NEXT STEP','eyebrow'),node('h2',title),node('p',message));const buttons=node('div',undefined,'question-actions');for(const [label,action] of actions)buttons.append(btt(label,action,'quiet'));card.append(buttons);wrap.append(card);}
function renderComparison(){
 const wrap=$('employee-comparison-body');if(!wrap)return;wrap.replaceChildren();const read=comparisonRead;
 if(questionHelp?.team===state.current_production){centerMessage(wrap,'What would you like to see?',questionHelp.answer,[['Compare pay & time on team',()=>askFromCenter('Who makes the most money and how long has everyone been working here?')],['Compare planned hours',()=>askFromCenter('Who works the most this week?')],['Open employees',()=>showScreen('people')],['Add an employee',()=>openEmployee()]]);return;}
 if(!comparisonCurrent(read)){centerMessage(wrap,'This answer needs a fresh look.','The team or an employee record has changed. Ask again to compare the current saved details.',[['Compare pay and time on team',()=>askFromCenter('Who makes the most money and how long has everyone been working here?')]]);return;}
 const header=node('div',undefined,'question-result-heading');header.append(node('span','TEAM INSIGHT','eyebrow'),node('h2',read.requested.length>1?'Pay & time on your team':read.requested[0]==='tenure'?'Time on your team':'Recorded hourly pay'),node('p',read.request_text),node('small',read.team_name+' · As of '+read.as_of_date));wrap.append(header);
 if(read.status==='clarification'){centerMessage(wrap,'Choose the comparison',read.clarification);return;}
 if(!read.rows.length){centerMessage(wrap,'Your team starts here.','Add an employee and their actual start date. Recorded hourly rates can then be compared.',[['Add employee',()=>openEmployee()],['Import employees',()=>openEmployeeImport()]]);return;}
 const tabs=node('div',undefined,'question-tabs');tabs.setAttribute('role','tablist');
 const available=[...(read.requested.includes('hourly_pay')?[['pay','Hourly pay']]:[]),...(read.requested.includes('tenure')?[['tenure','Time on team']]:[]),['details','All details']];
 if(!available.some(([key])=>key===comparisonTab))comparisonTab=available[0][0];
 for(const [key,label] of available){const tab=btt(label,()=>{comparisonTab=key;comparisonPage=0;renderComparison();},key===comparisonTab?'primary':'quiet');tab.setAttribute('role','tab');tab.setAttribute('aria-selected',String(key===comparisonTab));tabs.append(tab);}wrap.append(tabs);
 const panel=node('div',undefined,'question-result-panel');panel.setAttribute('role','tabpanel');wrap.append(panel);
 if(comparisonTab==='pay'){
  const groups=read.pay.groups||[];if(!groups.some(g=>g.currency===comparisonCurrency))comparisonCurrency=groups[0]?.currency||'';
  if(groups.length>1){const field=node('label','Currency · compared separately','question-currency'),select=node('select');select.setAttribute('aria-label','Comparison currency');for(const g of groups){const option=node('option',g.currency);option.value=g.currency;select.append(option);}select.value=comparisonCurrency;select.onchange=()=>{comparisonCurrency=select.value;comparisonPage=0;renderComparison();};field.append(select);panel.append(field);}
  const group=groups.find(g=>g.currency===comparisonCurrency),leaders=(group?.rows||[]).filter(r=>group.leader_ids.includes(r.employee_id));
  const stats=node('div',undefined,'question-stats');stats.append(centerStat('Highest recorded rate',leaders.length?comparisonCurrency+' '+leaders[0].amount+' / hr':'Not recorded',leaders.length?leaders.map(r=>r.name).join(' · '):'For active employees'),centerStat('Rates available',read.rows.filter(r=>r.employment_status==='active'&&r.rate).length,read.pay.missing_employee_ids.length+' active employees with no saved rate'),centerStat('People in this comparison',read.rows.length,'Former and future employees are listed in All details'));panel.append(stats);
  panel.append(node('p','These are saved hourly rates, not earnings or take-home pay. Active employees are compared within each currency.','question-context'));
  if(!group?.rows.length){centerMessage(panel,'Add rates to bring this view to life.','There are no recorded hourly rates for active employees on this date. A missing rate is not zero.',[['Open employees',()=>showScreen('people')]]);}
  else renderComparisonBars(panel,group.rows.map(r=>({id:r.employee_id,name:r.name,value:r.amount_minor/100,label:group.currency+' '+r.amount+' / hr'})),'Recorded hourly rate · '+group.currency);
 }else if(comparisonTab==='tenure'){
  const known=read.rows.filter(r=>r.tenure.status==='elapsed').sort((a,b)=>b.tenure.days-a.tenure.days||a.name.localeCompare(b.name));
  const leaders=read.rows.filter(r=>(read.tenure.leader_ids||[]).includes(r.employee_id));const stats=node('div',undefined,'question-stats');stats.append(centerStat('Longest service · active team',leaders[0]?.tenure.label||'Not recorded',leaders.length?leaders.map(r=>r.name).join(' · '):'Start dates are needed'),centerStat('Start dates available',read.rows.filter(r=>r.tenure.status!=='unknown').length,read.rows.filter(r=>r.tenure.status==='unknown').length+' dates not recorded'),centerStat('People on this view',read.rows.length,'Former service stops at the saved end date'));panel.append(stats);
  panel.append(node('p','Calendar time since the recorded start date. Future employees have not started; former employees stop at their recorded end date.','question-context'));
  if(!known.length)centerMessage(panel,'No elapsed service to compare.','Start dates are missing or are still in the future. See All details for each person’s saved dates.');
  else renderComparisonBars(panel,known.map(r=>({id:r.employee_id,name:r.name+(r.employment_status==='former'?' (former)':''),value:r.tenure.days,label:r.tenure.label})),'Calendar days on the team');
 }else{
  const table=node('table',undefined,'question-details'),head=node('thead'),tr=node('tr');for(const label of ['Employee','Hourly rate','Started','Time on team'])tr.append(node('th',label));head.append(tr);table.append(head);const body=node('tbody');for(const row of read.rows){const tr=node('tr'),name=node('td');name.append(btt(row.name,()=>comparisonEmployee(row.employee_id),'quiet'),node('small',row.employment_status+(row.end_date?' · End '+row.end_date:'')));tr.append(name,node('td',row.rate?row.rate.currency+' '+row.rate.amount+' / hr':row.rate_status==='invalid_saved_history'?'Check saved history':'Not recorded'),node('td',row.start_date||'Not recorded'),node('td',row.tenure.label));body.append(tr);}table.append(body);panel.append(table);
 }
}
function renderComparisonBars(panel,rows,label){const limit=innerWidth<700?4:8;comparisonPage=Math.min(comparisonPage,Math.max(0,Math.ceil(rows.length/limit)-1));const chart=node('div',undefined,'question-chart');panel.append(chart);ShiftBriefCharts.renderDimensionalBars(chart,{rows:rows.slice(comparisonPage*limit,(comparisonPage+1)*limit),label,onSelect:comparisonEmployee,maxValue:Math.max(...rows.map(r=>r.value),0)});const pages=node('div',undefined,'pager');pager(pages,comparisonPage,Math.ceil(rows.length/limit),n=>{comparisonPage=n;renderComparison();});panel.append(pages);}
const questionRouteBase=routeEmployeeReply;
routeEmployeeReply=function(reply){
 if(reply?.employee_comparison){if(reply.employee_comparison.team_id!==state.current_production)return;questionHelp=null;comparisonRead=structuredClone(reply.employee_comparison);comparisonTab=comparisonRead.requested.includes('hourly_pay')?'pay':'tenure';comparisonCurrency='';comparisonPage=0;showScreen('comparison');renderComparison();return;}
 if(reply?.kind==='onboarding'&&reply.employee_summary){comparisonRead=null;questionHelp={team:state.current_production,answer:reply.answer};showScreen('comparison');return;}
 return questionRouteBase(reply);
};
const questionHoursBase=renderEmployeeHours;
renderEmployeeHours=function(){
 const chart=computedHoursChart(),rows=chart.rows||[],wrap=$('employee-hours-chart');$('hours-view-toggle').hidden=true;wrap.classList.remove('is-3d');wrap.classList.add('question-hours');wrap.replaceChildren();$('hours-pages').replaceChildren();
 if(chart.scope_error){$('hours-week-label').textContent='Choose a week';$('hours-ranking-detail').textContent='';centerMessage(wrap,'Which week should I compare?',chart.scope_error,[['This week',()=>askFromCenter('Who works the most this week?')],['Last week',()=>askFromCenter('Who works the most last week?')]]);return;}
 $('hours-week-label').textContent='Week of '+chart.week_start+' · Planned hours';const highest=Math.max(...rows.map(r=>r.minutes),0);$('hours-ranking-detail').textContent=highest?'Based on saved shifts with breaks subtracted. Actual time worked is not recorded here.':'No saved planned hours for this week.';
 if(!highest){centerMessage(wrap,chart.has_saved_schedule?'This week has no planned work hours.':'This week has not been scheduled.',rows.length+' employees are saved. Build a week from their dated availability, or open a week that already has shifts.',[['Review employee availability',()=>showScreen('people')],['Suggest this selected week',()=>askFromCenter('Suggest the selected week')],['Open schedule',()=>showScreen('schedule')]]);return;}
 const leaders=rows.filter(r=>r.minutes===highest),summary=node('div',undefined,'question-stats');summary.append(centerStat('Most planned hours',hours(highest)+' h',leaders.map(r=>r.name).join(' · ')),centerStat('Team total',hours(rows.reduce((n,r)=>n+r.minutes,0))+' h','Saved planned hours'),centerStat('Employees',rows.length,'Click a column to open details'));wrap.append(summary);const target=node('div',undefined,'question-chart');wrap.append(target);const limit=innerWidth<700?4:8;hoursPage=Math.min(hoursPage,Math.max(0,Math.ceil(rows.length/limit)-1));ShiftBriefCharts.renderDimensionalBars(target,{rows:rows.slice(hoursPage*limit,(hoursPage+1)*limit).map(r=>({id:r.employee_id,name:r.name,value:r.minutes/60,label:hours(r.minutes)+' h'})),label:'Planned hours · week of '+chart.week_start,onSelect:comparisonEmployee,maxValue:highest/60});pager($('hours-pages'),hoursPage,Math.ceil(rows.length/limit),n=>{hoursPage=n;renderEmployeeHours();});
};
const questionRenderBase=renderStaffing;
renderStaffing=function(){if(questionTeam!==state.current_production){questionTeam=state.current_production;comparisonRead=null;questionHelp=null;comparisonPage=0;}questionRenderBase();if(deskScreen==='comparison')renderComparison();};
const questionConversationBase=renderConversation;
renderConversation=function(){
 const savedScroll=$('conversation').scrollTop;questionConversationBase();const all=state.assistant?.messages||[],replies=all.map((row,index)=>({...row,index})).filter(row=>row.role==='assistant');if(!replies.length)return;
 const signature=state.current_production+'|'+all.length+'|'+replies.at(-1).text;if(signature!==questionChatSignature){questionChatSignature=signature;questionChatIndex=replies.length-1;}questionChatIndex=Math.min(Math.max(0,questionChatIndex),replies.length-1);const reply=replies[questionChatIndex],wrap=$('conversation');wrap.replaceChildren();const question=all[reply.index-1];if(question?.role==='user')wrap.append(node('p',question.text,'question-chat-prompt'));const row=node('div',undefined,'chat-message assistant');row.append(node('strong','Sarah'),node('p',reply.text));if(reply.navigation||reply.employee_comparison)row.append(btt('Show this answer',()=>routeEmployeeReply(reply),'quiet'));wrap.append(row);pager($('chat-pages'),questionChatIndex,replies.length,n=>{questionChatIndex=n;renderConversation();if(replies[n].navigation||replies[n].employee_comparison)routeEmployeeReply(replies[n]);});const renderKey=signature+'|'+questionChatIndex;wrap.scrollTop=renderKey===questionChatRenderKey?savedScroll:0;questionChatRenderKey=renderKey;
};

$('week-board').classList.add('depth');$('chart-mode').textContent='2D view';
