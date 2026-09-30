#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
CFG=tempfile.TemporaryDirectory()
os.environ['XDG_CONFIG_HOME']=str(Path(CFG.name)/'config')
os.environ['XDG_DATA_HOME']=str(Path(CFG.name)/'data')
sys.path.insert(0,str(ROOT))
import azzx_cli as a

class Handler(BaseHTTPRequestHandler):
    def log_message(self,*args): pass
    def do_GET(self):
        if self.path.endswith('/models'):
            body={'data':[{'id':'mock-coder'}]}; self._send(body); return
        self.send_response(404); self.end_headers()
    def do_POST(self):
        length=int(self.headers.get('content-length','0')); req=json.loads(self.rfile.read(length) or b'{}')
        msgs=req.get('messages') or []
        system='\n'.join(str(x.get('content','')) for x in msgs if x.get('role')=='system')
        user='\n'.join(str(x.get('content','')) for x in msgs if x.get('role')=='user')
        if 'senior product analyst and software architect' in system:
            text=json.dumps({
                'product':'# Product\n\nMock product.',
                'requirements':'# Requirements\n\n- Generated module works.',
                'constraints':'# Constraints\n\n- Keep it small.',
                'architecture':'# Architecture\n\nEntry point: generated.py',
                'acceptance':'# Acceptance Tests\n\n- generated.py compiles.'
            })
        elif 'Return ONLY JSON with key milestones' in system:
            text=json.dumps({'milestones':[{'id':'M1','title':'Core','status':'pending','tasks':['Implement core']},{'id':'M2','title':'Verify','status':'pending','tasks':['Run tests']}]})
        elif 'careful coding agent' in system:
            content='def hello():\n    return "ok"\n'
            if 'sandbox-change' in user or 'factory-change' in user:
                content+='\ndef feature():\n    return 42\n'
            text=json.dumps({'summary':'mock patch','changes':[{'path':'generated.py','content':content}],'notes':[]})
        elif 'Planner agent' in system:
            text='1. Create or update generated.py\n2. Run syntax and tests\n3. Review the result'
        elif 'code review' in system:
            text='No blocking issues found in the supplied mock project.'
        elif 'software architect' in system:
            text='# Architecture\n\nEntry point: generated.py\n'
        else:
            text='Concise engineering guidance for the mock project.'
        self._send({'choices':[{'message':{'content':text}}]})
    def _send(self,obj):
        data=json.dumps(obj).encode(); self.send_response(200); self.send_header('Content-Type','application/json'); self.send_header('Content-Length',str(len(data))); self.end_headers(); self.wfile.write(data)

srv=ThreadingHTTPServer(('127.0.0.1',0),Handler)
thread=threading.Thread(target=srv.serve_forever,daemon=True); thread.start()
try:
    a.setup_homes()
    cfg=a.load_config(); cfg['default_provider']='mock'; cfg['provider_priority']=['mock']; cfg['fallback_enabled']=True; a.save_config(cfg)
    a.save_providers({'mock':{'name':'Mock AI','kind':'openai','base_url':f'http://127.0.0.1:{srv.server_address[1]}/v1','model':'mock-coder','requires_key':False,'enabled':True,'key_ids':[]}})
    with tempfile.TemporaryDirectory() as td:
        root=Path(td).resolve()
        assert a.run_edit_task(root,'create a tiny generated module','create')
        assert (root/'generated.py').read_text()=='def hello():\n    return "ok"\n'
        assert a.run_tests(root,quiet=True)
        a.generate_architecture(root)
        assert (root/'.azzx/architecture.md').exists()
        assert a.run_multi_agent(root,'keep generated module valid')
        tid=a.task_create(root,'maintain generated module')
        assert tid=='0001'
        assert a.task_resume(root,tid)
        obj=json.loads((root/'.azzx/tasks/0001.json').read_text())
        assert obj['status']=='done'
        a.refresh_repository_map(root,quiet=True)
        repo=json.loads((root/'.azzx/repo_map.json').read_text())
        assert 'hello' in repo['definitions']
        # V5 sandbox-first development
        assert a.sandbox_develop(root,'sandbox-change: add a feature',yes_merge=True)
        assert 'def feature' in (root/'generated.py').read_text()
        # V5 software-factory flow on a clean project
        factory_root=root/'factory_project'; factory_root.mkdir()
        (factory_root/'generated.py').write_text('def hello():\n    return "ok"\n')
        assert a.factory_develop(factory_root,'factory-change: extend generated module',yes_merge=True,package=False)
        assert (factory_root/'.azzx/spec/product.md').exists()
        assert (factory_root/'.azzx/roadmap.json').exists()
        assert 'def feature' in (factory_root/'generated.py').read_text()
        print('MOCK AI INTEGRATION PASSED')
finally:
    srv.shutdown(); srv.server_close(); thread.join(timeout=2)
    CFG.cleanup()
