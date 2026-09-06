"""Bounded client-side throughput measurement through an explicit HTTP proxy.

Example: python measure-proxy.py --proxy http://192.168.1.100:7893 --url https://YOUR-ENDPOINT/file
Uses neither environment proxies nor automatic direct fallback. Each round is
capped at 16 MiB / approximately 20 seconds; unfinished rounds are labelled.
"""
import argparse
import json
import time
import urllib.parse
import urllib.request


class ExplicitProxy(urllib.request.ProxyHandler):
    def proxy_open(self, req, proxy, type):
        # ProxyHandler normally bypasses local hosts via environment settings.
        # Explicitly set the proxy to avoid measuring an unintended path.
        parsed = urllib.parse.urlsplit(proxy)
        if parsed.username or parsed.password:
            raise ValueError('Use a temporary unauthenticated test listener; credentials are not logged')
        req.set_proxy(parsed.netloc, parsed.scheme)
        return None


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--proxy', required=True)
    parser.add_argument('--url', required=True)
    args = parser.parse_args()
    if urllib.parse.urlsplit(args.url).scheme != 'https':
        parser.error('The measurement endpoint must use HTTPS')
    proxy = urllib.parse.urlsplit(args.proxy)
    if proxy.scheme != 'http' or not proxy.hostname:
        parser.error('Specify an explicit HTTP proxy address')
    opener = urllib.request.build_opener(ExplicitProxy({'http': args.proxy, 'https': args.proxy}))
    for round_id in range(1, 4):
        start = time.monotonic()
        received = 0
        first_byte = None
        outcome = 'time_limit'
        try:
            request = urllib.request.Request(args.url, headers={'Range': 'bytes=0-16777215', 'Cache-Control': 'no-cache'})
            with opener.open(request, timeout=5) as response:
                while received < 16777216 and time.monotonic() - start < 20:
                    block = response.read(min(65536, 16777216-received))
                    if not block:
                        outcome = 'completed'
                        break
                    received += len(block)
                    if first_byte is None:
                        first_byte = time.monotonic() - start
                if received == 16777216:
                    outcome = 'byte_limit'
        except Exception as error:
            outcome = type(error).__name__
        elapsed = time.monotonic()-start
        print(json.dumps({'round': round_id, 'bytes': received, 'seconds': round(elapsed, 3),
                          'first_read_seconds': first_byte, 'average_mbps': round(received*8/elapsed/1e6, 3),
                          'result': outcome}))
