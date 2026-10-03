# GKE public gateway

This bootstrap adds one regional external L4 load balancer and one small,
non-root NGINX reverse proxy. It exposes only HTTPS on port 443 (port 80 only
redirects to HTTPS): `/` reaches `web.fleet-app:8080`, `/grafana/` reaches
`grafana.observability:3000`, and `/argo/` reaches `argocd-server.argocd:443`.
The app, Grafana and Argo services remain ClusterIP services. Redis,
controller metrics and telemetry stores are not routed.

The deployment requires three operator-provided inputs, intentionally kept out
of Git: a `fleet-gateway/fleet-gateway-tls` TLS Secret whose certificate has
the public IP in its IP SAN, and a `fleet-gateway/argocd-server-ca` ConfigMap with
key `ca.crt` containing the issuer for the Argo server certificate. The gateway
verifies Argo's upstream TLS certificate and SNI name `argocd-server`.
Inspect the Argo certificate SAN and issuer before creating that ConfigMap.
The third input is the reviewer's current public IPv4 `/32` in the Service's
`loadBalancerSourceRanges`. The checked-in Service uses an inert `0.0.0.0/32`
default; render a private overlay with the approved reviewer address before
applying. Never use `0.0.0.0/0`. Keep the address out of Git and verify GKE's
generated ingress firewall and access from the reviewer's computer after apply.
If the address changes, update the private allowlist before the next review.
The Argo Kustomize overlay sets `server.basehref` and `server.rootpath` to
`/argo`; it leaves Argo TLS enabled. Grafana must set
`GF_SERVER_ROOT_URL=https://<public-ip>/grafana/` and
`GF_SERVER_SERVE_FROM_SUB_PATH=true`.

The Service uses one ephemeral public IP that remains assigned for the
Service's lifetime; no separate static reservation is needed for this lab.
Read the address from Service status before issuing the certificate. The
public certificate must contain that IP in an IP subject alternative name.
An IP URL will show a browser certificate warning because the self-signed
issuer is not publicly trusted; traffic remains encrypted, and passwords are
not sent over HTTP. Deleting the Service releases the address.

The root operator applies the namespace and Service first, reads its allocated
IP, creates the private certificate Secret and verified Argo CA ConfigMap,
then applies the bootstrap. Example remaining workflow (PowerShell; keep
`gateway.key` private):

```powershell
$gatewayIp = (kubectl -n fleet-gateway get service fleet-gateway -o "jsonpath={.status.loadBalancer.ingress[0].ip}").Trim()
openssl req -x509 -newkey rsa:3072 -sha256 -days 30 -nodes `
  -keyout .\gateway.key -out .\gateway.crt `
  -subj "/CN=$gatewayIp" -addext "subjectAltName=IP:$gatewayIp"
kubectl -n fleet-gateway create secret tls fleet-gateway-tls `
  --cert .\gateway.crt --key .\gateway.key --dry-run=client -o yaml |
  kubectl apply -f -
kubectl apply -k .\bootstrap\gcp\argo
# Render the gateway with the private reviewer /32 patch, then apply that render.
kubectl apply -f <PRIVATE_GATEWAY_RENDER>
kubectl -n fleet-gateway get service fleet-gateway -o wide
kubectl -n fleet-gateway rollout status deployment/fleet-gateway --timeout=180s
```

Never print the private key or place it in Git. Remove the local key and
certificate after the Secret is created and verified. To tear down the public
exposure, delete the gateway Service first so GKE releases its ephemeral IP,
then remove the gateway deployment and namespace.

The one regional forwarding rule is currently listed at USD $0.025/hour (about
$18.25 for 730 hours); the forwarding-rule-attached public IP has no separate
hourly charge. L4 processed traffic is currently $0.008/GiB inbound and
$0.008/GiB outbound, before ordinary internet egress and the existing GKE
compute cost. Actual billing depends on region, traffic and currency. See
[Google Cloud network pricing](https://cloud.google.com/vpc/network-pricing).

The current manual cluster uses the legacy dataplane without NetworkPolicy enforcement. The included policy describes the intended egress rules, but does not establish isolation on this cluster. HTTPS, verified Argo upstream TLS and UI logins provide the current access controls. Enforce policies when creating the later CI cluster with a compatible dataplane.

The image is the verified NGINX Inc. unprivileged Docker image, pinned to the
multi-platform digest for the 1.30 Alpine line. NGINX documents its non-root
UID, 8080 listen port and `/tmp` PID/temp paths in the
[upstream image repository](https://github.com/nginx/docker-nginx-unprivileged);
the immutable digest is listed by the
[NGINX Inc. Docker Hub publisher](https://hub.docker.com/layers/nginxinc/nginx-unprivileged/1.30-alpine/images/sha256-ee1643aef6b99d1058aa79b74679ba3e63094a98a1144a4326def7bae77d293b).
