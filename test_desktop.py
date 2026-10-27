import json
import os
import tempfile
import unittest
from unittest.mock import Mock, patch

# Keep imports from creating a database in the user's data directory.
_test_data = tempfile.TemporaryDirectory()
os.environ['PROJECT_MANAGER_DATA'] = _test_data.name
import desktop


class DesktopTests(unittest.TestCase):
    def test_allowed_origins(self):
        self.assertEqual(desktop.private_origin('http://192.168.1.8:18766/#invite=abc'), 'http://192.168.1.8:18766')
        self.assertEqual(desktop.private_origin('http://127.0.0.1:1234/'), 'http://127.0.0.1:1234')
        for url in ['https://example.com', 'http://example.com', 'http://8.8.8.8', 'http://user:pw@127.0.0.1']:
            with self.assertRaises(ValueError):
                desktop.private_origin(url)

    def test_session_and_home(self):
        api = desktop.DesktopAPI('http://127.0.0.1:1234')
        api.window = Mock()
        api.window.get_current_url.return_value = 'http://192.168.1.8:18766/'
        with patch.object(desktop.shutil, 'which', return_value='/usr/bin/notify-send'):
            self.assertTrue(api.configure_notifications('a' * 32)['available'])
        self.assertEqual(api._base, 'http://192.168.1.8:18766')
        api.go_home()
        self.assertEqual((api._base, api._token), (api.local_base, ''))
        api.window.load_url.assert_called_once_with(api.local_base)
        with self.assertRaises(ValueError):
            api.configure_notifications('bad')

    def test_notification_ack_only_after_submission(self):
        api = desktop.DesktopAPI('http://127.0.0.1:1234')
        reminders = [{'id': 7, 'title': '测试任务'}]
        with patch.object(desktop, 'json_request', side_effect=[reminders]) as req, patch.object(desktop, 'send_notification', return_value=False):
            api._poll_once()
            self.assertEqual(req.call_count, 1)
        with patch.object(desktop, 'json_request', side_effect=[reminders, {'ok': True}]) as req, patch.object(desktop, 'send_notification', return_value=True):
            api._poll_once()
            self.assertEqual(req.call_args.args[1], 'reminder-ack')
            self.assertEqual(req.call_args.args[3], {'id': 7})


if __name__ == '__main__':
    unittest.main()
