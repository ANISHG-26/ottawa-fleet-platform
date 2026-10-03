# Platform acceptance

Application API, worker and browser behavior tests live in the app repository.
Platform checks validate bounded local acceptance evidence, immutable
promotion inputs and plan-only local cluster safeguards. Run the offline
stdlib suite from the platform repository root:

```powershell
python -m unittest discover -s tests -v
python scripts/check_repository.py
```

The checks do not launch Docker, Kubernetes, Argo CD, Terraform or cloud APIs.
They do not count as rollout, reconciliation, rollback or teardown evidence.
See [local acceptance runbook](../docs/runbooks/local-acceptance.md) for the
operator workflow and report limits.
