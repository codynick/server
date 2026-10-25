import importlib.util
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location('classroom_broker', Path(__file__).resolve().parents[1] / 'server/broker.py')
if sys.platform != 'win32':
    broker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(broker)


@unittest.skipIf(sys.platform == 'win32', 'Unix broker requires Linux')
class BrokerTests(unittest.TestCase):
    def setUp(self):
        broker.JOBS.clear()

    def test_invalid_actions_and_identity(self):
        for values in ({'uid': '../1', 'action': 'run'}, {'uid': 1, 'action': 'shell'}):
            with self.assertRaises(ValueError):
                broker.request(values)

    @patch('classroom_broker.docker')
    def test_other_user_stop_does_not_touch_container(self, docker):
        broker.JOBS['1'] = dict(name='cn-1-test', running=True, output='')
        broker.request(dict(uid=2, action='stop'))
        docker.assert_not_called()
        self.assertTrue(broker.JOBS['1']['running'])

    @patch('classroom_broker.threading.Thread')
    @patch('classroom_broker.docker', return_value='')
    def test_container_restrictions_are_fixed(self, docker, thread):
        result = broker.request(dict(uid=1, action='run', code='print(1)', mounts=['/']))
        self.assertTrue(result['ok'])
        args = docker.call_args_list[0].args
        self.assertIn('--read-only', args)
        self.assertEqual(args[args.index('--network') + 1], 'none')
        self.assertEqual(args[args.index('--memory') + 1], '128m')
        self.assertEqual(args[args.index('--pids-limit') + 1], '32')
        self.assertNotIn('--volume', args)
        self.assertNotIn('--privileged', args)

    def test_busy_slots(self):
        broker.JOBS['2'] = dict(running=True)
        broker.JOBS['3'] = dict(running=True)
        with self.assertRaisesRegex(ValueError, 'busy'):
            broker.request(dict(uid=1, action='run', code='pass'))


if sys.platform != 'win32':
    sys.modules['classroom_broker'] = broker
