#!/usr/bin/env python3
"""
Kuzu Server Stress Test
=======================
面向 kuzu-test-server 全部 API 接口执行压力测试，输出关键指标和压测报告。

用法:
  python stress_test.py [--base URL] [--concurrency 1,5,10,20,50] [--requests 20] [--timeout 120] [--output report.html]

默认连接 http://127.0.0.1:8000/api/v1
"""

import argparse
import json
import math
import os
import statistics
import sys
import time
import urllib.request
import urllib.error
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class RequestResult:
    name: str
    endpoint: str
    method: str
    status: int
    elapsed_ms: float
    server_ms: float = 0.0
    rows: int = 0
    error: str = ""


@dataclass
class EndpointStats:
    name: str
    endpoint: str
    method: str
    results: list[RequestResult] = field(default_factory=list)

    @property
    def ok_results(self) -> list[RequestResult]:
        return [r for r in self.results if r.error == ""]

    @property
    def error_results(self) -> list[RequestResult]:
        return [r for r in self.results if r.error != ""]

    def latencies(self) -> list[float]:
        return [r.elapsed_ms for r in self.ok_results]

    def server_latencies(self) -> list[float]:
        return [r.server_ms for r in self.ok_results]

    def summary(self) -> dict[str, Any]:
        lats = self.latencies()
        if not lats:
            return {"name": self.name, "endpoint": self.endpoint, "method": self.method,
                    "total": len(self.results), "errors": len(self.error_results), "error_rate": "100.0%"}
        slats = sorted(lats)
        n = len(slats)
        total_ms = sum(slats)
        qps = round(n / (total_ms / 1000 / max(len(lats), 1)), 1) if total_ms > 0 else 0
        return {
            "name": self.name,
            "endpoint": self.endpoint,
            "method": self.method,
            "total": n,
            "errors": len(self.error_results),
            "error_rate": f"{len(self.error_results)/len(self.results)*100:.1f}%",
            "qps": qps,
            "avg_ms": round(statistics.mean(slats), 1),
            "p50_ms": round(slats[int(n * 0.50)], 1),
            "p90_ms": round(slats[int(n * 0.90)], 1),
            "p95_ms": round(slats[min(int(n * 0.95), n - 1)], 1),
            "p99_ms": round(slats[min(int(n * 0.99), n - 1)], 1),
            "min_ms": round(slats[0], 1),
            "max_ms": round(slats[-1], 1),
            "stdev_ms": round(statistics.stdev(slats), 1) if n > 1 else 0.0,
            "avg_server_ms": round(statistics.mean(self.server_latencies()), 1) if self.server_latencies() else 0.0,
        }


# ---------------------------------------------------------------------------
# HTTP helpers
# ---------------------------------------------------------------------------

def http_get(url: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(url)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def http_post(url: str, body: dict, timeout: int = 120) -> dict:
    data = json.dumps(body).encode()
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def http_delete(url: str, timeout: int = 120) -> dict:
    req = urllib.request.Request(url, method="DELETE")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def make_request(method: str, url: str, body: dict | None = None, timeout: int = 120) -> tuple[dict, float]:
    start = time.perf_counter()
    if method == "GET":
        result = http_get(url, timeout)
    elif method == "DELETE":
        result = http_delete(url, timeout)
    else:
        result = http_post(url, body or {}, timeout)
    elapsed = (time.perf_counter() - start) * 1000
    return result, elapsed


# ---------------------------------------------------------------------------
# Test definitions
# ---------------------------------------------------------------------------

QUERIES = {
    "PK Lookup":                'MATCH (n:Account {id: 500000}) RETURN n.name, n.score',
    "Count single table":       'MATCH (n:Account) RETURN count(n)',
    "Filter score>90":          'MATCH (n:Account) WHERE n.score > 90 RETURN count(n)',
    "AVG score":                'MATCH (n:Account) RETURN avg(n.score)',
    "GROUP BY country":         'MATCH (n:Account) RETURN n.country, count(n) ORDER BY count(n) DESC',
    "1-hop Account->Post":      'MATCH (a:Account)-[:AccountCreatesPost]->(p:PostItem) RETURN count(*)',
    "2-hop Acct->Order->Prod":  'MATCH (a:Account)-[:AccountPlacesOrder]->(o:OrderItem)-[:OrderContainsProduct]->(p:Product) RETURN count(*)',
}

GRAPH_QUERIES = {
    "Graph 1-hop Account->Post":    'MATCH (a:Account)-[e:AccountCreatesPost]->(p:PostItem) RETURN a, e, p LIMIT 10',
    "Graph Account->Company":       'MATCH (a:Account)-[e:AccountWorksAtCompany]->(c:Company) RETURN a, e, c LIMIT 10',
    "Graph 2-hop Acct->Order->Prod":'MATCH (a:Account)-[:AccountPlacesOrder]->(o:OrderItem)-[e:OrderContainsProduct]->(p:Product) RETURN a, o, e, p LIMIT 10',
}

# ---------------------------------------------------------------------------
# Endpoint test runners
# ---------------------------------------------------------------------------

def run_single(name: str, method: str, url: str, body: dict | None, timeout: int) -> RequestResult:
    try:
        result, elapsed = make_request(method, url, body, timeout)
        if isinstance(result, list):
            server_ms = 0.0
            rows = len(result)
        else:
            server_ms = result.get("elapsed_ms", 0.0)
            rows = result.get("count", result.get("node_count", 0) + result.get("edge_count", 0))
        return RequestResult(name=name, endpoint=url, method=method,
                             status=200, elapsed_ms=elapsed, server_ms=server_ms, rows=rows)
    except urllib.error.HTTPError as e:
        body_text = ""
        try:
            body_text = e.read().decode()[:200]
        except Exception:
            pass
        return RequestResult(name=name, endpoint=url, method=method,
                             status=e.code, elapsed_ms=0, error=f"HTTP {e.code}: {body_text}")
    except Exception as e:
        return RequestResult(name=name, endpoint=url, method=method,
                             status=0, elapsed_ms=0, error=str(e)[:200])


def run_concurrent(name: str, method: str, url: str, body: dict | None,
                   concurrency: int, num_requests: int, timeout: int) -> EndpointStats:
    stats = EndpointStats(name=name, endpoint=url, method=method)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run_single, name, method, url, body, timeout)
                   for _ in range(num_requests)]
        for f in as_completed(futures):
            stats.results.append(f.result())
    return stats


def run_throughput(name: str, method: str, url: str, body: dict | None,
                   concurrency: int, num_requests: int, timeout: int) -> dict[str, Any]:
    start = time.perf_counter()
    errors = 0
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [pool.submit(run_single, name, method, url, body, timeout)
                   for _ in range(num_requests)]
        for f in as_completed(futures):
            r = f.result()
            if r.error:
                errors += 1
    total_ms = (time.perf_counter() - start) * 1000
    return {
        "name": name,
        "total_requests": num_requests,
        "errors": errors,
        "total_ms": round(total_ms, 0),
        "qps": round(num_requests / (total_ms / 1000), 1),
    }


# ---------------------------------------------------------------------------
# Main test orchestration
# ---------------------------------------------------------------------------

def run_all_tests(base: str, concurrencies: list[int], num_requests: int, timeout: int):
    print_banner()
    all_results: dict[str, Any] = {
        "base_url": base,
        "timestamp": datetime.now().isoformat(),
        "concurrencies": concurrencies,
        "requests_per_test": num_requests,
        "sequential": {},
        "concurrent": {},
        "scaling": {},
        "throughput": {},
        "mixed": {},
    }

    # --- 1. Pre-flight health check ---
    print("\n[Pre-flight] Checking server availability...")
    try:
        r, _ = make_request("GET", f"{base}/health", timeout=5)
        print(f"  Server OK  |  Nodes: {r.get('node_count', '?'):,}  |  Edges: {r.get('edge_count', '?'):,}")
        all_results["server_info"] = r
    except Exception as e:
        print(f"  FATAL: Cannot connect to {base} — {e}")
        sys.exit(1)

    # --- 2. Sequential baseline ---
    print(f"\n{'='*110}")
    print("  SEQUENTIAL BASELINE  (1 request at a time, no concurrency)")
    print(f"{'='*110}")
    seq_stats = run_sequential_tests(base, timeout)
    print_sequential_table(seq_stats)
    all_results["sequential"] = {s.name: s.summary() for s in seq_stats}

    # --- 3. Concurrent tests per endpoint ---
    for c in concurrencies:
        print(f"\n{'='*110}")
        print(f"  CONCURRENT TEST  ({c} workers, {num_requests} requests per endpoint)")
        print(f"{'='*110}")
        conc_stats = run_concurrent_tests(base, c, num_requests, timeout)
        print_concurrent_table(conc_stats)
        all_results["concurrent"][c] = {s.name: s.summary() for s in conc_stats}

    # --- 4. Concurrency scaling (selected endpoints) ---
    print(f"\n{'='*110}")
    print(f"  CONCURRENCY SCALING  (1→{max(concurrencies)} workers, tracking avg latency)")
    print(f"{'='*110}")
    scaling = run_scaling_test(base, concurrencies, num_requests, timeout)
    print_scaling_table(scaling)
    all_results["scaling"] = scaling

    # --- 5. Throughput test ---
    print(f"\n{'='*110}")
    print(f"  THROUGHPUT TEST  (max concurrency {max(concurrencies)}, mixed workload)")
    print(f"{'='*110}")
    tp = run_throughput_tests(base, max(concurrencies), num_requests, timeout)
    print_throughput_table(tp)
    all_results["throughput"] = tp

    # --- 6. Mixed workload ---
    print(f"\n{'='*110}")
    print(f"  MIXED WORKLOAD  (all query types interleaved, {max(concurrencies)} workers)")
    print(f"{'='*110}")
    mixed = run_mixed_workload(base, max(concurrencies), num_requests, timeout)
    print_mixed_table(mixed)
    all_results["mixed"] = {s.name: s.summary() for s in mixed}

    # --- 7. Sustained load ---
    print(f"\n{'='*110}")
    print(f"  SUSTAINED LOAD  (60s continuous, {max(concurrencies)} workers)")
    print(f"{'='*110}")
    sustained = run_sustained_load(base, max(concurrencies), 60, timeout)
    print_sustained_table(sustained)
    all_results["sustained"] = sustained

    return all_results


def run_sequential_tests(base: str, timeout: int) -> list[EndpointStats]:
    tests = define_endpoints(base)
    results = []
    for name, method, url, body in tests:
        stats = EndpointStats(name=name, endpoint=url, method=method)
        r = run_single(name, method, url, body, timeout)
        stats.results.append(r)
        results.append(stats)
    return results


def run_concurrent_tests(base: str, c: int, n: int, timeout: int) -> list[EndpointStats]:
    tests = define_endpoints(base)
    results = []
    for name, method, url, body in tests:
        stats = run_concurrent(name, method, url, body, c, n, timeout)
        results.append(stats)
    return results


def define_endpoints(base: str) -> list[tuple[str, str, str, dict | None]]:
    tests = [
        ("GET /health",           "GET",    f"{base}/health",              None),
        ("GET /schema",           "GET",    f"{base}/schema",              None),
        ("GET /schema/nodes",     "GET",    f"{base}/schema/nodes",        None),
        ("GET /schema/edges",     "GET",    f"{base}/schema/edges",        None),
        ("GET /query/history",    "GET",    f"{base}/query/history",       None),
        ("DELETE /query/history", "DELETE", f"{base}/query/history",       None),
    ]
    for qname, cypher in QUERIES.items():
        tests.append((f"POST /query — {qname}", "POST", f"{base}/query", {"query": cypher}))
    for qname, cypher in QUERIES.items():
        tests.append((f"POST /query/safe — {qname}", "POST", f"{base}/query/safe", {"query": cypher}))
    for qname, cypher in GRAPH_QUERIES.items():
        tests.append((f"POST /query/graph — {qname}", "POST", f"{base}/query/graph", {"query": cypher}))
    return tests


def run_scaling_test(base: str, concurrencies: list[int], n: int, timeout: int) -> dict:
    scaling_endpoints = [
        ("GET /health",           "GET",    f"{base}/health",              None),
        ("POST /query — PK Lookup", "POST", f"{base}/query",              {"query": QUERIES["PK Lookup"]}),
        ("POST /query — Count single table", "POST", f"{base}/query",     {"query": QUERIES["Count single table"]}),
        ("POST /query/safe — Count single table", "POST", f"{base}/query/safe", {"query": QUERIES["Count single table"]}),
        ("GET /schema",           "GET",    f"{base}/schema",              None),
    ]
    data = {}
    for name, method, url, body in scaling_endpoints:
        data[name] = {}
        for c in concurrencies:
            stats = run_concurrent(name, method, url, body, c, n, timeout)
            data[name][c] = stats.summary()
    return data


def run_throughput_tests(base: str, c: int, n: int, timeout: int) -> list[dict]:
    tests = [
        ("GET /health",           "GET",    f"{base}/health",              None),
        ("POST /query (mixed)",   "POST",   f"{base}/query",              None),
        ("POST /query/safe (mixed)", "POST", f"{base}/query/safe",        None),
        ("GET /schema",           "GET",    f"{base}/schema",              None),
    ]
    results = []
    for name, method, url, body in tests:
        if "mixed" in name:
            tp = run_mixed_throughput(name, method, url, c, n, timeout)
        else:
            tp = run_throughput(name, method, url, body, c, n, timeout)
        results.append(tp)
    return results


def run_mixed_throughput(name: str, method: str, url: str, c: int, n: int, timeout: int) -> dict:
    cyphers = list(QUERIES.values())
    start = time.perf_counter()
    errors = 0
    with ThreadPoolExecutor(max_workers=c) as pool:
        futures = []
        for i in range(n):
            body = {"query": cyphers[i % len(cyphers)]}
            futures.append(pool.submit(run_single, name, method, url, body, timeout))
        for f in as_completed(futures):
            r = f.result()
            if r.error:
                errors += 1
    total_ms = (time.perf_counter() - start) * 1000
    return {"name": name, "total_requests": n, "errors": errors,
            "total_ms": round(total_ms, 0), "qps": round(n / (total_ms / 1000), 1)}


def run_mixed_workload(base: str, c: int, n: int, timeout: int) -> list[EndpointStats]:
    all_tasks = []
    for qname, cypher in QUERIES.items():
        for _ in range(n):
            all_tasks.append((f"POST /query — {qname}", "POST", f"{base}/query", {"query": cypher}))
    for qname, cypher in QUERIES.items():
        for _ in range(n // 2):
            all_tasks.append((f"POST /query/safe — {qname}", "POST", f"{base}/query/safe", {"query": cypher}))
    for qname, cypher in GRAPH_QUERIES.items():
        for _ in range(n // 2):
            all_tasks.append((f"POST /query/graph — {qname}", "POST", f"{base}/query/graph", {"query": cypher}))

    results_by_name: dict[str, EndpointStats] = {}
    with ThreadPoolExecutor(max_workers=c) as pool:
        futures = {pool.submit(run_single, name, method, url, body, timeout): name
                   for name, method, url, body in all_tasks}
        for f in as_completed(futures):
            name = futures[f]
            r = f.result()
            if name not in results_by_name:
                results_by_name[name] = EndpointStats(name=name, endpoint=r.endpoint, method=r.method)
            results_by_name[name].results.append(r)

    ordered = []
    for qname in QUERIES:
        key = f"POST /query — {qname}"
        if key in results_by_name:
            ordered.append(results_by_name[key])
    for qname in QUERIES:
        key = f"POST /query/safe — {qname}"
        if key in results_by_name:
            ordered.append(results_by_name[key])
    for qname in GRAPH_QUERIES:
        key = f"POST /query/graph — {qname}"
        if key in results_by_name:
            ordered.append(results_by_name[key])
    return ordered


def run_sustained_load(base: str, c: int, duration_s: int, timeout: int) -> dict:
    cyphers = list(QUERIES.values())
    url = f"{base}/query"
    latencies: list[float] = []
    errors = 0
    total_req = 0
    deadline = time.perf_counter() + duration_s

    def _worker(idx: int) -> RequestResult:
        body = {"query": cyphers[idx % len(cyphers)]}
        return run_single("sustained", "POST", url, body, timeout)

    with ThreadPoolExecutor(max_workers=c) as pool:
        batch_size = c * 2
        while time.perf_counter() < deadline:
            futures = [pool.submit(_worker, total_req + i) for i in range(batch_size)]
            for f in as_completed(futures):
                r = f.result()
                total_req += 1
                if r.error:
                    errors += 1
                else:
                    latencies.append(r.elapsed_ms)

    slats = sorted(latencies)
    n = len(slats)
    actual_duration = duration_s
    return {
        "duration_s": actual_duration,
        "total_requests": total_req,
        "errors": errors,
        "error_rate": f"{errors/total_req*100:.2f}%" if total_req else "0%",
        "qps": round(total_req / actual_duration, 1),
        "avg_ms": round(statistics.mean(slats), 1) if slats else 0,
        "p50_ms": round(slats[int(n * 0.50)], 1) if slats else 0,
        "p90_ms": round(slats[int(n * 0.90)], 1) if slats else 0,
        "p95_ms": round(slats[min(int(n * 0.95), n - 1)], 1) if slats else 0,
        "p99_ms": round(slats[min(int(n * 0.99), n - 1)], 1) if slats else 0,
        "min_ms": round(slats[0], 1) if slats else 0,
        "max_ms": round(slats[-1], 1) if slats else 0,
        "stdev_ms": round(statistics.stdev(slats), 1) if n > 1 else 0,
    }


# ---------------------------------------------------------------------------
# Console output
# ---------------------------------------------------------------------------

def print_banner():
    print()
    print("  ╔═══════════════════════════════════════════════════════════╗")
    print("  ║            K U Z U   S E R V E R   S T R E S S           ║")
    print("  ║                     T E S T   S U I T E                  ║")
    print("  ╚═══════════════════════════════════════════════════════════╝")


def print_sequential_table(stats_list: list[EndpointStats]):
    print(f"  {'Endpoint':<45} {'Latency(ms)':<14} {'Server(ms)':<14} {'Rows':<8} {'Status'}")
    print(f"  {'-'*95}")
    for s in stats_list:
        r = s.results[0] if s.results else None
        if r and not r.error:
            print(f"  {s.name:<45} {r.elapsed_ms:<14.1f} {r.server_ms:<14.1f} {r.rows:<8} OK")
        else:
            err = r.error[:40] if r else "no result"
            print(f"  {s.name:<45} {'—':<14} {'—':<14} {'—':<8} ERR: {err}")


def print_concurrent_table(stats_list: list[EndpointStats]):
    print(f"  {'Endpoint':<45} {'avg':<8} {'p50':<8} {'p90':<8} {'p95':<8} {'p99':<8} {'min':<8} {'max':<8} {'err':<6} {'qps'}")
    print(f"  {'-'*120}")
    for s in stats_list:
        sm = s.summary()
        if "avg_ms" in sm:
            ok = sm["total"]
            errs = sm["errors"]
            total = ok + errs
            lats = s.latencies()
            qps = round(total / (sum(lats) / 1000 / max(ok, 1)), 1) if lats else 0
            print(f"  {sm['name']:<45} {sm['avg_ms']:<8.1f} {sm['p50_ms']:<8.1f} "
                  f"{sm['p90_ms']:<8.1f} {sm['p95_ms']:<8.1f} {sm['p99_ms']:<8.1f} "
                  f"{sm['min_ms']:<8.1f} {sm['max_ms']:<8.1f} {errs:<6} {qps}")
        else:
            print(f"  {sm['name']:<45} {'FAILED':<8} {'':<8} {'':<8} {'':<8} {'':<8} {'':<8} {'':<8} {sm['errors']:<6}")


def print_scaling_table(scaling: dict):
    concurrencies = sorted(set(c for v in scaling.values() for c in v.keys()))
    header = f"  {'Endpoint':<45}" + "".join(f"{'C='+str(c):<10}" for c in concurrencies)
    print(header)
    print(f"  {'-'*len(header)}")
    for name, by_c in scaling.items():
        row = f"  {name:<45}"
        for c in concurrencies:
            sm = by_c.get(c, {})
            avg = sm.get("avg_ms", "—")
            row += f"{avg if isinstance(avg, str) else f'{avg:.1f}':<10}"
        print(row)


def print_throughput_table(results: list[dict]):
    print(f"  {'Endpoint':<40} {'Requests':<12} {'Errors':<10} {'Time(ms)':<12} {'QPS'}")
    print(f"  {'-'*90}")
    for r in results:
        print(f"  {r['name']:<40} {r['total_requests']:<12} {r['errors']:<10} {r['total_ms']:<12.0f} {r['qps']}")


def print_mixed_table(stats_list: list[EndpointStats]):
    print(f"  {'Endpoint':<50} {'avg':<8} {'p50':<8} {'p95':<8} {'p99':<8} {'reqs':<8} {'errs'}")
    print(f"  {'-'*105}")
    for s in stats_list:
        sm = s.summary()
        if "avg_ms" in sm:
            print(f"  {sm['name']:<50} {sm['avg_ms']:<8.1f} {sm['p50_ms']:<8.1f} "
                  f"{sm['p95_ms']:<8.1f} {sm['p99_ms']:<8.1f} {sm['total']:<8} {sm['errors']}")
        else:
            print(f"  {sm['name']:<50} {'FAILED':<8} {'':<8} {'':<8} {'':<8} {sm['total']:<8} {sm['errors']}")


def print_sustained_table(data: dict):
    print(f"  Duration:       {data['duration_s']}s")
    print(f"  Total requests: {data['total_requests']}")
    print(f"  Errors:         {data['errors']} ({data['error_rate']})")
    print(f"  Throughput:     {data['qps']} req/s")
    print(f"  Latency avg:    {data['avg_ms']} ms")
    print(f"  Latency p50:    {data['p50_ms']} ms")
    print(f"  Latency p90:    {data['p90_ms']} ms")
    print(f"  Latency p95:    {data['p95_ms']} ms")
    print(f"  Latency p99:    {data['p99_ms']} ms")
    print(f"  Latency min:    {data['min_ms']} ms")
    print(f"  Latency max:    {data['max_ms']} ms")
    print(f"  Stdev:          {data['stdev_ms']} ms")


# ---------------------------------------------------------------------------
# HTML report generation
# ---------------------------------------------------------------------------

def generate_html_report(data: dict[str, Any]) -> str:
    ts = data["timestamp"]
    base = data["base_url"]
    server = data.get("server_info", {})
    concurrent_levels = data["concurrencies"]
    max_c = max(concurrent_levels)
    sustained = data.get("sustained", {})

    # Build sequential rows
    seq_rows = ""
    for name, sm in data["sequential"].items():
        if "avg_ms" in sm:
            seq_rows += f"""<tr>
                <td>{sm['name']}</td><td>{sm['method']}</td>
                <td>{sm['avg_ms']}</td><td>{sm.get('avg_server_ms','—')}</td>
                <td>{sm.get('min_ms','—')}</td><td>{sm.get('max_ms','—')}</td>
                <td>{sm['errors']}</td>
            </tr>"""
        else:
            seq_rows += f"""<tr class="error-row">
                <td>{sm['name']}</td><td>{sm['method']}</td>
                <td colspan="4">FAILED — {sm.get('error_rate','100%')}</td><td>{sm['errors']}</td>
            </tr>"""

    # Build concurrent rows (for max concurrency)
    conc_data = data["concurrent"].get(max_c, {})
    conc_rows = ""
    for name, sm in conc_data.items():
        if "avg_ms" in sm:
            conc_rows += f"""<tr>
                <td>{sm['name']}</td><td>{sm['method']}</td>
                <td>{sm['avg_ms']}</td><td>{sm['p50_ms']}</td><td>{sm['p90_ms']}</td>
                <td>{sm['p95_ms']}</td><td>{sm['p99_ms']}</td>
                <td>{sm['min_ms']}</td><td>{sm['max_ms']}</td><td>{sm['stdev_ms']}</td>
                <td>{sm['qps']}</td><td>{sm['error_rate']}</td>
            </tr>"""
        else:
            conc_rows += f"""<tr class="error-row">
                <td>{sm['name']}</td><td>{sm['method']}</td>
                <td colspan="10">FAILED</td><td>{sm.get('error_rate','100%')}</td>
            </tr>"""

    # Build scaling table
    scaling_header = "".join(f"<th>C={c}</th>" for c in sorted(concurrent_levels))
    scaling_rows = ""
    for name, by_c in data.get("scaling", {}).items():
        cells = f"<td>{name}</td>"
        for c in sorted(concurrent_levels):
            sm = by_c.get(c, {})
            avg = sm.get("avg_ms", "—")
            cells += f"<td>{avg if isinstance(avg, str) else f'{avg:.1f}'}</td>"
        scaling_rows += f"<tr>{cells}</tr>"

    # Throughput table
    tp_rows = ""
    for r in data.get("throughput", []):
        tp_rows += f"""<tr>
            <td>{r['name']}</td><td>{r['total_requests']}</td>
            <td>{r['errors']}</td><td>{r['total_ms']}</td><td>{r['qps']}</td>
        </tr>"""

    # Mixed workload
    mixed_rows = ""
    for name, sm in data.get("mixed", {}).items():
        if "avg_ms" in sm:
            mixed_rows += f"""<tr>
                <td>{sm['name']}</td>
                <td>{sm['avg_ms']}</td><td>{sm['p50_ms']}</td><td>{sm['p95_ms']}</td>
                <td>{sm['p99_ms']}</td><td>{sm['total']}</td><td>{sm['errors']}</td>
            </tr>"""

    # Conclusions
    conclusions = generate_conclusions(data)

    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Kuzu Server 压测报告 — {ts}</title>
<style>
  :root {{ --bg: #0d1117; --card: #161b22; --border: #30363d; --text: #c9d1d9;
           --accent: #58a6ff; --green: #3fb950; --red: #f85149; --yellow: #d29922; --dim: #8b949e; }}
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ font-family: -apple-system, 'Segoe UI', Helvetica, Arial, sans-serif;
          background: var(--bg); color: var(--text); line-height: 1.6; padding: 2rem; }}
  h1 {{ color: var(--accent); font-size: 1.8rem; margin-bottom: .25rem; }}
  h2 {{ color: var(--accent); font-size: 1.3rem; margin: 2rem 0 .75rem; border-bottom: 1px solid var(--border); padding-bottom: .25rem; }}
  .meta {{ color: var(--dim); margin-bottom: 1.5rem; }}
  .card {{ background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 1.25rem; margin-bottom: 1.5rem; overflow-x: auto; }}
  .stats-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(140px,1fr)); gap: 1rem; margin-bottom: 1rem; }}
  .stat {{ text-align: center; padding: .75rem; background: var(--bg); border-radius: 6px; }}
  .stat .value {{ font-size: 1.5rem; font-weight: 700; color: var(--green); }}
  .stat .value.warn {{ color: var(--yellow); }}
  .stat .value.bad {{ color: var(--red); }}
  .stat .label {{ font-size: .8rem; color: var(--dim); }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85rem; }}
  th {{ background: var(--bg); color: var(--dim); text-align: left; padding: .5rem .6rem;
        border-bottom: 2px solid var(--border); white-space: nowrap; }}
  td {{ padding: .4rem .6rem; border-bottom: 1px solid var(--border); white-space: nowrap; }}
  tr:hover {{ background: rgba(88,166,255,.06); }}
  .error-row {{ color: var(--red); }}
  .conclusion {{ background: var(--card); border-left: 4px solid var(--accent); padding: 1rem 1.25rem; margin-bottom: .75rem; border-radius: 0 6px 6px 0; }}
  .conclusion.warn {{ border-left-color: var(--yellow); }}
  .conclusion.bad {{ border-left-color: var(--red); }}
  .conclusion h3 {{ color: var(--accent); font-size: 1rem; margin-bottom: .25rem; }}
  .conclusion.warn h3 {{ color: var(--yellow); }}
  .conclusion.bad h3 {{ color: var(--red); }}
</style>
</head>
<body>
<h1>Kuzu Server 压力测试报告</h1>
<div class="meta">
  生成时间: {ts}<br>
  目标服务: {base}<br>
  数据库: {server.get('db_path','—')} ｜ 节点: {server.get('node_count','?'):,} ｜ 边: {server.get('edge_count','?'):,}<br>
  并发级别: {concurrent_levels} ｜ 每测试请求数: {data['requests_per_test']}
</div>

<h2>关键指标概览</h2>
<div class="card">
  <div class="stats-grid">
    <div class="stat"><div class="value">{sustained.get('qps', '—')}</div><div class="label">吞吐量 (req/s)</div></div>
    <div class="stat"><div class="value">{sustained.get('avg_ms', '—')}</div><div class="label">平均延迟 (ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('p95_ms', '—')}</div><div class="label">P95 延迟 (ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('p99_ms', '—')}</div><div class="label">P99 延迟 (ms)</div></div>
    <div class="stat"><div class="value {'warn' if sustained.get('errors',0) > 0 else ''}">{sustained.get('error_rate', '—')}</div><div class="label">错误率</div></div>
    <div class="stat"><div class="value">{sustained.get('total_requests', '—')}</div><div class="label">60s 总请求</div></div>
  </div>
</div>

<h2>1. 顺序基线 (Sequential Baseline)</h2>
<div class="card">
<table>
<tr><th>接口</th><th>方法</th><th>延迟(ms)</th><th>服务端(ms)</th><th>最小(ms)</th><th>最大(ms)</th><th>错误</th></tr>
{seq_rows}
</table>
</div>

<h2>2. 并发测试 (Concurrency={max_c})</h2>
<div class="card">
<table>
<tr><th>接口</th><th>方法</th><th>avg</th><th>p50</th><th>p90</th><th>p95</th><th>p99</th><th>min</th><th>max</th><th>stdev</th><th>QPS</th><th>错误率</th></tr>
{conc_rows}
</table>
</div>

<h2>3. 并发扩展性 (Concurrency Scaling)</h2>
<div class="card">
<table>
<tr><th>接口</th>{scaling_header}</tr>
{scaling_rows}
</table>
</div>

<h2>4. 吞吐量测试</h2>
<div class="card">
<table>
<tr><th>接口</th><th>请求数</th><th>错误</th><th>耗时(ms)</th><th>QPS</th></tr>
{tp_rows}
</table>
</div>

<h2>5. 混合负载</h2>
<div class="card">
<table>
<tr><th>接口</th><th>avg(ms)</th><th>p50(ms)</th><th>p95(ms)</th><th>p99(ms)</th><th>QPS</th><th>请求数</th><th>错误</th></tr>
{mixed_rows}
</table>
</div>

<h2>6. 持续负载 (60s)</h2>
<div class="card">
  <div class="stats-grid">
    <div class="stat"><div class="value">{sustained.get('qps','—')}</div><div class="label">QPS</div></div>
    <div class="stat"><div class="value">{sustained.get('total_requests','—')}</div><div class="label">总请求</div></div>
    <div class="stat"><div class="value">{sustained.get('avg_ms','—')}</div><div class="label">avg(ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('p50_ms','—')}</div><div class="label">p50(ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('p95_ms','—')}</div><div class="label">p95(ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('p99_ms','—')}</div><div class="label">p99(ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('min_ms','—')}</div><div class="label">min(ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('max_ms','—')}</div><div class="label">max(ms)</div></div>
    <div class="stat"><div class="value">{sustained.get('stdev_ms','—')}</div><div class="label">stdev(ms)</div></div>
    <div class="stat"><div class="value {'warn' if sustained.get('errors',0) > 0 else ''}">{sustained.get('error_rate','—')}</div><div class="label">错误率</div></div>
  </div>
</div>

<h2>7. 压测结论</h2>
{conclusions}

</body>
</html>"""
    return html


def generate_conclusions(data: dict) -> str:
    conclusions = ""
    sustained = data.get("sustained", {})
    max_c = max(data["concurrencies"])
    conc = data.get("concurrent", {}).get(max_c, {})
    scaling = data.get("scaling", {})

    # 1. Throughput assessment
    qps = sustained.get("qps", 0)
    if qps >= 100:
        conclusions += f'<div class="conclusion"><h3>吞吐量: 优秀</h3><p>持续负载 QPS={qps}，服务吞吐能力充足，可支撑生产级查询负载。</p></div>'
    elif qps >= 50:
        conclusions += f'<div class="conclusion warn"><h3>吞吐量: 良好</h3><p>持续负载 QPS={qps}，可满足中等并发场景，高并发下需关注延迟变化。</p></div>'
    else:
        conclusions += f'<div class="conclusion bad"><h3>吞吐量: 待优化</h3><p>持续负载 QPS={qps}，建议优化连接池大小或数据库 buffer_pool 配置。</p></div>'

    # 2. Latency assessment
    p95 = sustained.get("p95_ms", 9999)
    if p95 < 100:
        conclusions += f'<div class="conclusion"><h3>延迟: 优秀</h3><p>P95={p95}ms，绝大多数请求在可接受范围内。</p></div>'
    elif p95 < 500:
        conclusions += f'<div class="conclusion warn"><h3>延迟: 良好</h3><p>P95={p95}ms，多数请求在 500ms 内完成。复杂查询（多跳遍历）延迟较高属正常现象。</p></div>'
    else:
        conclusions += f'<div class="conclusion bad"><h3>延迟: 需关注</h3><p>P95={p95}ms，部分查询延迟过高，建议检查慢查询并优化索引/schema。</p></div>'

    # 3. Error rate
    err_rate = sustained.get("error_rate", "0%")
    err_count = sustained.get("errors", 0)
    if err_count == 0:
        conclusions += '<div class="conclusion"><h3>稳定性: 优秀</h3><p>压测期间零错误，服务稳定性良好。</p></div>'
    else:
        conclusions += f'<div class="conclusion bad"><h3>稳定性: 存在错误</h3><p>错误率={err_rate}，需排查超时或并发竞争问题。</p></div>'

    # 4. Concurrency scaling
    has_degradation = False
    for name, by_c in scaling.items():
        avgs = [sm.get("avg_ms", 0) for sm in by_c.values() if "avg_ms" in sm]
        if len(avgs) >= 2 and avgs[-1] > avgs[0] * 3:
            has_degradation = True
            break
    if has_degradation:
        conclusions += '<div class="conclusion warn"><h3>并发扩展性: 存在退化</h3><p>高并发下部分接口延迟增长超过 3 倍，连接池或内部锁可能成为瓶颈。建议评估 KUZU_POOL_SIZE 和 KUZU_BUFFER_POOL_MB 参数。</p></div>'
    else:
        conclusions += '<div class="conclusion"><h3>并发扩展性: 良好</h3><p>延迟随并发增长在合理范围内，连接池配置适当。</p></div>'

    # 5. /query/safe vs /query comparison
    safe_avgs = [sm["avg_ms"] for n, sm in conc.items() if "/query/safe" in n and "avg_ms" in sm]
    query_avgs = [sm["avg_ms"] for n, sm in conc.items() if "/query" in n and "/safe" not in n and "/graph" not in n and "avg_ms" in sm]
    if safe_avgs and query_avgs:
        safe_avg = statistics.mean(safe_avgs)
        query_avg = statistics.mean(query_avgs)
        ratio = safe_avg / query_avg if query_avg > 0 else 0
        if ratio > 2:
            conclusions += f'<div class="conclusion warn"><h3>/query/safe vs /query: {ratio:.1f}x 开销</h3><p>线程安全模式平均延迟 {safe_avg:.1f}ms vs 普通模式 {query_avg:.1f}ms，全局锁导致吞吐下降明显。写操作使用 /safe，读操作建议使用 /query。</p></div>'
        else:
            conclusions += f'<div class="conclusion"><h3>/query/safe vs /query: {ratio:.1f}x 开销</h3><p>线程安全模式额外开销可控，写场景可放心使用。</p></div>'

    # 6. Query pattern analysis
    heavy_queries = []
    for name, sm in conc.items():
        if "avg_ms" in sm and sm["avg_ms"] > 500:
            heavy_queries.append(f"{name} ({sm['avg_ms']}ms)")
    if heavy_queries:
        conclusions += f'<div class="conclusion warn"><h3>慢查询识别</h3><p>以下查询在高并发下平均延迟超过 500ms：{", ".join(heavy_queries)}。建议优化查询结构或增加索引。</p></div>'
    else:
        conclusions += '<div class="conclusion"><h3>查询性能: 全部达标</h3><p>所有查询在高并发下平均延迟均在 500ms 以内。</p></div>'

    return conclusions


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Kuzu Server Stress Test Suite")
    parser.add_argument("--base", default="http://127.0.0.1:8000/api/v1", help="API base URL")
    parser.add_argument("--concurrency", default="1,5,10,20,50", help="Comma-separated concurrency levels")
    parser.add_argument("--requests", type=int, default=20, help="Requests per endpoint per test")
    parser.add_argument("--timeout", type=int, default=120, help="HTTP request timeout in seconds")
    parser.add_argument("--output", default="stress_report.html", help="HTML report output path")
    args = parser.parse_args()

    base = args.base.rstrip("/")
    concurrencies = [int(x) for x in args.concurrency.split(",")]
    num_requests = args.requests

    results = run_all_tests(base, concurrencies, num_requests, args.timeout)

    # Write HTML report
    report_dir = os.path.dirname(os.path.abspath(__file__))
    output_path = os.path.join(report_dir, args.output)
    html = generate_html_report(results)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"\n{'='*110}")
    print(f"  REPORT: {output_path}")
    print(f"{'='*110}\n")


if __name__ == "__main__":
    main()
