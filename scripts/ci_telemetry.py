"""Install bounded lab telemetry and verify all three signals through Grafana."""
from __future__ import annotations

import base64
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal
import json
from pathlib import Path
import re
import secrets
import socket
import subprocess
import time
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler, ProxyHandler

from scripts.ci_application import _run
from scripts.gcp_lab import expected_context

COMPONENTS = ('loki', 'tempo', 'mimir', 'grafana', 'alloy')
SERVICES = {'fleet-api', 'ride-api', 'assignment-worker'}


def quantity(value):
    """Parse Kubernetes CPU/memory quantities without silently dropping requests."""
    match = re.fullmatch(r'(\d+(?:\.\d+)?)([eE][+-]?\d+|[numkKMGTEP]|[KMGTPE]i)?', str(value))
    if not match:
        raise ValueError('unsupported Kubernetes resource quantity')
    number, suffix = Decimal(match[1]), match[2] or ''
    if suffix.startswith(('e', 'E')) and len(suffix) > 1:
        return number * (Decimal(10) ** int(suffix[1:]))
    if suffix.endswith('i'):
        return number * (Decimal(1024) ** ('KMGTPE'.index(suffix[0]) + 1))
    powers = {'': 0, 'n': -9, 'u': -6, 'm': -3, 'k': 3, 'K': 3, 'M': 6, 'G': 9, 'T': 12, 'P': 15, 'E': 18}
    return number * (Decimal(10) ** powers[suffix])


def pod_request(pod, resource):
    spec = pod.get('spec', {})
    def request(container):
        return quantity(container.get('resources', {}).get('requests', {}).get(resource, '0'))
    regular = sum((request(c) for c in spec.get('containers', [])), Decimal(0))
    sidecars, peak = Decimal(0), Decimal(0)
    for container in spec.get('initContainers', []):
        amount = request(container)
        if container.get('restartPolicy') == 'Always':
            sidecars += amount
            peak = max(peak, sidecars)
        else:
            peak = max(peak, sidecars + amount)
    pod_level = quantity(spec.get('resources', {}).get('requests', {}).get(resource, '0'))
    return max(regular + sidecars, peak, pod_level) + quantity(spec.get('overhead', {}).get(resource, '0'))


def check_capacity(nodes, pods):
    ready = [n for n in nodes if not n.get('spec', {}).get('unschedulable') and
             any(c.get('type') == 'Ready' and c.get('status') == 'True' for c in n.get('status', {}).get('conditions', []))]
    if len(ready) != 1:
        raise ValueError('telemetry requires one ready schedulable lab node')
    node = ready[0]
    if any(t.get('effect') in ('NoSchedule', 'NoExecute') for t in node.get('spec', {}).get('taints', [])):
        raise ValueError('telemetry node has an unsupported scheduling taint')
    live = [p for p in pods if p.get('status', {}).get('phase') not in ('Succeeded', 'Failed')]
    # Reserve all existing pending work as well as work already bound to this node.
    live = [p for p in live if p.get('spec', {}).get('nodeName') in (None, '', node['metadata']['name'])]
    # Retry only the known five-pod namespace within its measured request budget.
    monitoring = [p for p in live if p.get('metadata', {}).get('namespace') == 'observability']
    names = [p.get('metadata', {}).get('labels', {}).get('app.kubernetes.io/name') for p in monitoring]
    if any(name not in COMPONENTS for name in names) or len(set(names)) != len(names):
        raise ValueError('unexpected or duplicate monitoring pods; inspect node headroom')
    if sum((pod_request(p, 'cpu') for p in monitoring), Decimal(0)) > Decimal('0.4') or sum((pod_request(p, 'memory') for p in monitoring), Decimal(0)) > 1056 * 1024 * 1024:
        raise ValueError('existing monitoring requests exceed the reviewed headroom budget')
    live = [p for p in live if p not in monitoring]
    allocatable = node['status']['allocatable']
    free_cpu = quantity(allocatable['cpu']) - sum((pod_request(p, 'cpu') for p in live), Decimal(0))
    free_memory = quantity(allocatable['memory']) - sum((pod_request(p, 'memory') for p in live), Decimal(0))
    # Existing five-pod budget plus one web rolling-update surge (50m / 64 MiB).
    if free_cpu < Decimal('0.45') or free_memory < 1120 * 1024 * 1024:
        raise ValueError('insufficient node request headroom for LGTM and web rollout')
    return {'free_cpu_millis': int(free_cpu * 1000), 'free_memory_mib': int(free_memory / 1024 / 1024)}


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *_args, **_kwargs):
        raise ValueError('Grafana readiness redirects are refused')


def _grafana_json(base, password, path, payload=None, *, timeout=10):
    if not re.fullmatch(r'http://127\.0\.0\.1:\d+', base) or not path.startswith('/grafana/api/'):
        raise ValueError('Grafana readiness requires the owned loopback forward')
    auth = base64.b64encode(('admin:' + password).encode()).decode()
    headers = {'Authorization': 'Basic ' + auth, 'Accept': 'application/json'}
    data = None
    if payload is not None:
        data = json.dumps(payload).encode()
        headers['Content-Type'] = 'application/json'
    request = Request(base + path, headers=headers, data=data)
    with build_opener(ProxyHandler({}), _NoRedirect()).open(request, timeout=timeout) as response:
        raw = response.read(1_000_001)
        if len(raw) > 1_000_000:
            raise ValueError('Grafana readiness response exceeded its bound')
        return json.loads(raw)


@contextmanager
def grafana_forward(command, remaining):
    # A private ephemeral listener is used only for authenticated readiness checks.
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 0))
        port = probe.getsockname()[1]
    process = subprocess.Popen([*command, '-n', 'observability', 'port-forward', 'service/grafana', f'{port}:3000', '--address=127.0.0.1'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        startup = time.monotonic() + min(20, remaining())
        while time.monotonic() < startup:
            if process.poll() is not None:
                raise RuntimeError('Grafana readiness forward exited')
            try:
                with socket.create_connection(('127.0.0.1', port), timeout=min(1, remaining())):
                    break
            except OSError:
                time.sleep(min(0.2, remaining()))
        else:
            raise RuntimeError('Grafana readiness forward timed out')
        yield f'http://127.0.0.1:{port}'
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)


def query_has_rows(data):
    result = data.get('results', {}).get('A', {}) if isinstance(data, dict) else {}
    if result.get('error') or result.get('status', 200) >= 400:
        return False
    return any(frame.get('data', {}).get('values') and len(frame['data']['values'][0]) > 0 for frame in result.get('frames', []))


def deploy(*, project, zone, cluster, kubeconfig, expires_at, root=None,
           runner=subprocess.run, now=lambda: datetime.now(timezone.utc), sleep=time.sleep,
           forward=grafana_forward):
    root = Path(root or Path(__file__).resolve().parents[1])
    expiry = datetime.fromisoformat(expires_at.replace('Z', '+00:00'))
    if expiry.tzinfo is None:
        raise ValueError('lab expiry must include a timezone')
    deadline = min(expiry, now() + timedelta(minutes=8))
    command = ['kubectl', '--kubeconfig', str(kubeconfig), '--context=' + expected_context(project, zone, cluster)]
    def remaining():
        seconds = (deadline - now()).total_seconds()
        if seconds <= 0:
            raise RuntimeError('LGTM readiness bound or lab expiry elapsed')
        return seconds
    def kube(args, *, data=None, timeout=30):
        return _run([*command, *args], runner=runner, cwd=root, input_text=data, timeout=min(timeout, max(0.1, remaining())))
    remaining()
    nodes = json.loads(kube(['get', 'nodes', '-o', 'json']))['items']
    pods = json.loads(kube(['get', 'pods', '-A', '-o', 'json']))['items']
    capacity = check_capacity(nodes, pods)
    kube(['-n', 'observability', 'apply', '-f', 'observability/kubernetes/namespace.yaml'])
    existing = kube(['-n', 'observability', 'get', 'secret', 'grafana-admin', '--ignore-not-found', '-o', 'json'])
    if existing.strip():
        try:
            secret = json.loads(existing)
            if secret['metadata'].get('labels', {}).get('platform.ottawa-fleet/owner') != 'ci-lgtm':
                raise ValueError('secret ownership differs')
            password = base64.b64decode(secret['data']['password'], validate=True).decode()
            if len(password) < 32 or len(password) > 256 or not password.isascii() or any(ord(c) < 33 or ord(c) > 126 for c in password):
                raise ValueError('invalid password')
        except Exception:
            raise ValueError('existing lab Grafana credential is invalid or not owned by CI') from None
    else:
        password = secrets.token_urlsafe(36)
        secret = {'apiVersion': 'v1', 'kind': 'Secret', 'type': 'Opaque', 'metadata': {'name': 'grafana-admin', 'namespace': 'observability', 'labels': {'platform.ottawa-fleet/owner': 'ci-lgtm'}}, 'data': {'password': base64.b64encode(password.encode()).decode()}}
        kube(['create', '-f', '-'], data=json.dumps(secret))
    kube(['apply', '-k', 'observability/ci'])
    kube(['apply', '-f', 'observability/kubernetes/alloy-rbac.yaml'])
    for component in COMPONENTS:
        seconds = max(1, int(remaining()))
        kube(['-n', 'observability', 'rollout', 'status', 'deployment/' + component, f'--timeout={seconds}s'], timeout=seconds)
    queries = {
        'metrics': {'refId': 'A', 'datasource': {'type': 'prometheus', 'uid': 'mimir'}, 'expr': 'ride_pending_jobs', 'instant': True, 'range': False, 'format': 'table'},
        'logs': {'refId': 'A', 'datasource': {'type': 'loki', 'uid': 'loki'}, 'expr': '{job="ottawa-fleet"}', 'queryType': 'range', 'direction': 'backward', 'maxLines': 10},
        'traces': {'refId': 'A', 'datasource': {'type': 'tempo', 'uid': 'tempo'}, 'queryType': 'traceqlSearch', 'query': '{}', 'limit': 5},
    }
    with forward(command, remaining) as base:
        while True:
            remaining()
            try:
                # Read-only synthetic HTTP traffic produces fresh logs and spans.
                for service, port, path in (('fleet-api', 8080, 'v1/fleet?limit=1'), ('ride-api', 8081, 'v1/rides?limit=1')):
                    kube(['get', '--raw', f'/api/v1/namespaces/fleet-app/services/{service}:{port}/proxy/{path}'])
                def fetch(path, payload=None):
                    return _grafana_json(base, password, path, payload, timeout=min(10, remaining()))
                if fetch('/grafana/api/health').get('database') != 'ok':
                    raise ValueError('Grafana database is not ready')
                sources = fetch('/grafana/api/datasources')
                if {s.get('uid') for s in sources} != {'mimir', 'loki', 'tempo'}:
                    raise ValueError('Grafana datasources are incomplete')
                up = fetch('/grafana/api/datasources/proxy/uid/mimir/api/v1/query?' + urlencode({'query': 'up{job="ottawa-fleet"}'}))
                series = up.get('data', {}).get('result', [])
                if up.get('status') != 'success' or {s.get('metric', {}).get('service') for s in series if s.get('value', [None, None])[1] == '1'} != SERVICES:
                    raise ValueError('application scrapes are not all healthy')
                if all(query_has_rows(fetch('/grafana/api/ds/query', {'from': 'now-5m', 'to': 'now', 'queries': [query]})) for query in queries.values()):
                    return {'ready_components': list(COMPONENTS), 'signals': list(queries), 'capacity': capacity}
            except Exception:
                # Never surface HTTP response bodies, Basic auth or secret values.
                pass
            sleep(min(5, remaining()))
