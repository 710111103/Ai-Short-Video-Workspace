import sys, unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from app.editorial_evidence import is_historical_script, editorial_evidence_block
class EvidenceTests(unittest.TestCase):
    def test_history(self):
        self.assertTrue(is_historical_script({'source':'历史稿'}))
        self.assertTrue(is_historical_script({'url':'C:/data/projects/50/content.md'}))
    def test_external(self):
        self.assertFalse(is_historical_script({'url':'https://example.com/report'}))
    def test_block_excludes_history(self):
        text=editorial_evidence_block([{'source':'历史稿','snippet':'UNRELATED'},{'title':'current','snippet':'SUPPORTED'}])
        self.assertNotIn('UNRELATED',text)
        self.assertIn('SUPPORTED',text)
if __name__=='__main__': unittest.main()
