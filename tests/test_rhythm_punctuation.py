import ast,re,unittest
from pathlib import Path
class RhythmPunctuationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        p=Path(__file__).resolve().parents[1]/'app/services.py'
        tree=ast.parse(p.read_text(encoding='utf-8'))
        fn=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='split_spoken_text_for_rhythm')
        ns={'re':re,'clean_text':lambda x:x.strip(),'content_lines_use_english':lambda x:False}
        exec(compile(ast.Module(body=[fn],type_ignores=[]),str(p),'exec'),ns)
        cls.split=staticmethod(ns[fn.name])
    def test_commas_preserved(self):
        text='机器人不会情绪不好，不会请假，也不会离职，它只是每天把几百杯拿铁，一杯一杯做好，放在取餐台上。'
        self.assertEqual(''.join(self.split(text,24)),text)
    def test_long_clause_preserved(self):
        text='这是一段需要保留完整标点的测试文本'*8+'，后面的内容也应该保持完整。'
        self.assertEqual(''.join(self.split(text,24)),text)
    def test_short_unchanged(self):
        self.assertEqual(self.split('你好，世界。'),['你好，世界。'])
if __name__=='__main__':unittest.main()
