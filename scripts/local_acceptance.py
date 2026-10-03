"""Bounded local application evidence collector (stdlib only)."""
from __future__ import annotations

import argparse
import ipaddress
import math
import json
import os
import platform
import re
import sys
import time
from datetime import datetime, timezone
from datetime import datetime as DateTime
from urllib.error import URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

MAX_RESPONSE_BYTES = 256 * 1024
MAX_TIMEOUT_SECONDS = 5


def validate_workload_bounds(rides: int, workers: int, duration_seconds: int) -> None:
    if any(type(value) is not int for value in (rides, workers, duration_seconds)):
        raise ValueError("workload bounds must be whole integers")
    if not 1 <= rides <= 100 or not 1 <= workers <= 8 or not 1 <= duration_seconds <= 60:
        raise ValueError("workload bounds are rides 1..100, workers 1..8, duration 1..60 seconds")


def unique_ride_ids(rides: list[dict]) -> None:
    ids = [ride.get("ride_id") for ride in rides]
    if not all(isinstance(i, str) and i for i in ids) or len(ids) != len(set(ids)):
        raise ValueError("ride history must contain unique, non-empty ride_id values")


def _loopback(url: str) -> bool:
    parsed = urlsplit(url)
    if parsed.scheme != "http" or parsed.username or parsed.password or not parsed.hostname:
        return False
    try:
        return ipaddress.ip_address(parsed.hostname).is_loopback
    except ValueError:
        # Avoid arbitrary DNS and DNS-rebinding targets; only the OS localhost alias is accepted.
        return parsed.hostname.casefold() == "localhost"


def collect_endpoint(url: str, timeout: float = 2.0, max_bytes: int = MAX_RESPONSE_BYTES) -> dict:
    if not _loopback(url):
        raise ValueError("endpoint must be an http URL on loopback")
    if not 0 < timeout <= MAX_TIMEOUT_SECONDS or not 1 <= max_bytes <= MAX_RESPONSE_BYTES:
        raise ValueError("timeout/response cap exceeds collector limits")
    start = time.monotonic()
    class RejectRedirect(HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            raise ValueError("endpoint redirected; redirects are not followed")

    request = Request(url, headers={"User-Agent": "ottawa-fleet-platform-acceptance/1"})
    try:
        with build_opener(ProxyHandler({}), RejectRedirect).open(request, timeout=timeout) as response:
            body = response.read(max_bytes + 1)
            if len(body) > max_bytes:
                raise ValueError("endpoint response exceeded byte limit")
            return {"url": url, "status_code": response.status,
                    "content_type": response.headers.get("Content-Type", ""),
                    "response_bytes": len(body), "elapsed_ms": round((time.monotonic() - start) * 1000, 2),
                    "body": body.decode("utf-8", errors="replace")}
    except URLError as exc:
        return {"url": url, "error": str(exc.reason), "elapsed_ms": round((time.monotonic() - start) * 1000, 2)}


def validate_report(report: dict) -> None:
    if not isinstance(report, dict):
        raise ValueError("report must be a JSON object")
    required = {"mode", "status", "observed_at", "workload", "hardware", "endpoints", "observations", "limitations", "resources"}
    missing = sorted(required - report.keys())
    if missing:
        raise ValueError("missing report fields: " + ", ".join(missing))
    if report["mode"] not in {"compose", "mixed-native-docker-non-compose", "native", "docker"}:
        raise ValueError("unknown runtime mode")
    if report["status"] != "accepted" or report["mode"] != "compose":
        raise ValueError("only a complete Compose run can be accepted; partial evidence must say partial")
    if not re.fullmatch(r"[a-f0-9]{40}", report.get("application_commit", "")):
        raise ValueError("application_commit must be the full observed Git commit SHA")
    if set(report["application_commit"]) == {"0"}:
        raise ValueError("application_commit cannot be an all-zero placeholder")
    try:
        observed = DateTime.fromisoformat(report["observed_at"].replace("Z", "+00:00"))
    except (TypeError, ValueError, AttributeError) as exc:
        raise ValueError("observed_at must be a real ISO-8601 timestamp") from exc
    if observed.tzinfo is None:
        raise ValueError("observed_at must include a timezone")
    if not isinstance(report["limitations"], list) or report["limitations"]:
        raise ValueError("accepted reports cannot contain unresolved limitations")
    w, h, o = report["workload"], report["hardware"], report["observations"]
    if not all(isinstance(v, dict) for v in (w, h, o)):
        raise ValueError("workload, hardware and observations must be JSON objects")
    validate_workload_bounds(w.get("rides", 0), w.get("workers", 0), w.get("duration_seconds", 0))
    if type(h.get("cpu_count")) is not int or h["cpu_count"] <= 0 or type(h.get("memory_bytes")) is not int or h["memory_bytes"] <= 0:
        raise ValueError("hardware must contain observed positive cpu_count and memory_bytes")
    expected = {"completed_rides", "duplicate_ride_ids", "backlog_before_restart", "backlog_after_restart", "recovery_seconds", "request_errors", "p95_latency_ms"}
    if expected - o.keys():
        raise ValueError("missing measured observation fields: " + ", ".join(sorted(expected - o.keys())))
    if any(type(o[k]) not in (int, float) or not math.isfinite(o[k]) or o[k] < 0 for k in expected):
        raise ValueError("observation values must be measured non-negative numbers")
    for key in ("completed_rides", "duplicate_ride_ids", "backlog_before_restart", "backlog_after_restart", "request_errors"):
        if type(o[key]) is not int:
            raise ValueError(f"{key} must be an observed whole count")
    if o["completed_rides"] > w["rides"]:
        raise ValueError("completed rides cannot exceed submitted workload")
    if o["duplicate_ride_ids"] != 0:
        raise ValueError("duplicate ride IDs detected")
    if o["backlog_before_restart"] <= o["backlog_after_restart"]:
        raise ValueError("recovery evidence requires backlog to drain after restart")
    required_endpoints = {"ui", "fleet-ready", "fleet", "fleet-metrics", "ride-ready", "rides", "ride-metrics"}
    endpoints = report["endpoints"]
    if not isinstance(endpoints, dict) or required_endpoints - endpoints.keys():
        raise ValueError("required UI, API, readiness, ride-history and metrics endpoint evidence is missing")
    if any(not isinstance(e, dict) or e.get("status_code") != 200 or not isinstance(e.get("body"), str) or not e.get("body") or "error" in e for e in endpoints.values()):
        raise ValueError("every endpoint must have a successful, non-empty real response")
    try:
        for ready_name in ("fleet-ready", "ride-ready"):
            if json.loads(endpoints[ready_name]["body"]).get("status") != "ok":
                raise ValueError(f"{ready_name} did not report ready")
        ride_data = json.loads(endpoints["rides"]["body"])
        unique_ride_ids(ride_data["items"])
        fleet_data = json.loads(endpoints["fleet"]["body"])
        if not isinstance(fleet_data.get("items"), list) or len(fleet_data["items"]) > 100:
            raise ValueError("fleet endpoint lacks a bounded items list")
        if len(ride_data["items"]) > 100:
            raise ValueError("ride history exceeds the bounded API page size")
    except (KeyError, TypeError, json.JSONDecodeError) as exc:
        raise ValueError(f"API response evidence is malformed: {exc}") from exc
    for endpoint in ("fleet-metrics", "ride-metrics"):
        body = endpoints[endpoint]["body"]
        if not any(line and not line.startswith("#") for line in body.splitlines()):
            raise ValueError(f"{endpoint} contains no observed metric samples")
    resources = report["resources"]
    if not isinstance(resources, dict):
        raise ValueError("resources must be a JSON object")
    if resources.get("scope") not in {"assignment-worker", "compose-app-stack"}:
        raise ValueError("resource scope must identify the measured worker or total Compose app stack")
    for key in ("cpu_percent", "memory_bytes"):
        if type(resources.get(key)) not in (int, float) or not math.isfinite(resources[key]) or resources[key] < 0:
            raise ValueError("resources must contain finite non-negative measured cpu_percent and memory_bytes")
    if resources["memory_bytes"] <= 0:
        raise ValueError("resource memory_bytes must be a non-zero observation")


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv[:1] == ["validate"]:
        if len(argv) != 2:
            print("usage: python -m scripts.local_acceptance validate REPORT.json", file=sys.stderr)
            return 2
        try:
            with open(argv[1], encoding="utf-8") as f:
                validate_report(json.load(f))
            print(f"Accepted Compose evidence: {argv[1]}")
            return 0
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            print(f"Acceptance report rejected: {exc}", file=sys.stderr)
            return 2
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", default="acceptance-report.json")
    parser.add_argument("--mode", choices=("compose", "mixed-native-docker-non-compose", "native", "docker"), required=True)
    parser.add_argument("--application-commit", required=True, help="full Git commit SHA of the app source used by the run")
    parser.add_argument("--rides", type=int, required=True)
    parser.add_argument("--workers", type=int, required=True)
    parser.add_argument("--duration-seconds", type=int, required=True)
    parser.add_argument("--completed-rides", type=int, required=True)
    parser.add_argument("--duplicate-ride-ids", type=int, required=True)
    parser.add_argument("--backlog-before-restart", type=int, required=True)
    parser.add_argument("--backlog-after-restart", type=int, required=True)
    parser.add_argument("--recovery-seconds", type=float, required=True)
    parser.add_argument("--request-errors", type=int, required=True, help="observed from fleet_http_requests_total / failure counter")
    parser.add_argument("--p95-latency-ms", type=float, required=True, help="measured from the bounded workload")
    parser.add_argument("--cpu-percent", type=float, required=True, help="measured workload process/container CPU")
    parser.add_argument("--memory-mib", type=float, required=True, help="measured workload process/container memory")
    parser.add_argument("--resource-scope", choices=("assignment-worker", "compose-app-stack"), required=True)
    parser.add_argument("--endpoint", action="append", default=[], metavar="NAME=URL")
    parser.add_argument("--limitation", action="append", default=[])
    args = parser.parse_args(argv)
    try:
        validate_workload_bounds(args.rides, args.workers, args.duration_seconds)
        endpoints = {}
        if len(args.endpoint) > 10:
            raise ValueError("at most 10 loopback endpoints may be collected")
        for item in args.endpoint:
            if "=" not in item:
                raise ValueError("--endpoint must be NAME=http://127.0.0.1:PORT/PATH")
            name, url = item.split("=", 1)
            if not name or name in endpoints:
                raise ValueError("endpoint names must be unique and non-empty")
            endpoints[name] = collect_endpoint(url)
        limitations = list(args.limitation)
        if args.mode != "compose" and "Runtime was not the integrated Compose stack" not in limitations:
            limitations.append("Runtime was not the integrated Compose stack")
        report = {"mode": args.mode, "status": "partial", "application_commit": args.application_commit,
                  "observed_at": datetime.now(timezone.utc).isoformat(),
                  "workload": {"rides": args.rides, "workers": args.workers, "duration_seconds": args.duration_seconds},
                  "hardware": {"cpu_count": os.cpu_count(), "memory_bytes": _memory_bytes()},
                  "endpoints": endpoints,
                  "observations": {"completed_rides": args.completed_rides, "duplicate_ride_ids": args.duplicate_ride_ids,
                                   "backlog_before_restart": args.backlog_before_restart, "backlog_after_restart": args.backlog_after_restart,
                                   "recovery_seconds": args.recovery_seconds, "request_errors": args.request_errors,
                                   "p95_latency_ms": args.p95_latency_ms},
                  "resources": {"scope": args.resource_scope, "cpu_percent": args.cpu_percent,
                                "memory_bytes": round(args.memory_mib * 1024 * 1024)},
                  "host": {"platform": platform.platform()}, "limitations": limitations}
        # A report starts partial. Promote its status only after all acceptance checks pass.
        report["status"] = "partial"
        with open(args.output, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2)
            f.write("\n")
        try:
            if args.mode != "compose" or limitations:
                raise ValueError("runtime mode/limitations do not meet Compose acceptance")
            candidate = dict(report, status="accepted")
            validate_report(candidate)
            report = candidate
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
                f.write("\n")
        except ValueError as exc:
            report["limitations"].append(str(exc))
            with open(args.output, "w", encoding="utf-8") as f:
                json.dump(report, f, indent=2)
                f.write("\n")
            print(f"Partial evidence report written: {args.output}", file=sys.stderr)
            return 2
        print(f"Accepted Compose report written: {args.output}")
        return 0
    except (ValueError, OSError) as exc:
        print(f"Acceptance evidence incomplete; any collected report remains partial: {exc}", file=sys.stderr)
        return 2


def _memory_bytes() -> int:
    # Windows and Linux have different stdlib surfaces; avoid adding psutil.
    if sys.platform == "win32":
        import ctypes
        class MemoryStatus(ctypes.Structure):
            _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                        ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                        ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                        ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                        ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
        status = MemoryStatus()
        status.dwLength = ctypes.sizeof(status)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return status.ullTotalPhys
    else:
        try:
            for line in open("/proc/meminfo", encoding="ascii"):
                if line.startswith("MemTotal:"):
                    return int(line.split()[1]) * 1024
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
