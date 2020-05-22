#!/usr/bin/env python


from datetime import datetime
import json
import os
from pathlib import PosixPath
import pwd
import subprocess
import signal
import socket
import sys
import tempfile
import time
from urllib.parse import urlparse
import uuid


import requests


VERSION = '0.1.0'


def send_to_sentry(uri, headers, data, timeout):
    kwargs = {}
    proxy_url = os.environ.get('SHELL_SENTRY_PROXY')
    if proxy_url is not None:
        kwargs['proxies'] = {
            'http': proxy_url,
            'https': proxy_url
        }
    try:
        resp = requests.post(
            uri, headers=headers, data=data, timeout=timeout,
            **kwargs
        )
        resp.raise_for_status()
    except requests.exceptions.RequestException as ex:
        clsname = ex.__class__.__name__
        eprint(f'Error "{clsname} while sending to Sentry: {ex}')


class SimpleSentryClient:
    TIMEOUT = 5
    SENTRY_VERSION = 5
    USER_AGENT = f'powerlibs.shentry/{VERSION}'

    def __init__(self, dsn, uri, public, secret, project_id):
        self.dsn = dsn
        self.uri = uri
        self.public = public
        self.secret = secret
        self.project_id = project_id

    @classmethod
    def new_from_environment(cls):
        dsn = os.environ.pop('SHELL_SENTRY_DSN', '')
        if not dsn:
            return None
        else:
            try:
                dsn_fields = urlparse(dsn)
                keys, netloc = dsn_fields.netloc.split('@', 1)
                if ':' in keys:
                    public, private = keys.split(':', 1)
                else:
                    public = keys
                    private = ''
                project_id = dsn_fields.path.lstrip('/')
                uri = f'{dsn_fields.scheme}://{netloc}/api/{project_id}/store/'
                return cls(dsn, uri, public, private, project_id)
            except Exception as ex:
                eprint(f'Error parsing sentry DSN {dsn}: {ex}')

    def send_event(
        self, message, level, fingerprint,
        logger='', culprit=None, extra_context=None
    ):
        extra_context = extra_context or {}

        event_id = uuid.uuid4().hex
        now = int(time.time())
        uname = os.uname()

        event = {
            'event_id': event_id,
            'timestamp': datetime.utcnow().isoformat().split('.', 1)[0],
            'message': message,
            'level': level,
            'server_name': socket.gethostname(),
            'sdk': {
                'name': 'powerlibs.shentry',
                'version': VERSION,
            },
            'fingerprint': fingerprint,
            'platform': 'other',
            'device': {
                'name': uname[0],
                'version': uname[2],
                'build': uname[3]
            },
            'extra': {}
        }
        if logger:
            event['logger'] = logger
        if culprit is not None:
            event['culprit'] = culprit
        event['extra'].update(extra_context)

        headers = {
            'X-Sentry-Auth': (
                f'Sentry sentry_version={self.SENTRY_VERSION}, '
                f'sentry_client={self.USER_AGENT}, '
                f'sentry_timestamp={now}, '
                f'sentry_key={self.public}, '
                f'sentry_secret={self.secret}'
            ),
            'User-Agent': self.USER_AGENT,
            'Content-Type': 'application/json',
        }
        if os.environ.get('SHELL_SENTRY_VERBOSE', '0') == '1':
            eprint('Sending to shentry')
            eprint(event)
        data = json.dumps(event).encode('utf-8')
        return send_to_sentry(
            uri=self.uri, headers=headers, data=data, timeout=self.TIMEOUT
        )


def get_command(argv):
    # get the command
    i_am_shell = False
    command = argv
    if command[0] == '-c':
        i_am_shell = True
        command = command[1:]
    if command[0] == '--':
        command = command[1:]
    shell = os.environ.get('SHELL', '/bin/sh')
    if i_am_shell or 'shentry' in shell:
        shell = '/bin/sh'
    command_ws = ' '.join(command)
    full_command = [shell, '-c', command_ws]
    return full_command, command_ws, shell


def eprint(*args):
    return print(*args, file=sys.stderr)


def show_usage():
    eprint('Usage: shentry [-c] command [...]')
    eprint('')
    eprint('Runs COMMAND, sending the output to Sentry if it exits non-0')
    eprint('Takes sentry DSN from $SHELL_SENTRY_DSN or /etc/shentry_dsn')


def read_snippet(fo, max_length):
    fo.seek(0, os.SEEK_END)
    length = fo.tell()
    rv = []
    fo.seek(0, os.SEEK_SET)
    read_all = False
    if length > max_length:
        top = int(max_length / 2) - 8
        bottom = max_length - top
        top = fo.read(top).decode('utf-8', 'ignore')
        rv.append(top)
        if not top.endswith('\n'):
            rv.append('\n')
        rv.append('\n[snip]\n')
        fo.seek(-1 * bottom, os.SEEK_END)
        rv.append(fo.read(bottom).decode('utf-8', 'ignore'))
    else:
        rv.append(fo.read().decode('utf-8', 'ignore'))
        read_all = True
    return ''.join(rv), read_all


def run(argv):
    if len(argv) < 2:
        show_usage()
        return 2

    extra_context = {
        'PATH': os.environ.get('PATH', ''),
        'username': pwd.getpwuid(os.getuid()).pw_name
    }

    if 'TZ' in os.environ:
        extra_context['TZ'] = os.environ['TZ']

    client = SimpleSentryClient.new_from_environment()

    full_command, command_ws, shell = get_command(argv[1:])
    extra_context['command'] = command_ws
    extra_context['shell'] = shell

    # if we couldn't configure sentry, just pass through
    if client is None:
        signal.signal(signal.SIGPIPE, signal.SIG_DFL)
        os.execv(shell, full_command)
        eprint('Unable to execv({0}, {1})'.format(shell, repr(full_command)))
        return 1

    working_dir = None
    p = None

    def passthrough(signum, frame):
        if p is not None:
            p.send_signal(signum)
        else:
            raise ValueError('received signal %d without a child; bailing' % signum)

    def reset_signals():
        for sig in (signal.SIGTERM, signal.SIGQUIT, signal.SIGINT, signal.SIGPIPE):
            signal.signal(sig, signal.SIG_DFL)

    def run_and_monitor(working_dir):
        stdout_path = working_dir / 'stdout'
        stderr_path = working_dir / 'stderr'
        with stdout_path.open('w+b') as stdout, \
                stderr_path.open('w+b') as stderr:
            start_time = time.time()

            p = subprocess.Popen(
                full_command, stdout=stdout, stderr=stderr,
                shell=False, preexec_fn=reset_signals
            )

            extra_context['start_time'] = start_time
            extra_context['load_average_at_exit'] = ' '.join(map(str, os.getloadavg()))
            extra_context['working_directory'] = os.getcwd()

            def print_all():
                stderr.seek(0)
                x = stderr.read().decode(sys.stderr.encoding)
                if x:
                    print(x, file=sys.stderr, end="")
                stdout.seek(0)
                x = stdout.read().decode(sys.stdout.encoding)
                if x:
                    print(x, end="")

            if p.wait() == 0:
                print_all()
                return 0

            else:
                end_time = time.time()
                extra_context['duration'] = end_time - start_time

                code = p.returncode
                extra_context['returncode'] = code

                stderr_head, stderr_is_all = read_snippet(stderr, 700)
                message = f'Command `{command_ws}` failed with code {code}.\n'
                if stderr_head:
                    if stderr_is_all:
                        message += '\nstderr:\n'
                    else:
                        message += '\nExcerpt of stderr:\n'
                    message += stderr_head
                stdout_head, stdout_is_all = read_snippet(
                    stdout, 200 + (700 - len(stderr_head))
                )
                if stdout_head:
                    if stdout_is_all:
                        message += '\nstdout:\n'
                    else:
                        message += '\nExcerpt of stdout:\n'
                    message += stdout_head
                client.send_event(
                    message=message,
                    level='error',
                    fingerprint=[socket.gethostname(), command_ws],
                    extra_context=extra_context,
                )
                print_all()
                return code

    for sig in (signal.SIGTERM, signal.SIGQUIT, signal.SIGINT):
        signal.signal(sig, passthrough)
    with tempfile.TemporaryDirectory() as working_dir:
        return run_and_monitor(PosixPath(working_dir))


def main():
    sys.exit(run(sys.argv[1:]))
