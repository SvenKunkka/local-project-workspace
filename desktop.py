"""Windows and Linux desktop shell for the local workspace."""
import ipaddress
import json
import logging
import os
import re
import shutil
import subprocess
import sys
import threading
import time
from http.server import ThreadingHTTPServer
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

import server

LOG = logging.getLogger('workspace')
POWERSHELL_TOAST = r'''$ErrorActionPreference = 'Stop'
[Windows.UI.Notifications.ToastNotificationManager, Windows.UI.Notifications, ContentType = WindowsRuntime] > $null
$title = [System.Security.SecurityElement]::Escape($env:PM_NOTIFICATION_TITLE)
$body = [System.Security.SecurityElement]::Escape($env:PM_NOTIFICATION_BODY)
$xml = New-Object Windows.Data.Xml.Dom.XmlDocument
$xml.LoadXml("<toast><visual><binding template='ToastGeneric'><text>$title</text><text>$body</text></binding></visual></toast>")
$toast = [Windows.UI.Notifications.ToastNotification]::new($xml)
[Windows.UI.Notifications.ToastNotificationManager]::CreateToastNotifier('Microsoft.Windows.PowerShell').Show($toast)
'''


def private_origin(url):
    """Allow only local or private IPv4 addresses used by workspace invitations."""
    parsed = urlsplit(url)
    if parsed.scheme != 'http' or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError('只允许本机或可信局域网的 HTTP 地址')
    if parsed.hostname != 'localhost':
        address = ipaddress.ip_address(parsed.hostname)
        if address.version != 4 or not (address.is_private or address.is_loopback):
            raise ValueError('只允许局域网 IPv4 地址')
    port = parsed.port or 80
    return f'http://{parsed.hostname}:{port}'


def send_notification(title, body):
    """Return True only when the platform command reports successful submission."""
    if sys.platform == 'win32':
        executable = shutil.which('powershell.exe')
        if not executable:
            return False
        env = dict(os.environ, PM_NOTIFICATION_TITLE=title, PM_NOTIFICATION_BODY=body)
        result = subprocess.run([executable, '-NoProfile', '-NonInteractive', '-Command', POWERSHELL_TOAST],
                                env=env, capture_output=True, timeout=15, creationflags=subprocess.CREATE_NO_WINDOW)
    elif sys.platform.startswith('linux'):
        executable = shutil.which('notify-send')
        if not executable:
            return False
        result = subprocess.run([executable, '--app-name=项目工作台', title, body], capture_output=True, timeout=15)
    else:
        return False
    if result.returncode:
        LOG.warning('Notification command failed with exit code %s', result.returncode)
    return result.returncode == 0


def json_request(base, path, token='', payload=None):
    headers = {}
    if token:
        headers['Authorization'] = 'Bearer ' + token
    body = None
    if payload is not None:
        body = json.dumps(payload).encode('utf-8')
        headers.update({'Origin': base, 'Content-Type': 'application/json'})
    request = Request(base + '/api/' + path, data=body, headers=headers)
    with urlopen(request, timeout=5) as response:
        return json.load(response)


class DesktopAPI:
    def __init__(self, local_base):
        self.local_base = local_base
        self.window = None
        self._base = local_base
        self._token = ''
        self._mutex = threading.Lock()
        self._stop = threading.Event()

    def configure_notifications(self, token=''):
        if not isinstance(token, str) or (token and not re.fullmatch(r'[A-Za-z0-9_-]{20,128}', token)):
            raise ValueError('邀请身份无效')
        origin = private_origin(self.window.get_current_url())
        if origin == self.local_base:
            token = ''
        elif not token:
            raise ValueError('远程工作区缺少邀请身份')
        with self._mutex:
            self._base, self._token = origin, token
        return {'available': bool(shutil.which('powershell.exe' if sys.platform == 'win32' else 'notify-send'))}

    def go_home(self):
        with self._mutex:
            self._base, self._token = self.local_base, ''
        self.window.load_url(self.local_base)

    def _poll_once(self):
        with self._mutex:
            base, token = self._base, self._token
        for item in json_request(base, 'reminders-due', token):
            if send_notification('任务提醒', str(item.get('title', '待办任务'))):
                json_request(base, 'reminder-ack', token, {'id': item['id']})

    def _poll(self):
        while not self._stop.wait(20):
            try:
                self._poll_once()
            except Exception as exc:
                LOG.warning('Reminder check failed: %s', type(exc).__name__)


def main():
    import webview
    listener = ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    port = listener.server_address[1]
    base = f'http://127.0.0.1:{port}'
    threading.Thread(target=listener.serve_forever, daemon=True).start()
    api = DesktopAPI(base)
    webview.settings['ALLOW_DOWNLOADS'] = True
    api.window = webview.create_window('项目工作台', base, js_api=api, width=1280, height=820, min_size=(720, 520))
    threading.Thread(target=api._poll, daemon=True).start()
    smoke = '--smoke' in sys.argv
    outcome = {'ok': False}
    def verify_window():
        try:
            if not api.window.events.loaded.wait(30):
                raise RuntimeError('window did not load')
            for _ in range(40):
                ready = api.window.evaluate_js("document.querySelector('#heading')?.textContent === '总览' && document.querySelector('#connection')?.textContent.includes('本机主机') && typeof window.workspaceNotificationStatus === 'number'")
                if ready:
                    break
                time.sleep(.5)
            else:
                raise RuntimeError('workspace data or desktop bridge did not initialize')
            outcome['ok'] = True
        except Exception as exc:
            LOG.error('Desktop smoke test failed: %s', exc)
        finally:
            api.window.destroy()
    try:
        webview.start(verify_window if smoke else None, gui='qt' if sys.platform.startswith('linux') else None)
    finally:
        api._stop.set()
        server.stop_lan()
        listener.shutdown()
        listener.server_close()
    if smoke and not outcome['ok']:
        raise SystemExit(1)


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    main()
