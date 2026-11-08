import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from recruit.runtime import data_root,settings
from recruit.extract import validate_job
from recruit.search import queries

class RuntimeTest(unittest.TestCase):
    def test_data_root_is_configurable_without_source_data(self):
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'config.json';target=Path(tmp)/'用户 data'
            path.write_text(json.dumps({'dataRoot':str(target),'profile':'Example only'}),encoding='utf-8-sig')
            with patch.dict(os.environ,{'CAMPUS_CONFIG_FILE':str(path)},clear=True):
                self.assertEqual(data_root(),target.resolve());self.assertEqual(settings()['profile'],'Example only')
            self.assertFalse(target.exists())
    def test_next_graduation_year_is_grounded_in_source(self):
        page={'url':'https://example.org/job','text':'示例公司 电气研发工程师 2028届校园招聘','links':[]}
        item={'company':'示例公司','title':'电气研发工程师','evidence':{'company':'示例公司','title':'电气研发工程师'}}
        self.assertEqual(validate_job(item,page,graduation_year=2028)['batch'],'2028届校招')
        self.assertTrue(all('2028' in q for q in queries('2027-11-01',year=2028)))

if __name__=='__main__':unittest.main()
