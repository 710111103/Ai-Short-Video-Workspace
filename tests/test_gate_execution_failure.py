import ast,json,sys,unittest
from pathlib import Path
from unittest.mock import Mock,patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.gate_repair_policy import mark_execution_failure,repeated_editorial_failure,gate_round_message
class FailureTests(unittest.TestCase):
    def test_timeout_binds_latest_input(self):
        r={'actions':[], 'score':58,'source_fingerprint':'old','editorial_attempted':True}
        mark_execution_failure(r,'Request timed out.','changed','now')
        self.assertEqual(r['source_fingerprint'],'changed')
        self.assertFalse(r['reassessment_completed'])
        r['cache_hit']=True
        self.assertTrue(repeated_editorial_failure(r))
        r['retry_after_epoch']=0
        self.assertFalse(repeated_editorial_failure(r))
        self.assertIn('未完成复评',gate_round_message(r,1))
    def test_closed_loop_stops_on_timeout(self):
        tree=ast.parse(Path('app/services.py').read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='run_production_stage_gate_closed_loop')
        fn.returns=None
        for arg in fn.args.args+fn.args.kwonlyargs:arg.annotation=None
        r={'status':'failed','score':58,'passed':False,'error':'Request timed out.','execution_failed':True,'actions':[],'issues':[]}
        call=Mock(return_value=r)
        ns=dict(json=json,run_production_stage_gate=call,emit_stage_gate_progress=Mock(),save_stage_gate_result=Mock(),clean_text=str,gate_round_message=gate_round_message)
        exec(compile(ast.Module(body=[fn],type_ignores=[]),'gate','exec'),ns)
        out=ns[fn.name](111,'content_gate',max_rounds=3)
        self.assertEqual(call.call_count,1)
        self.assertTrue(out['rounds'][0]['execution_failed'])
if __name__=='__main__':unittest.main()
