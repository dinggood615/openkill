"""Real Mihomo validation and local-only API, DNS and HTTP proxy smoke tests.

No TUN interface or host routes are created by the runtime smoke test.
TUN fixtures are checked with -t only; OpenWrt integration needs router tests.
"""
import argparse
import gzip
import hashlib
import http.client
import http.server
import json
import os
from pathlib import Path
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request


def free_port(socktype=socket.SOCK_STREAM):
    with socket.socket(socket.AF_INET, socktype) as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def download_core(tag, destination):
    url = 'https://api.github.com/repos/MetaCubeX/mihomo/releases/' + ('latest' if tag == 'latest' else 'tags/' + tag)
    headers = {'User-Agent': 'OpenKill-compatibility-tests'}
    token = os.environ.get('GITHUB_TOKEN')
    if token:
        headers['Authorization'] = 'Bearer ' + token
    with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=30) as response:
        release = json.load(response)
    assets = [a for a in release['assets'] if a['name'].startswith('mihomo-linux-amd64-compatible-') and a['name'].endswith('.gz')]
    if len(assets) != 1:
        raise RuntimeError('Official compatible amd64 asset is ambiguous or absent')
    asset = assets[0]
    digest = asset.get('digest', '')
    if not digest.startswith('sha256:'):
        raise RuntimeError('Official release asset has no SHA256 digest')
    with urllib.request.urlopen(asset['browser_download_url'], timeout=90) as response:
        data = response.read()
    if hashlib.sha256(data).hexdigest() != digest.split(':', 1)[1]:
        raise RuntimeError('Mihomo download checksum mismatch')
    destination.write_bytes(gzip.decompress(data))
    destination.chmod(0o755)
    return release['tag_name']


def api(port, password):
    conn = http.client.HTTPConnection('127.0.0.1', port, timeout=2)
    try:
        conn.request('GET', '/version', headers={'Authorization': 'Bearer ' + password})
        response = conn.getresponse()
        return response.status, response.read()
    finally:
        conn.close()


def run_tests(core, directory):
    baseline = {'mode': 'rule', 'log-level': 'warning', 'rules': ['MATCH,DIRECT'],
                'proxies': [], 'proxy-groups': []}
    count = 0
    for owner in ['openkill', 'mihomo']:
        for ipv6 in [False, True]:
            for stack in ['system', 'mixed']:
                config = dict(baseline, ipv6=ipv6)
                config['tun'] = {'enable': True, 'device': 'utun', 'stack': stack,
                                 'auto-route': owner == 'mihomo', 'auto-redirect': owner == 'mihomo',
                                 'dns-hijack': ['any:53', 'tcp://any:53']}
                file = directory / 'validate.yaml'
                file.write_text(json.dumps(config), encoding='utf-8')
                subprocess.run([str(core), '-t', '-d', str(directory), '-f', str(file)], check=True,
                               timeout=30, capture_output=True)
                count += 1

    class Probe(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.end_headers()
            self.wfile.write(b'openkill-proxy-smoke')
        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), Probe)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    control, mixed, dns = free_port(), free_port(), free_port(socket.SOCK_DGRAM)
    config = dict(baseline, **{'external-controller': f'127.0.0.1:{control}', 'secret': 'test-secret',
                              'mixed-port': mixed, 'allow-lan': False, 'bind-address': '127.0.0.1',
                              'hosts': {'probe.test': '127.0.0.1'},
                              'dns': {'enable': True, 'listen': f'127.0.0.1:{dns}', 'use-hosts': True,
                                      'enhanced-mode': 'redir-host', 'nameserver': ['127.0.0.1:9']}})
    file = directory / 'smoke.yaml'
    file.write_text(json.dumps(config), encoding='utf-8')
    log = (directory / 'core.log').open('wb')
    process = subprocess.Popen([str(core), '-d', str(directory), '-f', str(file)], stdout=log, stderr=log)
    try:
        deadline = time.monotonic() + 15
        while True:
            try:
                status, body = api(control, 'test-secret')
                if status == 200 and json.loads(body).get('version'):
                    break
            except (OSError, ValueError):
                pass
            if process.poll() is not None or time.monotonic() >= deadline:
                raise RuntimeError('Controller did not become healthy')
            time.sleep(0.2)
        assert api(control, 'wrong-secret')[0] in (401, 403), 'API accepted an invalid secret'
        connection = http.client.HTTPConnection('127.0.0.1', mixed, timeout=5)
        connection.request('GET', f'http://127.0.0.1:{server.server_port}/probe')
        response = connection.getresponse()
        assert response.status == 200 and response.read() == b'openkill-proxy-smoke', 'Proxy data path failed'
        connection.close()
        name = b'\x05probe\x04test\0'
        query = struct.pack('!6H', 1234, 0x100, 1, 0, 0, 0) + name + struct.pack('!2H', 1, 1)
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.settimeout(5)
            sock.sendto(query, ('127.0.0.1', dns))
            packet = sock.recv(4096)
        ident, flags, _, answers, _, _ = struct.unpack('!6H', packet[:12])
        assert ident == 1234 and flags & 15 == 0 and answers > 0, 'Local DNS response failed'
        print(f'{count} TUN configuration cases passed; controller/auth, HTTP proxy and local DNS passed')
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()
        server.shutdown()
        server.server_close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--release', default='v1.19.30')
    parser.add_argument('--core')
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix='openkill-core-test-') as tmp:
        directory = Path(tmp)
        core = Path(args.core).resolve() if args.core else directory / 'mihomo'
        if not args.core:
            print('Testing official stable', download_core(args.release, core))
        run_tests(core, directory)
