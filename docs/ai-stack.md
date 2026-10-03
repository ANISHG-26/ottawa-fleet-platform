# Investigator AI stack (proposal)

The investigator is a thin, read-only aid for examining synthetic fleet telemetry and producing evidence-backed summaries. It does not control vehicles, change cloud resources, or make safety decisions. This repository is a scaffold; no model integration or deployment is implemented.

## Initial design

Use a provider-neutral investigator with small provider adapters. The initial hosted-provider candidates are Groq and Gemini free access, subject to checking current terms, availability, limits, and account eligibility before use. Do not claim a particular free quota or service guarantee without a current provider source. Keep API keys outside the repository and logs; never commit key files, service-account JSON, credentials, or private account details.

Expose only read-only evidence tools. Each tool must have an explicit allowlist of operations and data sources, bounded input size, a timeout, a maximum call count per investigation, and bounded retries. Cache safe repeatable lookups where appropriate, with a documented expiry. On provider failure or exhausted limits, return a clear unavailable/partial result and the evidence already collected; do not fabricate model output or silently switch providers in a way that hides provenance. Label provider and model metadata when known.

Treat telemetry, retrieved text, and model output as untrusted. Use synthetic records, validate tool arguments and output schemas, and prevent tool output from invoking writes or expanding the allowlist. Recommendations remain advisory and require human review.

## Later CPU and GPU evaluation

First benchmark a suitable open model on ordinary CPU hardware using a fixed synthetic workload. Record model/version, hardware, runtime settings, latency, memory use, output quality rubric, and repeatability. Compare results with hosted adapters before considering specialized hardware.

GPU scheduling is a later feasibility gate, not a current requirement. The unupgraded GCP Free Trial cannot be used to provision GPU VMs; do not upgrade billing to bypass this gate. Before any GPU proposal, verify account eligibility, regional GPU quota and availability, API enablement, disk/IP/network quotas, and cost from current provider sources. A Kubernetes experiment would also need an installed NVIDIA device plugin, node taints/tolerations, and pod requests such as `nvidia.com/gpu`; a manifest alone does not make a GPU available. Schedule bounded batch jobs with explicit concurrency, deadlines, and teardown ownership, and compare their resource fit and lifecycle cost with CPU execution.

## Success criteria and evidence

- Every investigation uses synthetic evidence and the read-only allowlist; tool calls stay within recorded size, timeout, retry, and call-count bounds.
- Outputs identify their evidence and provider/model provenance when available, represent unavailable results honestly, and contain no invented findings.
- A CPU benchmark is reproducible from its recorded workload and environment before GPU work is proposed.
- Any future GPU decision includes current eligibility, quota, availability, pricing, scheduling, and teardown evidence. Until then, GPU provisioning remains out of scope.

These criteria describe future acceptance evidence. They do not claim that adapters, benchmarks, GPU manifests, or cloud resources currently exist.
