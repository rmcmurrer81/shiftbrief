from __future__ import annotations
import argparse, base64, json, secrets, threading, time, webbrowser
from copy import deepcopy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from briefing import Store, load_sample, update_packet
from agent import run_agent, runtime_settings
from sarah_local import run_local, ask as ask_sarah, confirm as confirm_sarah, LABEL

from voice_bridge import AppVoice
import staffing
import employee_pay, employee_import, team_file, work_history, workspace_file, general_chat
from staffing_agent import run_staffing_agent
import shift_schedule
import operating_hours

class App:
    def __init__(self, state_dir):
        self.store = Store(state_dir)
        self.voice = AppVoice(Path(__file__).parent, 'shiftbrief')
        self.jobs = {}
        self.token = secrets.token_urlsafe(24)
        self.job_lock = threading.Lock()
        workspace_file.install_app(self)
        self.general_chat = general_chat.GeneralChat(self)

    def team_file_action(self, operation, payload):
        # Keep the native job -> Store lock order. The helper owns exact replay
        # recovery, including replay after the user has selected another team.
        with self.job_lock:
            if operation in ('new', 'open') and any(
                job.get('status') == 'running' for job in self.jobs.values()
            ):
                raise ValueError('Let the current handoff finish before opening a team.')
            expected_team_id = payload.get('expected_team_id')
            if operation == 'export':
                return team_file.export_team(self.store, expected_team_id)
            if operation == 'new':
                return team_file.new_team(self.store, payload.get('title'), expected_team_id, payload.get('request_id'))
            if operation == 'open':
                return team_file.open_team(self.store, payload.get('text'), expected_team_id, payload.get('request_id'))
            raise ValueError('Unknown team file action.')

    @staticmethod
    def staffing_ai_available():
        from agent_provider import configured
        return configured() and __import__('importlib.util',fromlist=['find_spec']).find_spec('strands') is not None

    def _new_staffing_job(self, payload):
        # Caller holds job_lock then store.lock, as in ordinary planning.
        if payload.get('production_id') != self.store.production_id:
            raise ValueError('The selected team changed. Reopen the current team before planning.')
        week=staffing.week_start(payload.get('week_start'))
        if week!=staffing.book(self.store)['selected_week']:
            raise ValueError('Choose the saved selected week before planning.')
        if any(x['status']=='running' for x in self.jobs.values()):
            raise ValueError('A local agent is already working. Wait for it to finish.')
        job={'id':secrets.token_hex(6),'kind':'staffing_agent','production_id':self.store.production_id,
             'week_start':week,'status':'running','trace':[],'started':time.time()}
        self.jobs[job['id']]=job
        return job

    def _save_chat_checked(self, before):
        try:
            self.store.save()
            if json.loads((self.store.path/'state.json').read_text(encoding='utf-8'))!=self.store.data:
                raise OSError('The conversation update was not durably saved. Reopen the saved team before retrying.')
        except Exception:
            self.store.data=before
            raise

    def _finish_staffing_chat(self, job, result):
        if not job.get('from_conversation'):return
        with self.store.lock:
            thread=self.store.data.get('assistant_threads',{}).get(job['production_id'])
            if not thread:raise ValueError('The originating conversation is no longer available.')
            rows=[m for m in thread['messages'] if m.get('planning_job_id')==job['id']]
            if len(rows)!=1:raise ValueError('The exact planning conversation changed. Reopen its proposal.')
            before=deepcopy(self.store.data)
            rows[0].update(text=result['answer'],kind=result['kind'],planning_status='complete')
            if result.get('proposal'):
                thread['staffing_proposal_id']=result['proposal']['id']
                rows[0]['planning_proposal_id']=result['proposal']['id']
            self._save_chat_checked(before)

    def _launch_staffing_job(self, job, request):
        def work():
            try:
                with self.store.lock:
                    if self.store.production_id!=job['production_id']:
                        raise ValueError('The selected team changed before planning started.')
                result=run_staffing_agent(self.store,job['week_start'],request,
                    progress=lambda trace:job.update(trace=list(trace)))
                self._finish_staffing_chat(job,result)
                job.update(status='complete',result=result,elapsed_seconds=result['elapsed_seconds'])
            except Exception as exc:
                job.update(status='error',error=str(exc)[:700])
                try:self._finish_staffing_chat(job,{'kind':'staffing_ai_error','answer':'The local planning request did not finish: '+str(exc)[:500]+'. Check saved proposals before trying again.'})
                except Exception:pass  # The exact job still exposes its error; no claim that chat was saved.
        threading.Thread(target=work,daemon=True).start()

    def plan_staffing(self, payload):
        with self.job_lock, self.store.lock:job=self._new_staffing_job(payload)
        self._launch_staffing_job(job,payload.get('request','Plan this week using the saved team.'))
        return dict(job)

    def assistant_message(self, payload):
        mode=payload.get('conversation_mode','records')
        if mode not in ('records','ollama','bedrock'):raise ValueError('Choose Records, local AI or cloud AI for this conversation.')
        existing=self.general_chat.replay(payload)
        if existing is not None:return existing
        if mode!='records':
            with self.store.lock:
                if payload.get('production_id')!=self.store.production_id or payload.get('week_start')!=staffing.book(self.store)['selected_week']:
                    raise ValueError('The selected team/week changed. Reopen it before asking.')
                mutation,_=general_chat.preview(self.store,payload.get('message'),payload.get('briefing_id'))
            if not mutation:return self.general_chat.start(payload)
        job=None
        with self.job_lock, self.store.lock:
            if payload.get('production_id') is not None and payload['production_id']!=self.store.production_id:
                raise ValueError('The team changed before your message arrived. Reopen the current team.')
            if payload.get('week_start') is not None and payload['week_start']!=staffing.book(self.store)['selected_week']:
                raise ValueError('The selected week changed before your message arrived. Check the week and send it again.')
            old_pending=deepcopy(self.store.data.get('assistant_threads',{}).get(self.store.production_id,{}).get('pending'))
            result=ask_sarah(self.store,payload.get('message'),payload.get('briefing_id'))
            if result.get('kind')!='staffing_ai_request':
                if result.get('kind')=='staffing_rules_proposal':
                    before=deepcopy(self.store.data)
                    thread=self.store.data['assistant_threads'][self.store.production_id];row=thread['messages'][-1];thread['pending']=old_pending
                    row.update(planning_proposal_id=result['staffing_proposal']['id'],planning_status='complete',planning_week=result['staffing_proposal']['week_start'])
                    self._save_chat_checked(before)
                return result
            request=result['staffing_request'];thread=self.store.data['assistant_threads'][self.store.production_id]
            before=deepcopy(self.store.data);row=thread['messages'][-1]
            try:
                if payload.get('production_id')!=request['production_id'] or payload.get('week_start')!=request['week_start']:
                    raise ValueError('Reload the selected team/week before asking for AI planning.')
                if not self.staffing_ai_available():
                    raise ValueError('AI planning is not configured in this running edition. Your restriction request is preserved and has not been applied. Configure the optional provider to interpret it; the saved-availability planner does not apply these new instructions.')
                job=self._new_staffing_job(request);job['from_conversation']=True
                result.update(kind='staffing_ai_job',job=dict(job),answer='Sarah is checking your exact request against this team’s saved week. The proposal and any clarification will appear beside this conversation; nothing is accepted automatically.')
                row.update(planning_job_id=job['id'],planning_status='running',planning_request=request['request'],planning_week=request['week_start'])
            except ValueError as exc:
                result.update(kind='staffing_ai_unavailable',answer=str(exc))
            row.update(text=result['answer'],kind=result['kind']);thread['pending']=old_pending
            try:self._save_chat_checked(before)
            except Exception:
                if job:self.jobs.pop(job['id'],None)
                raise
        if job:self._launch_staffing_job(job,request['request'])
        return result


    def brief(self, request, mode='sarah_local'):
        if mode not in ('sarah_local','strands_ollama','strands_bedrock'):
            raise ValueError('Choose local evidence, optional local Strands/Ollama or explicitly configured cloud Strands/Bedrock.')
        with self.job_lock:
            if any(x['status'] == 'running' for x in self.jobs.values()):
                raise ValueError('A briefing is already being prepared.')
            job_id = secrets.token_hex(6)
            job = {'id': job_id, 'production_id': self.store.production_id, 'status': 'running', 'trace': [], 'started': time.time()}
            self.jobs[job_id] = job
        def work():
            try:
                result = (run_local(self.store, request, progress=lambda trace: job.update(trace=list(trace))) if mode=='sarah_local' else run_agent(self.store, request, progress=lambda trace: job.update(trace=list(trace)), provider='bedrock' if mode=='strands_bedrock' else 'ollama'))
                job.update(status='complete', briefing_id=result['id'], elapsed_seconds=result['elapsed_seconds'])
            except Exception as exc:
                job.update(status='error', error=str(exc)[:700])
        threading.Thread(target=work, daemon=True).start()
        return dict(job)


def handler(app):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass
        def safe(self, mutation=False):
            host = self.headers.get('Host', '')
            allowed = {f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'}
            if host not in allowed:
                raise ValueError('This app accepts local requests only.')
            origin = self.headers.get('Origin')
            if origin and origin not in {'http://' + x for x in allowed}:
                raise ValueError('Request origin does not match this local app.')
            if mutation and self.headers.get('X-ShiftBrief-Token') != app.token:
                raise ValueError('Reload this app before making changes.')
        def reply(self, value, status=200, content_type='application/json'):
            data = value if isinstance(value,bytes) else (json.dumps(value, ensure_ascii=False) if content_type == 'application/json' else value).encode('utf-8')
            self.send_response(status)
            self.send_header('Content-Type', content_type if isinstance(value,bytes) else content_type + '; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; media-src 'self' data:; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)
        def do_GET(self):
            try:
                self.safe()
                path = urlparse(self.path)
                if path.path == '/api/state':
                    self.reply({'app': 'ShiftBrief', 'state': {**app.store.view(), 'work_history_sha256': work_history.signature(app.store)}, 'token': app.token, 'runtime': {'mode':'sarah_local','label':LABEL,'model':'none','url':'local documents only','optional_strands_available':app.staffing_ai_available()}, 'jobs': [x for x in app.jobs.values() if x['production_id']==app.store.production_id]})
                elif path.path == '/api/assistant/general':
                    query=parse_qs(path.query)
                    self.reply(app.general_chat.status(query.get('team',[''])[0],query.get('id',[''])[0]))
                elif path.path == '/api/export':
                    self.reply(app.store.export(parse_qs(path.query).get('id', [''])[0]), content_type='text/markdown')
                elif path.path == '/api/staff/export-week':
                    self.reply(staffing.export_week(app.store,parse_qs(path.query).get('week',[staffing.book(app.store)['selected_week']])[0]),content_type='application/zip')
                elif path.path == '/api/schedule/history':
                    query=parse_qs(path.query);result=shift_schedule.view(app.store,query.get('date',[None])[0],int(query['number'][0]) if query.get('number') else None);result['coverage']=staffing.role_coverage(result['plan']);self.reply(result)
                elif path.path == '/api/schedule/export':
                    query=parse_qs(path.query);self.reply(shift_schedule.export_csv(shift_schedule.latest(app.store,query.get('date',[None])[0])),content_type='text/csv')
                elif path.path == '/api/voice/status':
                    self.reply(app.voice.status())
                elif path.path in ('/', '/app.js', '/style.css', '/sarah_voice.js', '/staffing_ui.js', '/operating_ui.js', '/source_handoff_ui.js', '/employee_workspace_ui.js', '/dimensional_charts.js', '/dimensional_charts.css', '/question_center_ui.js', '/question_center.css', '/team_file_ui.js', '/team_file.css', '/team_insights.css', '/team_insights_ui.js', '/fresh_start.js', '/work_history_ui.js', '/work_history.css', '/workspace_file_ui.js', '/workspace_design.js', '/workspace_design.css', '/general_chat_ui.js', '/Maple-Street-Fictional-Jun-Sep-2026.shiftbrief.json'):
                    name = 'index.html' if path.path == '/' else path.path[1:]
                    kind = {'index.html': 'text/html', 'app.js': 'text/javascript', 'sarah_voice.js': 'text/javascript', 'staffing_ui.js': 'text/javascript', 'operating_ui.js': 'text/javascript', 'source_handoff_ui.js': 'text/javascript', 'employee_workspace_ui.js': 'text/javascript', 'style.css': 'text/css', 'dimensional_charts.js': 'text/javascript', 'dimensional_charts.css': 'text/css', 'question_center_ui.js': 'text/javascript', 'question_center.css': 'text/css', 'team_file_ui.js': 'text/javascript', 'team_file.css': 'text/css', 'team_insights.css': 'text/css', 'team_insights_ui.js': 'text/javascript', 'fresh_start.js': 'text/javascript', 'work_history_ui.js': 'text/javascript', 'workspace_file_ui.js': 'text/javascript', 'workspace_design.js': 'text/javascript', 'workspace_design.css': 'text/css', 'general_chat_ui.js': 'text/javascript', 'work_history.css': 'text/css', 'Maple-Street-Fictional-Jun-Sep-2026.shiftbrief.json': 'application/json'}[name]
                    asset = Path(__file__).parent / name
                    content = asset.read_bytes() if kind == 'application/json' else asset.read_text('utf-8-sig')
                    self.reply(content, content_type=kind)
                else:
                    self.reply({'error': 'Not found'}, 404)
            except (ValueError, OSError) as exc:
                self.reply({'error': str(exc)}, 400)
        def do_POST(self):
            try:
                self.safe(True)
                size = int(self.headers.get('Content-Length', '0'))
                maximum = workspace_file.MAX_REQUEST_BYTES if self.path in ('/api/workspace-file/preview', '/api/workspace-file/restore') else 7_000_000
                if size <= 0 or size > maximum:
                    raise ValueError('Request too large or empty.')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload,dict): raise ValueError('Supply a JSON object.')
                if self.path in ('/api/production/create','/api/production/select'):
                    with app.job_lock:
                        if any(x['status']=='running' for x in app.jobs.values()):
                            raise ValueError('Let the current handoff finish before switching teams.')
                        if self.path.endswith('/create'):
                            result=app.store.create_production(payload['title'])
                        else:
                            app.store.select_production(payload['id'])
                            result={'selected':True}
                elif self.path in ('/api/workspace-file/export', '/api/workspace-file/preview', '/api/workspace-file/restore', '/api/workspace-file/relink'):
                    result = workspace_file.action(app, self.path.rsplit('/', 1)[-1], payload)
                elif self.path in ('/api/team-file/export', '/api/team-file/new', '/api/team-file/open'):
                    result = app.team_file_action(self.path.rsplit('/', 1)[-1], payload)
                elif self.path.startswith('/api/work-history/'):
                    with app.store.lock:
                        action=self.path.rsplit('/',1)[-1]
                        if action=='preview':result=work_history.draft_record(app.store,payload)
                        elif action=='save':result=work_history.save_record(app.store,payload)
                        elif action=='view':
                            if payload.get('team_id')!=app.store.production_id:raise ValueError('The selected team changed.')
                            result=work_history.work_read(app.store,payload.get('period',''),employee_ids=[])
                        else:raise ValueError('Unknown work-history action.')
                elif self.path.startswith('/api/staff/'):
                    route=self.path.rsplit('/',1)[-1]
                    if route=='pay-propose':result=employee_pay.propose(app.store,payload)
                    elif route=='pay-accept':result=employee_pay.accept(app.store,payload)
                    elif route=='employee-import-prepare':result=employee_import.prepare(app.store,payload)
                    elif route=='employee-import-accept':result=employee_import.accept(app.store,payload)
                    elif route=='hours-propose':result=operating_hours.propose(app.store,payload['config'],'Owner reviewed operating-hours form')
                    elif route=='hours-accept':result=operating_hours.accept(app.store,payload['id'],payload['sha256'])
                    elif route=='employee':
                        result=staffing.save_employee(app.store,payload)
                        thread=app.store.data.setdefault('assistant_threads',{}).setdefault(app.store.production_id,{'messages':[],'pending':None});thread['staffing_form']=None;thread['messages'].append({'role':'assistant','text':'Saved '+result['name']+' and the availability you entered for '+staffing.book(app.store)['selected_week']+'. I can now suggest the week using these recorded details.','kind':'employee_saved','created':__import__('briefing').now()});app.store.save()
                    elif route=='end':result=staffing.end_employment(app.store,payload['employee_id'],payload['date'],payload.get('reason','Owner recorded employment end'))
                    elif route=='timeoff-cancel':result=staffing.cancel_time_off(app.store,payload['employee_id'],payload['date'],payload['expected_revision'])
                    elif route=='timeoff':result=staffing.time_off(app.store,payload['employee_id'],payload['start'],payload['end'],payload.get('reason','Time off requested'))
                    elif route=='settings':result=staffing.settings(app.store,payload)
                    elif route=='week':result=staffing.select_week(app.store,payload['week_start'])
                    elif route=='day':result=staffing.select_day(app.store,payload['date'])
                    elif route=='suggest':result=__import__('staffing_constraints').suggest_preserving(app.store,payload['week_start'])
                    elif route=='agent-plan':result=app.plan_staffing(payload)
                    elif route=='revise':result=staffing.revise_week(app.store,payload['id'],payload['sha256'],payload['days'])
                    elif route=='lunch':result=staffing.suggest_lunch(app.store,payload['shift_id'],payload['date'],payload.get('duration',30))
                    elif route=='sick':result=staffing.suggest_sick(app.store,payload['employee_id'],payload['date'])
                    elif route=='accept':result=staffing.accept(app.store,payload['id'],payload['sha256'],payload.get('choice'))
                    elif route=='shift':result=staffing.edit_shift(app.store,payload)
                    elif route=='restore':result=staffing.restore_schedule(app.store,payload)
                    elif route=='example':result=staffing.load_staff_example(app.store)
                    else:raise ValueError('Unknown staffing action.')
                elif self.path == '/api/import':
                    raw = base64.b64decode(payload['base64'], validate=True) if 'base64' in payload else payload.get('text', '').encode()
                    result = app.store.import_document(payload.get('title', ''), payload.get('filename', 'pasted.txt'), raw, payload.get('document_id'))
                elif self.path == '/api/sample':
                    with app.job_lock:
                        if any(x['status']=='running' for x in app.jobs.values()):
                            raise ValueError('Let the current handoff finish before opening the example.')
                        existing=next((x for x in app.store.data['productions'] if x.get('sample')),None)
                        if existing:
                            app.store.select_production(existing['id'])
                        else:
                            example=app.store.create_production('Fictional shoot example')
                            next(x for x in app.store.data['productions'] if x['id']==example['id'])['sample']=True
                        load_sample(app.store)
                    result = {'added': True}
                elif self.path == '/api/watch':
                    result = app.store.watch_file(payload['path'], payload.get('title', ''), payload.get('document_id'))
                elif self.path == '/api/watch/toggle':
                    app.store.toggle_watch(payload['id'], payload['enabled'])
                    result = {'updated': True}
                elif self.path == '/api/watch/refresh':
                    result = {'updates': app.store.refresh_watches()}
                elif self.path == '/api/voice/speak':
                    result = app.voice.speak(payload.get('text'))
                elif self.path == '/api/assistant/message':
                    result = app.assistant_message(payload)
                elif self.path == '/api/assistant/confirm':
                    result = confirm_sarah(app.store,payload.get('proposal_id'),payload.get('proposal_sha'),payload.get('confirmation'))
                elif self.path == '/api/brief':
                    result = app.brief(payload.get('request', 'Prepare the next-shift handoff.'),payload.get('mode','sarah_local'))
                elif self.path == '/api/decision':
                    app.store.set_decision(payload['briefing_id'], payload['decision_id'], payload['done'])
                    result = {'saved': True}
                else:
                    self.reply({'error': 'Not found'}, 404)
                    return
                self.reply(result)
            except (ValueError, KeyError, OSError) as exc:
                self.reply({'error': str(exc)}, 400)
    return workspace_file.synchronize_handler(Handler, app)


def make_server(state_dir, port=8797):
    app = App(state_dir)
    server = ThreadingHTTPServer(('127.0.0.1', port), handler(app))
    server.app = app
    return server

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=8797)
    parser.add_argument('--state-dir', default=str(Path(__file__).parent / 'data'))
    parser.add_argument('--open', action='store_true')
    args = parser.parse_args()
    server = make_server(args.state_dir, args.port)
    if args.open:
        def open_when_ready():
            import urllib.request
            for _ in range(100):
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{server.server_port}/api/state', timeout=1) as response:
                        if json.load(response).get('app') == 'ShiftBrief':
                            webbrowser.open(f'http://127.0.0.1:{server.server_port}')
                            return
                except OSError:
                    time.sleep(0.1)
        threading.Thread(target=open_when_ready, daemon=True).start()
    def watch_loop():
        while True:
            time.sleep(15)
            server.app.store.refresh_watches()
    threading.Thread(target=watch_loop, daemon=True).start()
    print(f'ShiftBrief: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()
