from __future__ import annotations
import argparse, base64, json, secrets, threading, time, webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs
from briefing import Store, load_sample, update_packet
from agent import run_agent, runtime_settings
from sarah_local import run_local, ask as ask_sarah, confirm as confirm_sarah, LABEL

from voice_bridge import AppVoice
import staffing
import shift_schedule
import operating_hours

class App:
    def __init__(self, state_dir):
        self.store = Store(state_dir)
        self.voice = AppVoice(Path(__file__).parent, 'shiftbrief')
        self.jobs = {}
        self.token = secrets.token_urlsafe(24)
        self.job_lock = threading.Lock()

    def brief(self, request, mode='sarah_local'):
        if mode not in ('sarah_local','strands_ollama'):
            raise ValueError('Choose Sarah local evidence or optional Strands/Ollama.')
        with self.job_lock:
            if any(x['status'] == 'running' for x in self.jobs.values()):
                raise ValueError('A briefing is already being prepared.')
            job_id = secrets.token_hex(6)
            job = {'id': job_id, 'production_id': self.store.production_id, 'status': 'running', 'trace': [], 'started': time.time()}
            self.jobs[job_id] = job
        def work():
            try:
                result = (run_local if mode=='sarah_local' else run_agent)(self.store, request, progress=lambda trace: job.update(trace=list(trace)))
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
                    self.reply({'app': 'ShiftBrief', 'state': app.store.view(), 'token': app.token, 'runtime': {'mode':'sarah_local','label':LABEL,'model':'none','url':'local documents only','optional_strands_available':__import__('importlib.util',fromlist=['find_spec']).find_spec('strands') is not None}, 'jobs': [x for x in app.jobs.values() if x['production_id']==app.store.production_id]})
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
                elif path.path in ('/', '/app.js', '/style.css', '/sarah_voice.js', '/staffing_ui.js', '/operating_ui.js', '/source_handoff_ui.js'):
                    name = 'index.html' if path.path == '/' else path.path[1:]
                    kind = {'index.html': 'text/html', 'app.js': 'text/javascript', 'sarah_voice.js': 'text/javascript', 'staffing_ui.js': 'text/javascript', 'operating_ui.js': 'text/javascript', 'source_handoff_ui.js': 'text/javascript', 'style.css': 'text/css'}[name]
                    self.reply((Path(__file__).parent / name).read_text('utf-8-sig'), content_type=kind)
                else:
                    self.reply({'error': 'Not found'}, 404)
            except (ValueError, OSError) as exc:
                self.reply({'error': str(exc)}, 400)
        def do_POST(self):
            try:
                self.safe(True)
                size = int(self.headers.get('Content-Length', '0'))
                if size <= 0 or size > 7_000_000:
                    raise ValueError('Request too large or empty.')
                payload = json.loads(self.rfile.read(size))
                if not isinstance(payload,dict): raise ValueError('Supply a JSON object.')
                if self.path in ('/api/production/create','/api/production/select'):
                    with app.job_lock:
                        if any(x['status']=='running' for x in app.jobs.values()):
                            raise ValueError('Let the current handoff finish before switching productions.')
                        if self.path.endswith('/create'):
                            result=app.store.create_production(payload['title'])
                        else:
                            app.store.select_production(payload['id'])
                            result={'selected':True}
                elif self.path.startswith('/api/staff/'):
                    route=self.path.rsplit('/',1)[-1]
                    if route=='hours-propose':result=operating_hours.propose(app.store,payload['config'],'Owner reviewed operating-hours form')
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
                    elif route=='suggest':result=staffing.suggest_week(app.store,payload['week_start'])
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
                    result = ask_sarah(app.store,payload.get('message'),payload.get('briefing_id'))
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
    return Handler


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
