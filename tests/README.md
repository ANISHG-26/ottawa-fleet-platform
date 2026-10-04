# Platform acceptance

Application API, worker and browser behavior tests live in the app repository.
Platform checks validate local acceptance evidence, immutable promotion,
cluster safeguards, GCP bootstrap, telemetry configuration and CI expiry/cleanup
contracts. Run the offline stdlib suite from the platform repository root:

```powershell
python -m unittest discover -s tests -v
python scripts/check_repository.py
```

Most tests use stdlib fixtures and fakes without calling cloud APIs. If Terraform
and its Google provider are initialized, `test_terraform_bounds.py` invokes
provider-mocked Terraform tests; otherwise it reports an explicit skip. The
separate gateway rendering suite requires kubectl and the verified upstream
Argo manifest. CI also validates all four Terraform roots and runs real function
startup and cleanup-image smoke checks. See the
[validation entrypoints](../docs/tooling-map.md#validation-entrypoints) for those commands.

These checks do not count as live rollout, reconciliation, rollback or teardown
evidence.
See [local acceptance runbook](../docs/runbooks/local-acceptance.md) for the
operator workflow and report limits.
