'use strict';
// Presentation only. Saved staffing data, draft controls and existing chart renderers stay owned by their original modules.
(() => {
  if (document.body.classList.contains('workspace-design')) return;
  document.body.classList.add('workspace-design');
  const el = (tag, text, cls) => node(tag, text, cls);
  const dateLabel = (value, options = {month:'short', day:'numeric'}) => {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(value || '')) return 'Choose a date';
    return new Date(value + 'T12:00:00').toLocaleDateString('en-US', options);
  };
  const duration = value => Number.isFinite(value) ? new Intl.NumberFormat('en-US', {maximumFractionDigits:1}).format(value / 60) : '—';
  const time = value => Number.isFinite(value) ? ampm(value) : 'Not recorded';
  const minutes = plan => plan && Array.isArray(plan.shifts)
    ? plan.shifts.reduce((sum, shift) => sum + shift.end - shift.start - (shift.breaks || []).reduce((n, b) => n + b.end - b.start, 0), 0)
    : null;
  const button = (text, fn, cls = 'wd-text-action') => btt(text, fn, cls);
  const selected = () => {
    const f = state.staffing || {}, days = f.days || [];
    const date = days.some(d => d.date === f.selected_date) ? f.selected_date : f.selected_week;
    return {f, days, date, row:days.find(d => d.date === date), team:state.productions?.find(p => p.id === state.current_production)};
  };
  const teamGuard = id => { if (state.current_production !== id) throw Error('The team changed. Choose the date again in the current team.'); };
  async function openDate(date, team, week, screen = 'welcome') {
    teamGuard(team);
    if (state.staffing?.selected_week !== week || !state.staffing.days?.some(d => d.date === date)) throw Error('The selected week changed. Choose a date in the current week.');
    await api('staff/day', {date});
    await refresh();
    teamGuard(team);
    if (state.staffing?.selected_week !== week) return;
    if (screen === 'schedule') { planningCenter = null; dayShiftPage = 0; }
    showScreen(screen);
  }
  function draftQuestion(text) {
    const input = $('chat-message');
    if (input.value.trim()) {
      status('Your message is still in the conversation box. Send it or clear it before choosing another question.');
    } else input.value = text;
    if (innerWidth < 1000) showScreen('chat');
    input.focus();
  }
  function metric(label, value, detail) {
    const row = el('div', undefined, 'wd-measure');
    row.append(el('span', label), el('strong', value), el('small', detail));
    return row;
  }
  function homeTimeline(wrap, row) {
    const plan = row?.plan;
    if (!plan) {
      const empty = el('div', undefined, 'wd-empty');
      empty.append(el('span', 'NO SAVED PLAN', 'wd-kicker'), el('h3', 'Make room for a well-planned day.'),
        el('p', 'This date has no saved shifts. Open Schedule to review availability and create a plan.'),
        button('Open Schedule →', () => showScreen('schedule'), 'primary'));
      wrap.append(empty); return;
    }
    if (!plan.shifts.length) {
      wrap.append(el('p', 'This date is saved with no planned shifts.', 'wd-empty')); return;
    }
    const shifts = [...plan.shifts].sort((a,b) => a.start - b.start || a.employee.localeCompare(b.employee));
    const start = Math.floor(Math.min(plan.open, ...shifts.map(s => s.start)) / 60) * 60;
    const end = Math.ceil(Math.max(plan.close, ...shifts.map(s => s.end)) / 60) * 60;
    const span = Math.max(60, end - start);
    const table = el('div', undefined, 'wd-timeline');
    table.setAttribute('role', 'table'); table.setAttribute('aria-label', 'Saved planned shifts for ' + row.date);
    const head = el('div', undefined, 'wd-timeline-head'); head.setAttribute('role', 'row');
    head.append(el('span', 'EMPLOYEE / ROLE', 'wd-kicker'));
    const ticks = el('div', undefined, 'wd-time-axis');
    for (let i=0; i<5; i++) { const tick=el('span',time(start + Math.round(span*i/4))); tick.style.left=(i*25)+'%'; ticks.append(tick); }
    head.append(ticks, el('span', 'PLANNED', 'wd-kicker')); table.append(head);
    shifts.forEach((shift, index) => {
      const line = el('div', undefined, 'wd-timeline-row'); line.setAttribute('role','row');
      const person = el('div', undefined, 'wd-shift-person'); person.setAttribute('role','cell');
      person.append(el('span', String(index+1).padStart(2,'0'), 'wd-row-number'));
      const name = el('div'); name.append(el('strong', shift.employee), el('small', shift.role || 'Team')); person.append(name);
      const track = el('div', undefined, 'wd-shift-track'); track.setAttribute('role','cell');
      track.setAttribute('aria-label', time(shift.start)+' to '+time(shift.end)+', '+(shift.breaks?.length || 0)+' recorded breaks');
      const bar = el('div', undefined, 'wd-shift-bar'); bar.style.left=((shift.start-start)/span*100)+'%'; bar.style.width=((shift.end-shift.start)/span*100)+'%';
      bar.style.setProperty('--wd-shift-color',['#79dbd4','#a6a3fa','#edbc77','#77b7f5'][index%4]);
      bar.append(el('span', time(shift.start)+' – '+time(shift.end)));
      for (const rest of shift.breaks || []) {
        const gap = el('i', undefined, 'wd-shift-break'); gap.style.left=((rest.start-shift.start)/(shift.end-shift.start)*100)+'%'; gap.style.width=((rest.end-rest.start)/(shift.end-shift.start)*100)+'%'; gap.title='Recorded break · '+time(rest.start)+'–'+time(rest.end); bar.append(gap);
      }
      track.append(bar);
      const value=el('strong',duration(shift.end-shift.start-(shift.breaks||[]).reduce((n,b)=>n+b.end-b.start,0))+' h','wd-shift-total'); value.setAttribute('role','cell');
      line.append(person,track,value); table.append(line);
    });
    wrap.append(table, el('p','Saved planned shifts · hatched sections are recorded breaks · hours exclude breaks','wd-footnote'));
  }
  renderFreshHome = function() {
    if (!state.staffing) return;
    const {f,days,date,row,team} = selected(), teamID = state.current_production, week = f.selected_week;
    const saved = days.filter(d=>d.plan), total = saved.reduce((sum,d)=>sum+minutes(d.plan),0);
    freshHome.replaceChildren();
    const mast = el('div',undefined,'wd-home-mast');
    const title = el('div');
    const empty = state.workspace_setup?.empty_business === true;
    const demo = state.workspace_setup?.fictional_demo === true;
    title.append(el('span',demo?'FICTIONAL DEMO · INVENTED PEOPLE AND RECORDS':'BUSINESS WORKSPACE',demo?'wd-kicker wd-demo-label':'wd-kicker'),el('h2',team?.title || 'Your business'),el('p',empty?'Start with your own business. No demo records have been loaded.':'Your people. The week ahead. The details behind it.'));
    const open = button('Open Schedule ↗',()=>showScreen('schedule'),'primary');
    mast.append(title,open); freshHome.append(mast);
    const fileActions=el('section',undefined,'wd-business-actions');
    fileActions.setAttribute('aria-label','Business setup and saved files');
    fileActions.append(button('Create a business',teamFileNew,'quiet'),
      button('Load saved business…',()=>$('team-file-open').click(),'quiet'),
      button('Restore backup from previous computer…',()=>$('workspace-restore').click(),'quiet'),
      button('Load demo',teamFileExample,'quiet'));
    freshHome.append(fileActions);
    if(empty){
      const start=el('section',undefined,'wd-chart-empty');
      start.append(el('span','BLANK BUSINESS','wd-kicker'),el('h3','Ready for your first employee.'),
        el('p','Create a business with its own name, or add employees to this blank business. You can also load a saved business file or restore a complete backup.'),
        button('Add first employee',()=>{showScreen('people');openEmployee();},'primary'),
        el('p','Changes save on this computer. Use Save business copy for one business, or Back up all businesses to move all saved work to another computer.','wd-footnote'));
      freshHome.append(start);return;
    }
    const overview = el('section',undefined,'wd-week-overview'); overview.setAttribute('aria-label','Selected saved week');
    const heading=el('div',undefined,'wd-section-heading');
    const dates=el('div'); dates.append(el('span','SELECTED WEEK','wd-kicker'),el('h3',dateLabel(week)+' — '+dateLabel(days.at(-1)?.date || week, {month:'short',day:'numeric',year:'numeric'})));
    heading.append(dates,button('Change week →',()=>{showScreen('schedule');$('week-start').focus();})); overview.append(heading);
    const numbers=el('div',undefined,'wd-measures');
    numbers.append(metric('Saved planned hours',saved.length?duration(total)+' h':'—',saved.length?`${saved.length} of ${days.length} dates have a saved plan`:'No saved plans in this week'),
      metric('Employees',String((f.employees||[]).length),'Saved roster · includes former and future staff'),
      metric('Selected date',dateLabel(date,{weekday:'short',day:'numeric'}),row?.plan?'Saved revision '+row.plan.number:'No saved plan'));
    const overviewBody=el('div',undefined,'wd-overview-body');
    if(saved.length && window.ShiftBriefCharts) {
      const chart=el('div',undefined,'wd-home-chart');
      chart.id='workspace-week-chart';
      ShiftBriefCharts.renderDimensionalBars(chart,{
        label:'Saved planned hours by day',itemName:'day',
        rows:saved.map(d=>({id:d.date,name:dateLabel(d.date,{weekday:'short',day:'numeric'}),value:minutes(d.plan)/60,label:duration(minutes(d.plan))+' h'})),
        onSelect:day=>act(()=>openDate(day,teamID,week))
      });
      overviewBody.append(chart);
    } else {
      const noChart=el('div',undefined,'wd-chart-empty');
      noChart.append(el('span','NO SAVED SHIFTS','wd-kicker'),el('h3','Your week is ready to plan.'),el('p','Choose a date or open Schedule to begin. A chart appears when this week has saved shifts.'));
      overviewBody.append(noChart);
    }
    overviewBody.append(numbers); overview.append(overviewBody);
    const strip=el('div',undefined,'wd-week-strip'); strip.setAttribute('aria-label','Select a saved date');
    for (const day of days) {
      const dayButton=button('',()=>openDate(day.date,teamID,week),'wd-day'+(day.date===date?' is-selected':''));
      dayButton.setAttribute('aria-label',dateLabel(day.date,{weekday:'long',month:'long',day:'numeric'})+(day.plan?', '+duration(minutes(day.plan))+' planned hours':', no saved plan'));
      dayButton.setAttribute('aria-pressed',String(day.date===date)); dayButton.dataset.date=day.date;
      dayButton.append(el('span',dateLabel(day.date,{weekday:'short'})),el('strong',dateLabel(day.date,{day:'numeric'})),el('small',day.plan?duration(minutes(day.plan))+' h':'Unscheduled'));
      strip.append(dayButton);
    }
    overview.append(strip); freshHome.append(overview);
    const day=el('section',undefined,'wd-day-work');
    const dayHeading=el('div',undefined,'wd-section-heading'),dayTitle=el('div');
    dayTitle.append(el('span','DAY PLAN','wd-kicker'),el('h3',dateLabel(date,{weekday:'long',month:'long',day:'numeric'})));
    dayHeading.append(dayTitle,button('Review this date →',()=>openDate(date,teamID,week,'schedule'))); day.append(dayHeading);
    homeTimeline(day,row); freshHome.append(day);
    const bottom=el('section',undefined,'wd-explore');
    const heading2=el('div'); heading2.append(el('span','GO DEEPER','wd-kicker'),el('h3','Ask a better question. See the whole picture.'));
    bottom.append(heading2);
    const questions=el('div',undefined,'wd-question-links');
    for (const [label, detail, prompt] of [
      ['Hours by employee','Compare this saved week','Who works the most in the week of '+week+'?'],
      ['Pay & raises','Read the recorded pay history','When was each person’s last raise?'],
      ['Dated availability','Use the selected date','Who is available on '+date+'?']
    ]) {
      const b=button('',()=>draftQuestion(prompt),'wd-question-link'); b.append(el('strong',label+' ↗'),el('small',detail)); questions.append(b);
    }
    bottom.append(questions,el('p','Choose a question to draft it for Sarah. Your unsent message stays intact.','wd-footnote')); freshHome.append(bottom);
  };
  // Existing controls are retained as the same nodes with the same listeners.
  const context=el('div',undefined,'wd-context'); context.id='workspace-context'; context.setAttribute('aria-label','Workspace context');
  document.querySelector('.desk-title').after(context);
  const titleMap={welcome:'Overview',schedule:'Schedule',people:'Employees',contacts:'Contacts',hours:'Planned hours',requests:'Requests',history:'History',sources:'Sources',handoff:'Handoffs',settings:'Settings',pay:'Pay & raises',availability:'Availability',comparison:'Team insight',import:'Import employees',chat:'Conversation'};
  const navIcons={welcome:'⌂',schedule:'▦',people:'◉',contacts:'@',hours:'▥',requests:'≋',history:'↶',sources:'▤',handoff:'↗',settings:'⚙',chat:'↳'};
  for (const nav of document.querySelectorAll('.desk-nav .nav-item')) {
    const key=nav.dataset.screen;
    if (!titleMap[key]) continue;
    const label=el('span',titleMap[key]),icon=el('span',navIcons[key] || '·','wd-nav-icon'); icon.setAttribute('aria-hidden','true');
    nav.replaceChildren(icon,label); nav.title=titleMap[key];
  }
  const nav=document.querySelector('.desk-nav');
  const group=el('span','WORKSPACE','wd-nav-label');nav.prepend(group);
  const sources=nav.querySelector('[data-screen="sources"]');if(sources)sources.before(el('span','RECORDS & TOOLS','wd-nav-label'));
  const sarahHead=document.querySelector('.sarah-heading');
  if (sarahHead) { const h=sarahHead.querySelector('h2');if(h)h.textContent='A clearer conversation.'; }
  const input=$('chat-message');input.setAttribute('aria-label','Message Sarah');
  const compose=document.querySelector('.chat-compose');
  const composeNote=el('small','Your question opens the relevant records beside this conversation.','wd-compose-note');compose.append(composeNote);
  const chatContext=el('div',undefined,'wd-chat-context');chatContext.id='workspace-chat-context';
  if (sarahHead) sarahHead.after(chatContext);
  function updateContext() {
    if (!state.staffing) return;
    const {team,date}=selected();
    context.replaceChildren(el('span',team?.title||'Your team'),el('span','/','wd-context-divider'),el('strong',titleMap[deskScreen]||'Team records'));
    if(deskScreen!=='comparison')context.append(el('small','Schedule date: '+dateLabel(date,{month:'short',day:'numeric',year:'numeric'})));
    chatContext.replaceChildren(el('span','WORKING WITH','wd-kicker'),el('strong',team?.title||'Your team'));
    document.body.dataset.workspaceScreen=deskScreen;
    if(deskScreen==='welcome')$('screen-title').textContent='Your team, in focus.';
    document.querySelectorAll('.desk-nav .nav-item').forEach(n=>{if(n.dataset.screen===deskScreen)n.setAttribute('aria-current','page');else n.removeAttribute('aria-current');});
  }
  const viewBase=showScreen;
  showScreen=function(name){viewBase(name);updateContext();};
  const staffingBase=renderStaffing;
  renderStaffing=function(){staffingBase();updateContext();};
  updateContext();
  if (state.staffing && deskScreen==='welcome') renderFreshHome();
})();
