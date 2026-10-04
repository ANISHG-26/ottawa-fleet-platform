"""Register private JSON fields before actions can print derived values."""
import json
import os
import re
import sys


def private_masks(inputs: str, provider: str) -> list[str]:
    match = re.fullmatch(r'projects/([0-9]+)/locations/global/workloadIdentityPools/[A-Za-z0-9_-]+/providers/[A-Za-z0-9_-]+', provider)
    if not match:
        raise ValueError('invalid federation provider for private log masking')
    values = set()
    def visit(value):
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)
        elif isinstance(value, str) and len(value) >= 4:
            values.add(value)
    visit(json.loads(inputs))
    values.add(match.group(1))
    return sorted(values)


def emit_masks(inputs: str, provider: str, stream=None) -> None:
    stream = stream or sys.stdout
    # Workflow-command data requires escaping so input cannot introduce a command.
    for value in private_masks(inputs, provider):
        escaped = value.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
        print('::add-mask::' + escaped, file=stream, flush=True)


if __name__ == '__main__':
    try:
        emit_masks(os.environ['LAB_TFVARS_JSON'], os.environ['GCP_WIF_PROVIDER'])
    except (KeyError, ValueError, TypeError):
        print('private log masking configuration is invalid', file=sys.stderr)
        sys.exit(1)
