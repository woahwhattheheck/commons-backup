import unittest
from types import SimpleNamespace
from scientific_environment import ScientificEnvironment,THREAD_LIMITS,install
class Fake:
    PIPE=object()
    def __init__(self):self.calls=[]
    def Popen(self,*a,**kw):self.calls.append((a,kw));return SimpleNamespace(pid=23)
class Tests(unittest.TestCase):
    def setUp(self):self.fake=Fake();self.proxy=ScientificEnvironment(self.fake,['/exact/scipy.py'])
    def test_selected(self):
        env={'PATH':'/bin','LANG':'C.UTF-8'};args=['python','-B','evaluate.py','--worker','/exact/scipy.py','cache','loader','42']
        self.proxy.Popen(args,env=env,cwd='/private',start_new_session=True)
        call=self.fake.calls[0];self.assertIs(call[0][0],args);self.assertEqual(call[1]['env'],{**env,**THREAD_LIMITS});self.assertEqual(env,{'PATH':'/bin','LANG':'C.UTF-8'});self.assertTrue(call[1]['start_new_session']);self.assertTrue(self.proxy.launches[0]['limits_applied'])
    def test_unselected(self):
        env={'X':'not_copied_from_parent'};self.proxy.Popen(['python','--worker','/other.py'],env=env);self.assertIs(self.fake.calls[0][1]['env'],env);self.assertFalse(self.proxy.launches[0]['limits_applied'])
    def test_nonworker(self):
        self.proxy.Popen(['echo','ok']);self.assertNotIn('env',self.fake.calls[0][1])
    def test_string_not_parsed(self):
        self.proxy.Popen('python --worker /exact/scipy.py');self.assertFalse(self.proxy.launches[0]['limits_applied'])
    def test_no_parent_env_inheritance(self):
        with self.assertRaises(ValueError):self.proxy.Popen(['python','--worker','/exact/scipy.py'])
        self.assertEqual(self.fake.calls,[])
    def test_overrides_only_whitelist(self):
        env={'OPENBLAS_NUM_THREADS':'9','TOKEN':'present_only_as_explicit_input'};self.proxy.Popen(['python','--worker','/exact/scipy.py'],env=env);got=self.fake.calls[0][1]['env'];self.assertEqual(got['OPENBLAS_NUM_THREADS'],'1');self.assertEqual(got['TOKEN'],env['TOKEN']);self.assertEqual(env['OPENBLAS_NUM_THREADS'],'9')
    def test_delegation(self):self.assertIs(self.proxy.PIPE,self.fake.PIPE)
    def test_install_local_only(self):
        module=SimpleNamespace(subprocess=self.fake);p=install(module,['x']);self.assertIs(module.subprocess,p);self.assertFalse(isinstance(self.fake,ScientificEnvironment));self.assertIs(p._original,self.fake)
    def test_no_double_install(self):
        m=SimpleNamespace(subprocess=self.fake);install(m,['x'])
        with self.assertRaises(ValueError):install(m,['x'])
    def test_exact_spec_only(self):
        self.proxy.Popen(['python','--worker','/exact/scipy.py::other'],env={});self.assertFalse(self.proxy.launches[0]['limits_applied'])
    def test_invalid_specs(self):
        for value in ([],[''],[None]):
            with self.assertRaises(ValueError):ScientificEnvironment(self.fake,value)
    def test_launch_failure_retained(self):
        def fail(*a,**kw):raise OSError('synthetic start failure')
        self.fake.Popen=fail
        with self.assertRaisesRegex(OSError,'synthetic'):self.proxy.Popen(['python','--worker','/exact/scipy.py'],env={})
        self.assertEqual(self.proxy.launches,[])
if __name__=='__main__':unittest.main()
