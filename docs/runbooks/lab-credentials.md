# Lab reviewer credentials

This runbook covers the existing Grafana and Argo reviewer logins for the lab. The retained `terraform/access` root owns exactly two Secret Manager containers: `fleet-lab-grafana-admin` and `fleet-lab-argo-admin`. Each payload is JSON with `username` and `password`. The credential migration and consumer configuration are handled separately; this root creates no payload versions, access grants, service accounts, or controller integration. The UI continues to use the existing passwords. Future CI access requires a separately reviewed identity and accessor change.

## Provisioning boundary

Use the separate GCS backend state prefix `lab-access`, outside any disposable lab or CI teardown state. Before the first apply, confirm the project and record the human approval of the exact two-secret proposal in the private plan. Set `resource_plan_reviewed = true` only after that review is recorded. Keep `project_id` and `review_project_id` sensitive in the private variable file and ensure they match. Do not put payload JSON, usernames, or passwords in Terraform variables, plans, state, command arguments, or logs.

The root enables `secretmanager.googleapis.com` with `disable_on_destroy = false`. Both containers use automatic global replication, labels `purpose=reviewer-access` and `managed_by=terraform`, provider deletion protection, and Terraform `prevent_destroy`. Their GCS state is retained separately from disposable lab state. No cloud provisioning is authorized by this documentation alone.

## Retrieve a login

Open the Secret Manager versions page for the specific secret in the reviewed project:

- Grafana: `https://console.cloud.google.com/security/secret-manager/secret/fleet-lab-grafana-admin/versions?project=<PROJECT_ID>`
- Argo: `https://console.cloud.google.com/security/secret-manager/secret/fleet-lab-argo-admin/versions?project=<PROJECT_ID>`

Replace `<PROJECT_ID>` with the reviewed project ID. Select the exact numeric version recorded for the consumer or migration, then view its JSON payload and copy the `username` and `password` fields directly into the intended secure login flow. Do not use `latest` for a reproducible handoff. Never paste payload values into shell commands, Terraform, tickets, chat, or logs. The username is `admin` for both current reviewer logins.

## Rotate a password

1. Create a new version of the relevant secret through the approved secret-entry workflow. Enter the JSON payload in the secure UI; do not echo the value from a command or capture it in terminal history or logs.
2. Retrieve and verify the new version by its exact numeric version, then update the intended consumer to that pinned version/password.
3. Confirm the new intended credential authenticates against the live UI, and retain the previous version for rollback until this succeeds. Updating Grafana's bootstrap Kubernetes Secret alone does not update or prove its database-backed login password. For Argo, preserve its bcrypt password-verifier generation and modification-time behavior, then verify the new login after updating its verifier. Rotation requires a separately authorized operator workflow.
4. Only after the consumer succeeds, disable or destroy the superseded version according to the approved retention policy, and record the version number and verification in the private operations log. Disabled versions remain billable while retained, so remove obsolete versions when policy permits.

Rotation is an explicit two-step operation: first verify the new version, then update and verify the consumer. Do not change both consumers as part of routine container provisioning. Container deletion protection and the separate retained state remain in force during rotation.

## Cost and replication

Automatic replication keeps each secret available globally and incurs one billable replication location per secret. At two enabled versions the estimate is approximately **US$0.12 gross per month**, before account-level free allowances. Secret Manager's free allowance is account-wide (up to six active secret versions and 10,000 access operations per month in the reviewed pricing basis); check current pricing and usage before relying on it. Disabled versions still count as active and billable until destroyed. Access operations from future consumers may add charges.

Pricing reference: [Google Cloud Secret Manager pricing](https://cloud.google.com/secret-manager/pricing). Container reference: [Secret Manager overview](https://cloud.google.com/secret-manager/docs/overview).
