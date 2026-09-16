"""Offline checks: block network before importing any project or test code."""
import os
import sys

if os.environ.get('HOMEOSTASIS_OFFLINE') == '1':
    for key in ('GEMINI_API_KEY', 'GOOGLE_API_KEY', 'OPENAI_API_KEY'):
        os.environ.pop(key, None)

    def deny_network(event, args):
        if event in ('socket.connect', 'socket.getaddrinfo', 'socket.sendto'):
            raise RuntimeError('HOMEOSTASIS offline check: network forbidden')
    sys.addaudithook(deny_network)
