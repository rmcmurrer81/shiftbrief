'use strict';
// The center follows the question; every numeric view uses saved records.
let employerInsightRead = null;
askFromCenter = function(text) {
  const draft = $('chat-message');
  if (draft.value.trim() && draft.value.trim() !== text.trim()) {
    status('Your unsent message is still in the chat box. Send it or clear it before choosing another question.');
    draft.focus();
    return;
  }
  draft.value = text;
  $('chat-send').click();
};
const employerRouteBase = routeEmployeeReply;
routeEmployeeReply = function(reply) {
  if (reply.employer_insight) {
    employerInsightRead = reply.employer_insight;
    questionHelp = null;
    showScreen('comparison');
    renderComparison();
    return;
  }
  employerInsightRead = null;
  employerRouteBase(reply);
};
const employerComparisonBase = renderComparison;
renderComparison = function() {
  const read = employerInsightRead;
  if (!read) return employerComparisonBase();
  const wrap = $('employee-comparison-body');
  wrap.replaceChildren();
  $('screen-title').textContent = read.title;
  if (read.team_id !== state.current_production) {
    employerInsightRead = null;
    return employerComparisonBase();
  }
  const current = state.staffing?.employees || [];
  if (read.employee_revisions.length !== current.length || !read.employee_revisions.every(r=>current.some(e=>e.id===r.id && (e.revision||1)===(r.revision||1)))) {
    wrap.append(node('p','The employee records changed after this answer. Ask again to use the latest details.','insight-state'));
    return;
  }
  const scheduleCurrent = read.hours.week_start === state.staffing?.selected_week &&
    Array.isArray(read.hours.source_revisions) && read.hours.source_revisions.length === 7 &&
    read.hours.source_revisions.every(r=>state.staffing.days.some(d=>d.date===r.date && (d.plan?.sha256 || null) === r.sha256));
  if (!scheduleCurrent) {
    wrap.append(node('p','This saved answer belongs to an earlier schedule or a different week. Ask again to compare the current saved records.','insight-state'));
    const prompt = read.topic === 'attendance' ? 'Can you compare attendance?' : read.topic === 'costs' ? 'How can we reduce staffing costs?' : read.topic === 'performance' ? 'How can we compare employee performance?' : 'How can we review reducing staff?';
    wrap.append(btt('Refresh this answer',()=>askFromCenter(prompt),'quiet'));
    return;
  }
  const intro = node('div', undefined, 'insight-intro');
  intro.append(node('span', 'TEAM REVIEW', 'eyebrow'),node('h2', read.title),node('p',read.summary));
  wrap.append(intro);
  const grid = node('div',undefined,'insight-grid');
  const available = node('section',undefined,'insight-available');
  available.append(node('span','SAVED RECORDS','insight-kicker'),node('h3',read.available_label));
  const actions = node('div',undefined,'insight-actions');
  for (const [label, prompt] of [['Compare planned hours','Who works the most in the selected week?'],['Compare hourly rates','Compare all employees hourly rates'],['Review employees','Show employees']]) {
    actions.append(btt(label,()=>askFromCenter(prompt),'quiet'));
  }
  available.append(actions);
  const chart = node('div');
  if (read.hours.has_saved_schedule) {
    ShiftBriefCharts.renderDimensionalBars(chart,{
      label:'Planned hours · '+read.hours.week_start+' – '+read.hours.week_end,
      rows:read.hours.rows.map(r=>({id:r.employee_id,name:r.name,value:r.minutes/60,label:hours(r.minutes)+' h'})),
      onSelect:id=>{const e=current.find(e=>e.id===id);if(e)askFromCenter('Tell me about '+e.name);}
    });
  } else chart.append(node('p','There are no saved shifts for this open week. Choose a saved week to compare planned hours.','insight-state'));
  available.append(chart);
  const missing = node('section',undefined,'insight-evidence');
  missing.append(node('span','BEFORE MAKING A COMPARISON','insight-kicker'),node('h3','What’s missing'));
  const list=node('ol');
  for(const text of read.missing)list.append(node('li',text));
  missing.append(list,node('p','No attendance or performance scores have been inferred from the schedule.','muted'));
  grid.append(available,missing);wrap.append(grid);
  const next=node('section',undefined,'insight-next');
  next.append(node('h3',read.question));
  const choices=read.topic==='staffing_decision'?['Reduce staffing costs','Performance','Attendance']:read.topic==='costs'?['Compare all employees hourly rates','Who works the most in the selected week?']:['What can you compare?','Show employees'];
  const buttons=node('div',undefined,'insight-actions');
  for(const prompt of choices)buttons.append(btt(prompt,()=>askFromCenter(prompt),'quiet'));
  next.append(buttons);wrap.append(next);
};

const insightWeekBase=renderWeek;
renderWeek=function(){
  insightWeekBase();
  const board=$('week-board');
  board.classList.remove('depth');
  board.classList.add('week-date-selector');
  board.querySelectorAll('.day-bars').forEach(el=>el.remove());
  let stage=$('week-volume-stage');
  if(!stage){stage=node('div',undefined,'week-volume-stage');stage.id='week-volume-stage';board.before(stage);}
  stage.hidden=board.hidden;
  if(board.hidden)return;
  const days=displayedDays();
  const saved=days.filter(d=>d.plan);
  if(!saved.length){stage.replaceChildren();stage.hidden=true;return;}
  ShiftBriefCharts.renderDimensionalBars(stage,{
    label:'Your week in planned hours',
    itemName:'day',
    rows:saved.map(d=>({id:d.date,name:new Date(d.date+'T12:00:00').toLocaleDateString('en-US',{weekday:'short',day:'numeric'}),value:(d.coverage||calcCoverage(d.plan)).scheduled_work_minutes/60,label:hours((d.coverage||calcCoverage(d.plan)).scheduled_work_minutes)+' h'})),
    onSelect:async day=>{await act(async()=>{planningCenter=null;dayShiftPage=0;await api('staff/day',{date:day});await refresh();});}
  });
  const button=$('chart-mode');
  button.hidden=true;
};
const insightStaffingBase=renderStaffing;
renderStaffing=function(){
  if(employerInsightRead && employerInsightRead.team_id!==state.current_production)employerInsightRead=null;
  insightStaffingBase();
  if(employerInsightRead && $('screen-comparison').classList.contains('active'))renderComparison();
};
$('chat-message').placeholder='Ask about your team or tell Sarah what changed…';
