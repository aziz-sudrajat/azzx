#!/usr/bin/env python3
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent
TMP_CONFIG=tempfile.TemporaryDirectory()
os.environ['XDG_CONFIG_HOME']=str(Path(TMP_CONFIG.name)/'config')
os.environ['XDG_DATA_HOME']=str(Path(TMP_CONFIG.name)/'data')
sys.path.insert(0,str(ROOT))
import azzx_cli as a


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.td=tempfile.TemporaryDirectory()
        self.root=Path(self.td.name).resolve()

    def tearDown(self):
        self.td.cleanup()

    def test_parse_json_object(self):
        obj=a.parse_json_object('```json\n{"summary":"ok","changes":[]}\n```')
        self.assertEqual(obj['summary'],'ok')

    def test_safe_workspace_path(self):
        self.assertEqual(a.safe_workspace_path(self.root,'src/a.py'),self.root/'src/a.py')
        with self.assertRaises(a.AzzxError):
            a.safe_workspace_path(self.root,'../outside.txt')
        with self.assertRaises(a.AzzxError):
            a.safe_workspace_path(self.root,'.azzx/x')

    def test_backup_diff_undo_new_and_existing(self):
        (self.root/'a.py').write_text('x=1\n')
        backup=a.apply_changes(self.root,[{'path':'a.py','content':'x=2\n'},{'path':'new.py','content':'y=3\n'}],'test')
        self.assertEqual((self.root/'a.py').read_text(),'x=2\n')
        self.assertTrue((self.root/'new.py').exists())
        self.assertIn('-x=1',a.diff_backup(self.root,backup))
        restored=a.restore_backup(self.root,backup)
        self.assertIn('a.py',restored)
        self.assertEqual((self.root/'a.py').read_text(),'x=1\n')
        self.assertFalse((self.root/'new.py').exists())

    def test_repository_map_python_and_js(self):
        (self.root/'main.py').write_text('class App:\n    pass\n\ndef run():\n    return App()\n')
        (self.root/'web.js').write_text('function start() { return run(); }\nclass UI {}\n')
        repo=a.refresh_repository_map(self.root,quiet=True)
        self.assertIn('App',repo['definitions'])
        self.assertIn('run',repo['definitions'])
        self.assertIn('start',repo['definitions'])
        self.assertGreaterEqual(repo['symbol_count'],4)

    def test_context_symbol_boost(self):
        (self.root/'alpha.py').write_text('def SpecialRouter():\n    return 1\n')
        (self.root/'misc.py').write_text('x=1\n')
        a.refresh_repository_map(self.root,quiet=True)
        files=a.list_project_files(self.root)
        selected=a.select_relevant_files(self.root,files,'fix SpecialRouter',1)
        self.assertEqual(selected[0].name,'alpha.py')

    def test_task_persistence_without_ai(self):
        tid=a.task_create(self.root,'offline task example')
        self.assertEqual(tid,'0001')
        obj=json.loads((self.root/'.azzx/tasks/0001.json').read_text())
        self.assertEqual(obj['goal'],'offline task example')
        a.task_set_status(self.root,tid,'paused')
        obj=json.loads((self.root/'.azzx/tasks/0001.json').read_text())
        self.assertEqual(obj['status'],'paused')

    def test_package_filename_cannot_escape_dist(self):
        (self.root/'main.py').write_text('print("ok")\n')
        with self.assertRaises(a.AzzxError):
            a.package_tar(self.root,'../escape.tar.gz')

    def test_plain_secret_migrates_when_crypto_available(self):
        if a.Fernet is None:
            self.skipTest('cryptography unavailable')
        a.setup_homes()
        a.SECRETS_FILE.unlink(missing_ok=True)
        a.PLAIN_SECRETS_FILE.write_text(json.dumps({'legacy-key':'secret-value'}))
        vault=a.SecretVault()
        self.assertEqual(vault.get('legacy-key'),'secret-value')
        self.assertTrue(a.SECRETS_FILE.exists())
        self.assertFalse(a.PLAIN_SECRETS_FILE.exists())

    def test_portable_package(self):
        (self.root/'main.py').write_text('print("ok")\n')
        (self.root/'.azzx').mkdir()
        (self.root/'.azzx/secret').write_text('no')
        target=a.package_tar(self.root)
        self.assertTrue(target.exists())
        import tarfile
        with tarfile.open(target) as tf:
            names=tf.getnames()
        self.assertTrue(any(n.endswith('/main.py') for n in names))
        self.assertFalse(any('/.azzx/' in n for n in names))

    def test_release_manifest_and_arch_scaffold(self):
        (self.root/'main.py').write_text('print("ok")\n')
        (self.root/'.azzx-package.json').write_text(json.dumps({'name':'demo-app','version':'1.2.3','entrypoint':'main.py'}))
        manifest=a.release_project(self.root,'2.0.0')
        data=json.loads(manifest.read_text())
        self.assertEqual(data['version'],'2.0.0')
        self.assertEqual(len(data['sha256']),64)
        pkgbuild=a.build_arch_package(self.root)
        self.assertTrue(pkgbuild.exists())
        self.assertIn('pkgname=demo-app',pkgbuild.read_text())

    def test_workspace_registry_missing_name(self):
        with self.assertRaises(a.AzzxError):
            a.workspace_command(self.root,'status','does-not-exist')

    def test_mcp_modern_stdio(self):
        server={'name':'mock','command':sys.executable,'args':[str(HERE/'mock_mcp_server.py')],'protocol':'auto'}
        proc,era=a._mcp_open(self.root,server)
        try:
            self.assertEqual(era,'modern')
            tools=a._mcp_request(proc,era,2,'tools/list',{})
            self.assertEqual(tools['tools'][0]['name'],'echo')
            out=a._mcp_request(proc,era,3,'tools/call',{'name':'echo','arguments':{'x':1}})
            self.assertIn('content',out)
        finally:
            a._close_mcp_process(proc)

    def test_mcp_legacy_fallback(self):
        server={'name':'legacy','command':sys.executable,'args':[str(HERE/'mock_mcp_legacy.py')],'protocol':'auto'}
        proc,era=a._mcp_open(self.root,server)
        try:
            self.assertEqual(era,'legacy')
            tools=a._mcp_request(proc,era,2,'tools/list',{})
            self.assertEqual(tools['tools'][0]['name'],'legacy_echo')
        finally:
            a._close_mcp_process(proc)

    def test_parser_v3_commands(self):
        p=a.build_parser()
        ns=p.parse_args(['task','create','repair','router'])
        self.assertEqual(ns.command,'task')
        self.assertEqual(ns.task_args,['repair','router'])
        ns=p.parse_args(['mcp','call','srv','echo','{"x":1}'])
        self.assertEqual(ns.mcp_args[0],'echo')
        ns=p.parse_args(['build','tar'])
        self.assertEqual(ns.target,'tar')

    def test_v4_dependency_graph_and_impact(self):
        (self.root/'util.py').write_text('def helper():\n    return 1\n')
        (self.root/'main.py').write_text('from util import helper\nprint(helper())\n')
        graph=a.build_dependency_graph(self.root,quiet=True)
        self.assertIn('util.py',graph['files']['main.py'])
        result=a.impact_analysis(self.root,'helper',2)
        self.assertIn(('main.py',1),[tuple(x) for x in result['affected']])

    def test_v4_issue_lifecycle(self):
        a.issue_command(self.root,'create',text='Login fails')
        obj=json.loads((self.root/'.azzx/issues/0001.json').read_text())
        self.assertEqual(obj['status'],'open')
        a.issue_command(self.root,'close','0001')
        obj=json.loads((self.root/'.azzx/issues/0001.json').read_text())
        self.assertEqual(obj['status'],'closed')

    def test_v4_security_scan_does_not_echo_secret(self):
        secret='super-secret-value-123456789'
        (self.root/'config.py').write_text(f'api_key = "{secret}"\n')
        findings=a.security_scan(self.root,False)
        self.assertTrue(any(f['severity']=='HIGH' for f in findings))
        report=(self.root/'.azzx/security-report.json').read_text()
        self.assertNotIn(secret,report)

    def test_v4_sqlite_and_ci(self):
        import sqlite3
        db=self.root/'app.db'
        con=sqlite3.connect(db); con.execute('create table users(id integer primary key, name text)'); con.commit(); con.close()
        a.db_command(self.root,'inspect','app.db')
        a.db_command(self.root,'query','app.db','select count(*) as n from users')
        path=a.ci_create(self.root,'github')
        self.assertTrue(path.exists())
        self.assertIn('actions/checkout',path.read_text())

    def test_v4_skills_context(self):
        a.skill_command(self.root,'use','google-apps-script')
        ctx=a.active_skill_context(self.root)
        self.assertIn('Google Apps Script',ctx)
        (self.root/'Code.gs').write_text('function doGet(){ return 1; }\n')
        built,_,_=a.build_workspace_context(self.root,'fix doGet',a.load_config())
        self.assertIn('ACTIVE PROJECT SKILL',built)

    def test_parser_v4_commands(self):
        p=a.build_parser()
        self.assertEqual(p.parse_args(['impact','foo']).command,'impact')
        self.assertEqual(p.parse_args(['issue','create','broken','login']).issue_args,['broken','login'])
        self.assertEqual(p.parse_args(['tests','generate','auth.py']).action,'generate')
        self.assertEqual(p.parse_args(['db','inspect','app.db']).database,'app.db')
        self.assertEqual(p.parse_args(['skill','use','fastapi']).name,'fastapi')

    def test_safe_workspace_path_inside_parent_azzx(self):
        nested=self.root/'.azzx/sandboxes/demo'; nested.mkdir(parents=True)
        self.assertEqual(a.safe_workspace_path(nested,'generated.py'),nested/'generated.py')
        with self.assertRaises(a.AzzxError): a.safe_workspace_path(nested,'.azzx/internal.json')


    def test_v5_spec_and_roadmap_state(self):
        a.spec_init(self.root,'Demo product')
        self.assertIn('Demo product',(self.root/'.azzx/spec/product.md').read_text())
        a.spec_command(self.root,'set','requirements','- Must work offline')
        self.assertIn('offline',(self.root/'.azzx/spec/requirements.md').read_text())
        a.save_json(a.roadmap_path(self.root),{'goal':'demo','milestones':[{'id':'M1','title':'Core','status':'pending','tasks':['x']}]})
        a.roadmap_command(self.root,'set',['M1','done'])
        data=json.loads(a.roadmap_path(self.root).read_text())
        self.assertEqual(data['milestones'][0]['status'],'done')

    def test_v5_permissions(self):
        cfg=a.load_config(); original=dict(cfg.get('permissions') or {})
        try:
            cfg['permissions']=dict(original); cfg['permissions']['git.push']='deny'; a.save_config(cfg)
            self.assertEqual(a.permission_policy('git.push'),'deny')
            with self.assertRaises(a.AzzxError): a.require_permission('git.push','test',noninteractive=True)
            cfg=a.load_config(); cfg['permissions']['filesystem.write']='allow'; a.save_config(cfg)
            self.assertTrue(a.require_permission('filesystem.write','test',noninteractive=True))
        finally:
            cfg=a.load_config(); cfg['permissions']=original; a.save_config(cfg)

    def test_v5_sandbox_diff_and_regression(self):
        (self.root/'main.py').write_text('x=1\n')
        sandbox=a.create_sandbox(self.root,'unit')
        (sandbox/'main.py').write_text('x=2\n')
        (sandbox/'new.py').write_text('y=3\n')
        changes=a._sandbox_changes(self.root,sandbox)
        self.assertEqual({c['path'] for c in changes},{'main.py','new.py'})
        base=a.capture_regression_baseline(self.root)
        self.assertTrue(base['tests_ok'])
        self.assertTrue(a.regression_check(self.root))

    def test_v5_release_candidate(self):
        (self.root/'main.py').write_text('print("ok")\n')
        a.capture_regression_baseline(self.root)
        manifest=a.release_prepare(self.root,'5.0.1')
        self.assertTrue(manifest.exists())
        self.assertTrue((self.root/'dist/checksums.txt').exists())
        self.assertTrue((self.root/'dist/RELEASE_NOTES.md').exists())

    def test_v5_dashboard_health_endpoint(self):
        import http.server, threading, urllib.request
        handler=type('TestDash',(a._DashboardHandler,),{'root_path':self.root})
        srv=http.server.ThreadingHTTPServer(('127.0.0.1',0),handler)
        th=threading.Thread(target=srv.serve_forever,daemon=True); th.start()
        try:
            raw=urllib.request.urlopen(f'http://127.0.0.1:{srv.server_address[1]}/api/health',timeout=3).read()
            data=json.loads(raw)
            self.assertTrue(data['ok']); self.assertEqual(data['version'],'6.0.0')
        finally:
            srv.shutdown(); srv.server_close(); th.join(timeout=2)

    def test_parser_v5_commands(self):
        p=a.build_parser()
        ns=p.parse_args(['permissions','set','shell.run','allow']); self.assertEqual(ns.capability,'shell.run')
        ns=p.parse_args(['spec','set','requirements','hello']); self.assertEqual(ns.section,'requirements')
        ns=p.parse_args(['roadmap','set','M1','done']); self.assertEqual(ns.roadmap_args,['M1','done'])
        ns=p.parse_args(['sandbox','fix','login','--yes-merge']); self.assertTrue(ns.yes_merge)
        ns=p.parse_args(['factory','build','app','--package']); self.assertTrue(ns.package)


    def test_v6_package_alias_and_command_builder(self):
        self.assertEqual(a.app_package_candidates('metasploit','pacman',a.BUILTIN_APP_RECIPES)[0],'metasploit')
        self.assertEqual(a.app_package_candidates('python','apt',a.BUILTIN_APP_RECIPES)[0],'python3')
        ctx=a.SystemContext('linux','debian','Debian','debian','13','x86_64','apt',True,False)
        self.assertEqual(a.package_action_command(ctx,'install',['ffmpeg']),['apt-get','install','-y','ffmpeg'])
        self.assertEqual(a.package_action_command(ctx,'remove',['ffmpeg']),['apt-get','remove','-y','ffmpeg'])

    def test_v6_package_name_guard(self):
        self.assertEqual(a._sanitize_package_name('libxml2-dev'),'libxml2-dev')
        with self.assertRaises(a.AzzxError): a._sanitize_package_name('--help')
        with self.assertRaises(a.AzzxError): a._sanitize_package_name('../../evil')
        with self.assertRaises(a.AzzxError): a._sanitize_package_name('bad package')

    def test_v6_resolver_prefers_native_when_available(self):
        from unittest.mock import patch
        fake=a.SystemContext('linux','arch','Arch Linux','','','x86_64','pacman',True,False)
        with patch.object(a,'detect_system_context',return_value=fake), patch.object(a,'package_available',return_value=True):
            plan=a.resolve_app_plan('metasploit',probe=True)
        self.assertEqual(plan.method,'native')
        self.assertEqual(plan.packages,['metasploit'])

    def test_v6_metasploit_official_fallback_is_trusted(self):
        from unittest.mock import patch
        fake=a.SystemContext('linux','debian','Debian','','13','x86_64','apt',True,False)
        with patch.object(a,'detect_system_context',return_value=fake), patch.object(a,'package_available',return_value=False):
            plan=a.resolve_app_plan('metasploit',probe=True)
        self.assertEqual(plan.method,'official-script')
        self.assertTrue(plan.source_url.startswith('https://raw.githubusercontent.com/rapid7/'))

    def test_v6_termux_does_not_use_metasploit_vendor_fallback(self):
        from unittest.mock import patch
        fake=a.SystemContext('termux','termux','Termux','android','','aarch64','pkg',False,False)
        with patch.object(a,'detect_system_context',return_value=fake), patch.object(a,'package_available',return_value=False):
            plan=a.resolve_app_plan('metasploit',probe=True)
        self.assertEqual(plan.method,'unresolved')

    def test_v6_install_record_roundtrip(self):
        plan=a.AppPlan('demo','demo','native','apt',['demo'],['definitely-not-installed-azzx-test'])
        a._record_install(plan,'')
        rec=a._load_install_records()['demo']
        self.assertEqual(rec['method'],'native')
        self.assertEqual(rec['packages'],['demo'])

    def test_parser_v6_app_commands(self):
        p=a.build_parser()
        ns=p.parse_args(['install','ffmpeg','--plan']); self.assertTrue(ns.plan)
        ns=p.parse_args(['install','httpie','--isolated']); self.assertTrue(ns.isolated)
        ns=p.parse_args(['uninstall','ffmpeg','--dry-run']); self.assertTrue(ns.dry_run)
        ns=p.parse_args(['update','--all','--dry-run']); self.assertTrue(ns.all)
        ns=p.parse_args(['app','search','video','editor']); self.assertEqual(ns.app_args,['video','editor'])
        self.assertEqual(p.parse_args(['installed']).command,'installed')


    def test_v6_isolated_path_stays_inside_data_home(self):
        target=a._isolated_app_dir('httpie')
        self.assertTrue(str(target).startswith(str(a.ISOLATED_APPS_HOME.resolve())))
        plan=a.resolve_isolated_plan('httpie')
        self.assertEqual(plan.method,'python-venv')
        self.assertEqual(plan.packages,['httpie'])


if __name__=='__main__':
    unittest.main(verbosity=2)
