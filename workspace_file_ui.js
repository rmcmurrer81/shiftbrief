'use strict';
let workspaceRestorePending=null,workspaceFileBusy=false;
async function workspaceRequest(action,payload){
  if(!token)await refresh();
  const response=await fetch('/api/workspace-file/'+action,{method:'POST',headers:{'Content-Type':'application/json','X-ShiftBrief-Token':token},body:JSON.stringify(payload)});
  const result=await response.json();if(!response.ok){const error=Error(result.error||'Workspace file request failed.');error.definitive=response.status===400;throw error;}return result;
}
function workspaceSummary(value){return value.teams+' businesses · '+value.employees+' employees · '+value.documents+' documents / '+value.document_revisions+' revisions · '+value.chat_messages+' conversation messages · '+value.schedule_revisions+' schedule revisions';}
function workspaceDraftGuard(){
  teamFileDraftGuard();
  if($('chat-message').value.trim()||document.querySelector('dialog:has(#work-entry-date)'))throw Error('Finish your unsaved message or work entry before restoring. Your draft is still here.');
  if(teamFileBusy||teamFilePending)throw Error('Finish the current team-file action before restoring.');
}
async function fullWorkspaceBackup(){
  if(workspaceFileBusy)throw Error('Wait for the current workspace-file action.');
  const copy=await workspaceRequest('export',{});teamFileDownload(copy.filename,copy.text);
  const {body}=modal('Complete backup prepared');body.append(node('p',workspaceSummary(copy.summary)),node('p','The downloaded .shiftbrief-workspace.json file contains all saved businesses, completed work, schedules, pay history, contacts, documents and their extracted revisions, handoffs and Sarah conversations.'),node('p','On another computer, open ShiftBrief and choose Restore backup from previous computer. Original external files and the app itself are separate.','muted'));
}
async function previewWorkspaceFile(file){
  if(!file)return;workspaceDraftGuard();
  if(workspaceRestorePending)throw Error('Resolve the pending restore before choosing another backup.');
  if(file.size>64000000)throw Error('Choose a workspace backup no larger than 64 MB.');
  const text=await file.text(),preview=await workspaceRequest('preview',{text}),{d,body}=modal('Restore all saved work');
  body.append(node('h3',file.name),node('p',workspaceSummary(preview.summary)),node('p','This restores the complete workspace and replaces the saved businesses on this computer. ShiftBrief will save a complete backup of the current workspace before replacing it.'),node('p','Current workspace: '+workspaceSummary(preview.current_summary),'muted'),node('p',preview.linked_files_disabled?'Linked document files will stay off until you choose their paths again on this computer.':'Your saved conversations, rates, schedules, completed work and document history will be restored.'));
  const resultText=node('p');resultText.setAttribute('role','status');
  const restore=btt('Restore all data',async()=>{
    if(workspaceFileBusy)return;workspaceDraftGuard();
    if(!workspaceRestorePending)workspaceRestorePending={text,expected_backup_sha256:preview.backup_sha256,expected_workspace_sha256:preview.expected_workspace_sha256,request_id:crypto.randomUUID().replaceAll('-',''),confirm_replace:true};
    workspaceFileBusy=true;restore.disabled=true;const surfaces=[document.querySelector('header'),document.querySelector('main')],prior=surfaces.map(e=>e.inert);surfaces.forEach(e=>e.inert=true);
    try{
      const result=await workspaceRequest('restore',workspaceRestorePending);workspaceRestorePending=null;
      const message=result.current_matches_restored?'All saved work restored. Your previous workspace was backed up automatically.':'That restore already completed. Your later saved changes have been preserved.';
      sessionStorage.setItem('shiftbrief-restored-notice',message);location.reload();
    }catch(error){
      if(error.definitive){workspaceRestorePending=null;restore.disabled=true;resultText.textContent=error.message+' Close this window and preview the file again.';}
      else{restore.textContent='Check this restore again';resultText.textContent='The response was interrupted. Check the same restore to find whether it completed. '+error.message;}
    }finally{workspaceFileBusy=false;surfaces.forEach((e,i)=>e.inert=prior[i]);if(workspaceRestorePending)restore.disabled=false;}
  },'primary');body.append(restore,resultText);
  d.addEventListener('cancel',e=>{if(workspaceFileBusy||workspaceRestorePending)e.preventDefault();});
  const close=d.querySelector('.dialog-head button');close.onclick=()=>{if(workspaceFileBusy||workspaceRestorePending){resultText.textContent='Check the pending restore before closing this window.';return;}d.close();};
}
const workspaceControls=document.querySelector('.team-file-controls');
const workspaceInput=node('input');workspaceInput.type='file';workspaceInput.accept='.shiftbrief-workspace.json,.json';workspaceInput.hidden=true;workspaceInput.id='workspace-restore-input';workspaceInput.onchange=()=>{const file=workspaceInput.files[0];workspaceInput.value='';act(()=>previewWorkspaceFile(file));};document.body.append(workspaceInput);
const backupButton=btt('Back up all businesses',fullWorkspaceBackup,'quiet');backupButton.id='workspace-backup';
const restoreButton=btt('Restore backup from previous computer…',()=>{workspaceDraftGuard();workspaceInput.click();},'quiet');restoreButton.id='workspace-restore';workspaceControls.append(backupButton,restoreButton);
const restoredNotice=sessionStorage.getItem('shiftbrief-restored-notice');if(restoredNotice){sessionStorage.removeItem('shiftbrief-restored-notice');setTimeout(()=>status(restoredNotice),500);}
