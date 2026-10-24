"""Editorial request failures must never reach persistence/canonicalization."""
import ast
import unittest
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import Mock

class EditorialFailureTests(unittest.TestCase):
    def run_case(self, text, reason, expected):
        source=Path(__file__).resolve().parents[1]/'app'/'services.py'
        tree=ast.parse(source.read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='optimize_project_content')
        storage=Mock()
        storage.get_project.return_value={'template':'test'}
        storage.get_template.return_value={'mode':'video'}
        response=NS(choices=[NS(message=NS(content=text),finish_reason=reason)])
        client=Mock();client.chat.completions.create.return_value=response
        env={'DEEPSEEK_API_KEY':'test','DEEPSEEK_MODEL':'test'}
        ns={'request_editor_stream':lambda *a,**kw:response,'Any':object,'storage':storage,'clean_text':lambda x:str(x or '').strip(),
            'content_engagement_report':Mock(return_value={}), 'runtime_env':lambda:env,
            'OpenAI':Mock(return_value=client),'normalize_deepseek_base_url':lambda x:x,
            'normalize_deepseek_model':lambda x,y:x,'deepseek_optional_request_body':Mock(return_value={}),
            'deepseek_rewrite_timeout_seconds':lambda x:180,'compose_deepseek_rewrite_messages':Mock(return_value=[{'content':'test'}]),
            'build_common_content_system_rules':lambda:'','build_viral_content_rules':lambda *a:'',
            'build_product_content_rules':lambda *a:'','build_output_language_rules':lambda *a:'',
            'message_content_to_text':lambda x:x,'strip_code_fences':lambda x:x,
            're':__import__('re'),'ContentGenerationError':ValueError,
            'canonicalize_project_content':Mock(), 'editorial_evidence_block':lambda x:'', 'effective_project_references':Mock(return_value=[])}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(source),'exec'),ns)
        with self.assertRaisesRegex(ValueError,expected):
            ns['optimize_project_content'](111,'# original')
        ns['canonicalize_project_content'].assert_not_called()
        storage.save_content.assert_not_called()
        self.assertEqual(storage.save_report.call_count, 2)
    def test_empty(self): self.run_case('', 'stop','正文为空')
    def test_truncated(self): self.run_case('# incomplete','length','被截断')
    def test_invalid_format(self): self.run_case('explanation only','stop','格式异常')

if __name__=='__main__': unittest.main()
