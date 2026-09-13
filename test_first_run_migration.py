import copy,hashlib,json,sys,tempfile,threading,unittest,uuid
from pathlib import Path
from urllib.request import Request,urlopen
ROOT=Path(__file__).resolve().parent
APP=ROOT/'app' if (ROOT/'app/server.py').exists() else ROOT
sys.path.insert(0,str(APP))
import briefing,staffing,server,team_file,workspace_file

DEMO=(APP/'Maple-Street-Fictional-Jun-Sep-2026.shiftbrief.json').read_text('utf-8')

class BusinessStartTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
  self.store=briefing.Store(Path(self.tmp.name)/'fresh')
 def demo(self,store=None):
  store=store or self.store
  return team_file.open_team(store,DEMO,store.production_id,str(uuid.uuid4()))
 def test_fresh_start_is_blank_and_does_not_fetch_or_load_demo(self):
  app=server.App(Path(self.tmp.name)/'new-install');view=app.store.view()
  self.assertEqual('Your business',view['productions'][0]['title'])
  self.assertEqual({'empty_business':True,'fictional_demo':False},view['workspace_setup'])
  self.assertEqual([],view['staffing']['employees']);self.assertEqual([],view['documents'])
  self.assertTrue(all(not d['plan'] for d in view['staffing']['days']))
  self.assertEqual([],view['assistant']['messages']);self.assertEqual(1,len(view['productions']))
 def test_existing_demo_survives_reopen_byte_for_byte(self):
  opened=self.demo();file=self.store.path/'state.json';before=file.read_bytes()
  app=server.App(self.store.path);view=app.store.view()
  self.assertEqual(opened['team_id'],view['current_production']);self.assertTrue(view['workspace_setup']['fictional_demo'])
  self.assertEqual(8,len(view['staffing']['employees']));self.assertFalse(view['workspace_setup']['empty_business'])
  self.assertEqual(before,file.read_bytes())
 def test_new_business_and_explicit_demo_preserve_existing_business(self):
  opened=team_file.new_team(self.store,'Owner-created blank business',self.store.production_id,'new-business')
  before=copy.deepcopy(self.store.data);self.demo()
  self.assertEqual(before['productions'],self.store.data['productions'][:-1])
  for section in ('staffing','shift_schedules'):
   self.assertEqual(before[section][opened['team_id']],self.store.data[section][opened['team_id']])
 def test_empty_hint_checks_all_dates_and_saved_conversation(self):
  self.assertTrue(self.store.view()['workspace_setup']['empty_business'])
  self.store.data.setdefault('assistant_threads',{})[self.store.production_id]={'messages':[{'role':'user','text':'Saved work'}]}
  self.assertFalse(self.store.view()['workspace_setup']['empty_business'])
  self.store.data['assistant_threads'].clear()
  self.store.data.setdefault('shift_schedules',{})[self.store.production_id]={'days':{'2020-01-01':{'revisions':[]}},'selected_date':'2026-09-13'}
  self.assertFalse(self.store.view()['workspace_setup']['empty_business'])
 def test_portable_business_roundtrip_keeps_records_additive(self):
  self.demo();before=(self.store.path/'state.json').read_bytes()
  exported=team_file.export_team(self.store,self.store.production_id)
  target=briefing.Store(Path(self.tmp.name)/'other-computer');original=copy.deepcopy(target.data)
  loaded=team_file.open_team(target,exported['text'],target.production_id,'load-copy')
  reexport=team_file.export_team(target,loaded['team_id'])
  a=json.loads(exported['text']);b=json.loads(reexport['text'])
  for key in ('team','staffing','schedules','work_records','schema','includes','excludes'):
   self.assertEqual(a[key],b[key],key)
  self.assertEqual(original['productions'][0],target.data['productions'][0])
  self.assertEqual(before,(self.store.path/'state.json').read_bytes())
 def test_restore_preview_and_atomic_roundtrip_preserve_before_backup(self):
  self.demo();pid=self.store.production_id
  self.store.import_document('Fixture note','note.txt',b'Old revision')
  document=self.store.data['documents'][0]
  self.store.import_document('','note.txt',b'Updated revision',document['id'])
  self.store.data.setdefault('assistant_threads',{})[pid]={'messages':[{'role':'user','text':'Fixture saved conversation'}],'pending':None};self.store.save()
  exported=workspace_file.export_workspace(self.store)
  target=briefing.Store(Path(self.tmp.name)/'migration-target');target.save();old=copy.deepcopy(target.data)
  preview=workspace_file.preview_workspace(target,exported['text']);self.assertEqual(old,target.data)
  request={'text':exported['text'],'expected_backup_sha256':preview['backup_sha256'],'expected_workspace_sha256':preview['expected_workspace_sha256'],'request_id':uuid.uuid4().hex,'confirm_replace':True}
  result=workspace_file.restore_workspace(target,request)
  self.assertTrue(result['current_matches_restored']);self.assertEqual(self.store.data,target.data)
  backup=(target.path/'workspace-restores'/result['before_backup']['filename']).read_text('utf-8')
  self.assertEqual(old,workspace_file.decode(backup)[0]['data'])
  self.assertEqual(target.data,briefing.Store(target.path).data)
  target.data['productions'][0]['title']='Later edit';target.save()
  replay=workspace_file.restore_workspace(target,request)
  self.assertTrue(replay['replayed']);self.assertFalse(replay['current_matches_restored'])
  self.assertEqual('Later edit',target.data['productions'][0]['title'])
 def test_corrupted_backup_does_not_change_current_business(self):
  self.store.save();before=(self.store.path/'state.json').read_bytes()
  exported=workspace_file.export_workspace(self.store);value=json.loads(exported['text']);value['data']['productions'][0]['title']='Corrupted'
  with self.assertRaises(ValueError):workspace_file.preview_workspace(self.store,json.dumps(value))
  self.assertEqual(before,(self.store.path/'state.json').read_bytes())
 def test_normal_http_first_run_business_copy_and_migration(self):
  srv=server.make_server(Path(self.tmp.name)/'http',0)
  self.addCleanup(srv.server_close);self.addCleanup(srv.shutdown)
  thread=threading.Thread(target=srv.serve_forever,daemon=True);thread.start()
  base='http://127.0.0.1:'+str(srv.server_port)
  def call(path,body=None):
   req=Request(base+'/api/'+path,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-ShiftBrief-Token':srv.app.token})
   with urlopen(req,timeout=10) as r:return json.load(r)
  initial=call('state');self.assertTrue(initial['state']['workspace_setup']['empty_business'])
  loaded=call('team-file/open',{'text':DEMO,'expected_team_id':'main','request_id':'http-demo'})
  exported=call('team-file/export',{'expected_team_id':loaded['team_id']});self.assertEqual(8,exported['summary']['employees'])
  full=call('workspace-file/export',{});preview=call('workspace-file/preview',{'text':full['text']})
  restored=call('workspace-file/restore',{'text':full['text'],'expected_backup_sha256':preview['backup_sha256'],'expected_workspace_sha256':preview['expected_workspace_sha256'],'request_id':uuid.uuid4().hex,'confirm_replace':True})
  self.assertTrue(restored['current_matches_restored']);self.assertEqual(8,len(call('state')['state']['staffing']['employees']))

if __name__=='__main__':unittest.main(verbosity=2)
