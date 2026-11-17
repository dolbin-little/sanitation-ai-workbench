import unittest
from backend.scenario import fresh,research_demo
from backend.reference_solver import reference

class ReferenceTests(unittest.TestCase):
    def test_exact_tiny_model_covers_and_proves_bound(self):
        s=fresh(research_demo(count=3));s['vehicles']=s['vehicles'][:3]
        r=reference(s,3)
        self.assertEqual(r['stages'][0]['status'],'OPTIMAL')
        self.assertEqual(r['stages'][0]['value'],0)
        tasks=[a['id'] for seq in r['routes'].values() for a in seq if a['kind']=='task']
        self.assertEqual(set(tasks),{'T001','T002','T003'});self.assertEqual(len(tasks),3)
    def test_model_refuses_large_claims(self):
        with self.assertRaises(ValueError):reference(fresh(research_demo()),1)
