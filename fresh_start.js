'use strict';
// Opening the app changes presentation only. Saved work and messages stay intact.
const freshTeams=new Map();
let freshInitialized=false,freshHistory=false;
const freshHome=node('section',undefined,'desk-screen fresh-home');
freshHome.id='screen-welcome';
document.querySelector('.desk-center').append(freshHome);
const homeNav=btt('⌂  Home',()=>showScreen('welcome'),'nav-item');
homeNav.dataset.screen='welcome';
document.querySelector('.desk-nav').prepend(homeNav);
const freshNavBase=showScreen;
showScreen=function(name){freshNavBase(name);document.body.classList.toggle('fresh-start',name==='welcome');if(name==='welcome'){$('screen-title').textContent='What shall we work on today?';renderFreshHome();}};
function freshTeam(){
 const team=state.current_production;
 if(!freshTeams.has(team))freshTeams.set(team,{floor:state.assistant?.messages?.length||0,initialForm:JSON.stringify(state.assistant?.staffing_form||null)});
 return freshTeams.get(team);
}
function renderFreshHome(){
 if(!state.staffing)return;
 const selected=state.productions.find(p=>p.id===state.current_production),f=state.staffing;
 freshHome.replaceChildren();
 const hero=node('div',undefined,'fresh-hero');
 hero.append(node('span','YOUR WORKSPACE, READY WHEN YOU ARE','eyebrow'),node('h2','A fresh start. Your work is here.'),node('p','Create a blank business, load a saved business, restore a complete backup, or choose the fictional demo.'));
 const actions=node('div',undefined,'fresh-actions');
 actions.append(btt('Create a business',teamFileNew,'quiet'),btt('Load saved business…',()=>$('team-file-open').click(),'quiet'),btt('Restore backup from previous computer…',()=>$('workspace-restore').click(),'quiet'),btt('Load demo',teamFileExample,'quiet'));
 hero.append(actions);freshHome.append(hero);
 const saved=node('article',undefined,'fresh-saved');
 saved.append(node('span','SAVED ON THIS COMPUTER','eyebrow'),node('h3',selected?.title||'Your team'),node('p',(f.employees?.length||0)+' employees · Week of '+f.selected_week),btt('Open this team',()=>{planningCenter=null;showScreen('schedule');},'primary'),node('small','Choose another saved team from the Team menu above.'));
 const update=node('article',undefined,'fresh-update');
 update.append(node('span','UPDATED SEPTEMBER 8','eyebrow'),node('h3','Answers that change your workspace'),node('p','Larger 3D charts and focused views for attendance questions, staffing costs, hourly rates and time on the team.'),node('p','The example has saved planned shifts. Actual attendance and performance records are still needed for those comparisons.'));
 const grid=node('div',undefined,'fresh-grid');grid.append(saved,update);freshHome.append(grid);
}
const freshStaffingBase=renderStaffing;
renderStaffing=function(){
 if(!state.staffing)return;
 const session=freshTeam();
 if(!freshInitialized){freshInitialized=true;deskScreen='welcome';planningCenter=null;planningHydrated=true;document.querySelectorAll('.desk-screen').forEach(el=>el.classList.toggle('active',el===freshHome));document.querySelectorAll('.nav-item').forEach(el=>el.classList.toggle('active',el===homeNav));document.body.classList.add('fresh-start');$('screen-title').textContent='What shall we work on today?';}
 const assistant=state.assistant;
 // An explicit new form request may legitimately reproduce the saved form.
 const newFormRequested=(assistant?.messages||[]).slice(session.floor).some(m=>m.role==='assistant'&&m.kind==='employee_form');
 const suppress=!freshHistory&&!newFormRequested&&JSON.stringify(assistant?.staffing_form||null)===session.initialForm;
 if(suppress&&assistant)state.assistant={...assistant,staffing_form:null};
 try{freshStaffingBase();}finally{state.assistant=assistant;}
 if(deskScreen==='welcome')renderFreshHome();
};
const freshConversationBase=renderConversation;
renderConversation=function(){
 if(!state.current_production)return;
 const session=freshTeam(),assistant=state.assistant||{},all=assistant.messages||[];
 state.assistant={...assistant,messages:freshHistory?all:all.slice(session.floor)};
 try{freshConversationBase();}finally{state.assistant=assistant;}
 if(!freshHistory&&all.length===session.floor){
  const wrap=$('conversation');wrap.replaceChildren();
  const hello=node('div',undefined,'chat-message assistant');
  hello.append(node('strong','Sarah'),node('p','What would you like to work on today? Create a business, load saved work, or ask me a question. The fictional demo loads only when you choose Load demo.'));
  if(assistant.pending||assistant.staffing_form)hello.append(node('p','You also have an unfinished change saved. Open conversation history to review it.'));
  wrap.append(hello);$('chat-pages').replaceChildren();
 }
 let controls=$('fresh-chat-controls');
 if(!controls){controls=node('div',undefined,'fresh-chat-controls');controls.id='fresh-chat-controls';$('conversation').before(controls);}
 controls.replaceChildren();
 if(all.length)controls.append(btt(freshHistory?'Back to this session':'Conversation history',()=>{freshHistory=!freshHistory;questionChatSignature='';questionChatRenderKey='';renderConversation();if(freshHistory)renderStaffing();},'quiet'));
};
// A restored browser tab must also show the new welcome state after back/forward cache.
addEventListener('pageshow',event=>{if(event.persisted){freshInitialized=false;freshHistory=false;freshTeams.clear();refresh().catch(e=>status(e.message));}});
