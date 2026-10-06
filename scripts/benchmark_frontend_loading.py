"""Compare resident and on-demand search on one frozen frontend snapshot.

Uses two temporary builds, isolated FastAPI/SQLite instances, and fresh browser
contexts. The optimized build must match the current production dist byte for
byte. Nothing in production src, dist, configuration or data is changed.
"""

from __future__ import annotations

import argparse
import gzip
import hashlib
import json
import os
import platform
import shutil
import socket
import statistics
import subprocess
import tempfile
import threading
import time
from collections import Counter
from contextlib import ExitStack, contextmanager
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote, urlparse

import uvicorn
from fastapi.responses import JSONResponse
from playwright.sync_api import expect, sync_playwright

from career_radar.api import create_app

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
LAYOUT = Path("src/components/layout/AppLayout.tsx")
CONDITIONAL = '{commandOpen && <Suspense fallback={<div role="status"'
RESIDENT = '{<Suspense fallback={<div role="status"'


def digest_tree(directory: Path) -> dict[str, str]:
    return {
        path.relative_to(directory).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(directory.rglob("*"))
        if path.is_file()
    }


@contextmanager
def dependency_link(link: Path):
    """Share installed packages; remove only the link, never the target."""
    target = WEB / "node_modules"
    if os.name == "nt":
        subprocess.run(
            ["cmd.exe", "/c", "mklink", "/J", str(link), str(target)],
            check=True,
            capture_output=True,
        )
    else:
        link.symlink_to(target, target_is_directory=True)
    assert link.resolve() == target.resolve()
    try:
        yield
    finally:
        if os.name == "nt":
            os.rmdir(link)
        else:
            link.unlink()


def build(snapshot: Path, out: Path, temporary: Path) -> dict:
    assert out.resolve().is_relative_to(temporary.resolve())
    node = shutil.which("node")
    if not node:
        raise RuntimeError("Existing Node installation is required")
    command = [
        node,
        str(WEB / "node_modules/vite/bin/vite.js"),
        "build",
        "--configLoader",
        "runner",
        "--outDir",
        str(out),
        "--emptyOutDir",
    ]
    started = time.perf_counter()
    result = subprocess.run(command, cwd=snapshot, capture_output=True, text=True, encoding="utf-8")
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return {"seconds": round(time.perf_counter() - started, 3), "exitCode": result.returncode}


@contextmanager
def isolated_server(directory: Path, dist: Path):
    directory.mkdir()
    config = directory / "config.yaml"
    config.write_text(
        """app:
  database_path: data/benchmark.db
crawler:
  render_mode: never
  user_agent: Career Radar isolated loading benchmark
llm:
  provider: mimo
  model: offline-disabled
smtp:
  enabled: false
companies:
  - name: Offline benchmark company
    url: https://example.com/careers
""",
        encoding="utf-8",
    )
    app = create_app(config, web_dist=dist)
    model_attempts = []

    def forbidden_model(*_args):
        model_attempts.append("unexpected gateway construction")
        raise RuntimeError("Models are disabled during the loading benchmark")

    app.state.growth_manager.gateway_factory = forbidden_model

    @app.middleware("http")
    async def read_only(request, call_next):
        if request.method != "GET":
            return JSONResponse({"detail": "Benchmark accepts GET only"}, status_code=405)
        return await call_next(request)

    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 15
    while not server.started and time.monotonic() < deadline:
        time.sleep(0.05)
    if not server.started:
        server.should_exit = True
        thread.join(timeout=5)
        raise RuntimeError("Temporary API failed to start")
    try:
        yield f"http://127.0.0.1:{port}", model_attempts
    finally:
        server.should_exit = True
        thread.join(timeout=30)
        assert not thread.is_alive(), "Temporary API did not stop"
        assert not model_attempts, model_attempts


def resource_summary(requests: list[dict], dist: Path) -> dict:
    scripts = sorted({item["path"] for item in requests if urlparse(item["path"]).path.endswith(".js")})
    assets = []
    for url in scripts:
        path = dist / unquote(urlparse(url).path).lstrip("/")
        assert path.resolve().is_relative_to(dist.resolve())
        data = path.read_bytes()
        assets.append({
            "path": url,
            "rawBytes": len(data),
            "gzipBytes": len(gzip.compress(data, compresslevel=9, mtime=0)),
            "sha256": hashlib.sha256(data).hexdigest(),
        })
    api = [item for item in requests if item["path"].startswith("/api/")]
    return {
        "js": assets,
        "jsFileCount": len(assets),
        "jsRawBytes": sum(item["rawBytes"] for item in assets),
        "jsGzipBytes": sum(item["gzipBytes"] for item in assets),
        "apiRequests": api,
        "apiRequestCount": len(api),
        "apiCountsByPath": dict(sorted(Counter(item["path"] for item in api).items())),
    }


def sample(browser, origin: str, dist: Path, repetition: int) -> dict:
    context = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
    requests = []
    errors = []
    forbidden = []

    def route_request(route):
        request = route.request
        if not request.url.startswith(origin + "/") or request.method != "GET":
            forbidden.append({"url": request.url, "method": request.method})
            route.abort()
        else:
            route.continue_()

    context.route("**/*", route_request)
    page = context.new_page()
    page.on("pageerror", lambda error: errors.append(str(error)))

    def record(response):
        parsed = urlparse(response.url)
        path = parsed.path + ("?" + parsed.query if parsed.query else "")
        requests.append({"method": response.request.method, "path": path, "status": response.status})

    page.on("response", record)
    try:
        started = time.perf_counter()
        page.goto(origin, wait_until="networkidle")
        expect(page.get_by_role("heading", name="今日岗位机会", exact=True)).to_be_visible()
        page.wait_for_timeout(250)
        home_ready_ms = (time.perf_counter() - started) * 1000
        initial_requests = list(requests)
        initial = resource_summary(initial_requests, dist)
        timing = page.evaluate("""() => {
          const nav = performance.getEntriesByType('navigation')[0];
          const fcp = performance.getEntriesByName('first-contentful-paint')[0];
          return {domContentLoadedMs:nav.domContentLoadedEventEnd,
            loadMs:nav.loadEventEnd,firstContentfulPaintMs:fcp?.startTime ?? null};
        }""")
        started = time.perf_counter()
        page.get_by_role("button", name="打开全局搜索", exact=True).click()
        expect(page.get_by_role("combobox")).to_be_visible()
        search_visible_ms = (time.perf_counter() - started) * 1000
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(250)
        additional = resource_summary(requests[len(initial_requests):], dist)
        total = resource_summary(requests, dist)
        assert not errors, errors
        assert not forbidden, forbidden
        assert all(item["status"] < 400 for item in requests), requests
        return {
            "repetition": repetition,
            "initial": initial,
            "searchOpenedAdditional": additional,
            "afterSearchTotal": total,
            "labTiming": {
                "homeReadyIncludingIdleWaitMs": round(home_ready_ms, 3),
                "clickToSearchVisibleMs": round(search_visible_ms, 3),
                **timing,
            },
            "pageErrors": errors,
            "blockedExternalOrMutatingRequests": forbidden,
        }
    finally:
        context.close()


def medians(samples: list[dict]) -> dict:
    result = {}
    for phase in ("initial", "searchOpenedAdditional", "afterSearchTotal"):
        result[phase] = {
            name: statistics.median(item[phase][name] for item in samples)
            for name in ("jsFileCount", "jsRawBytes", "jsGzipBytes", "apiRequestCount")
        }
    result["labTiming"] = {
        name: statistics.median(item["labTiming"][name] for item in samples)
        for name in ("homeReadyIncludingIdleWaitMs", "clickToSearchVisibleMs", "domContentLoadedMs", "loadMs")
    }
    return result


def run(output: Path, repetitions: int):
    if repetitions < 3:
        raise ValueError("At least three repetitions per variant are required")
    current_dist = WEB / "dist"
    production_before = digest_tree(current_dist)
    with tempfile.TemporaryDirectory(prefix="career-loading-comparison-") as temporary_name:
        temporary = Path(temporary_name)
        snapshot = temporary / "web"
        shutil.copytree(WEB, snapshot, ignore=shutil.ignore_patterns("node_modules", "dist", ".git", ".cache", "coverage"))
        optimized = temporary / "optimized-dist"
        shutil.copytree(current_dist, optimized)
        source_before = digest_tree(snapshot)
        print("Source and current dist snapshots captured", flush=True)
        with dependency_link(snapshot / "node_modules"):
            checked_dist = temporary / "checked-optimized-dist"
            optimized_build = build(snapshot, checked_dist, temporary)
            if digest_tree(checked_dist) != digest_tree(optimized):
                raise RuntimeError("Current dist is not reproducible from the source snapshot; rebuild production first")
            layout = snapshot / LAYOUT
            source = layout.read_text(encoding="utf-8")
            assert source.count(CONDITIONAL) == 1, "Expected one conditional search mount"
            layout.write_text(source.replace(CONDITIONAL, RESIDENT, 1), encoding="utf-8")
            changed = [name for name, digest in source_before.items() if hashlib.sha256((snapshot / name).read_bytes()).hexdigest() != digest]
            assert changed == [LAYOUT.as_posix()], changed
            baseline = temporary / "resident-dist"
            baseline_build = build(snapshot, baseline, temporary)
        print("Temporary variants built; production dist matches optimized snapshot", flush=True)
        variants = {"residentSearch": baseline, "onDemandSearch": optimized}
        samples = {name: [] for name in variants}
        with ExitStack() as stack:
            services = {
                name: stack.enter_context(isolated_server(temporary / name, dist))
                for name, dist in variants.items()
            }
            with sync_playwright() as playwright:
                browser = playwright.chromium.launch(headless=True)
                browser_version = browser.version
                try:
                    for repetition in range(1, repetitions + 1):
                        order = list(variants) if repetition % 2 else list(reversed(variants))
                        for name in order:
                            origin, _ = services[name]
                            result = sample(browser, origin, variants[name], repetition)
                            samples[name].append(result)
                            print(json.dumps({"variant": name, "repetition": repetition, "initialJsRawBytes": result["initial"]["jsRawBytes"], "initialApiRequests": result["initial"]["apiRequestCount"]}), flush=True)
                finally:
                    browser.close()
        baseline_median = medians(samples["residentSearch"])
        optimized_median = medians(samples["onDemandSearch"])
        assert digest_tree(current_dist) == production_before, "Production dist changed during benchmark"
        result = {
            "recordedAt": datetime.now(timezone.utc).isoformat(),
            "experiment": "Same new interface: resident controlled search versus conditional on-demand search",
            "environment": {"platform": platform.platform(), "python": platform.python_version(), "chromium": browser_version, "viewport": {"width": 1440, "height": 1000}, "repetitionsPerVariant": repetitions, "cache": "fresh browser contexts; routing disables HTTP cache", "network": "localhost; no throttling", "dataset": "empty jobs, runs and reports, one static synthetic configured company; separate temporary SQLite databases"},
            "isolation": {"productionDistUnchanged": True, "optimizedBuildMatchesCurrentDist": True, "changedSourceFiles": [LAYOUT.as_posix()], "sourceSnapshotSha256": hashlib.sha256(json.dumps(source_before, sort_keys=True).encode()).hexdigest(), "liveModelCalls": 0, "temporaryServersStopped": True},
            "measurement": {"bytes": "Sum unique actually requested JS files; raw bytes read from corresponding build file, gzip estimate with Python gzip level 9, mtime=0; not HTTP transferSize", "initialPhase": "home heading visible after networkidle plus 250ms; before search opens", "searchPhase": "new responses after click through networkidle plus 250ms", "timing": "Playwright wall time and Navigation Timing in a headless laboratory; home-ready includes idle waits, not user-perceived load time or field INP"},
            "builds": {"resident": baseline_build, "optimizedReproduction": optimized_build},
            "variants": {name: {"samples": values, "median": medians(values)} for name, values in samples.items()},
            "initialMedianReduction": {name: baseline_median["initial"][name] - optimized_median["initial"][name] for name in ("jsFileCount", "jsRawBytes", "jsGzipBytes", "apiRequestCount")},
            "limitations": ["Only search mount policy differs within the same redesigned frontend; this does not measure the original site's overall speed", "Empty dataset does not cover real list sizes, network latencies or model completion", "Search code and requests are deferred until first open, not removed", "No field INP claim; wall timings include automation and idle waits", "Shared browser process and warm local servers; new context for every measured sample"],
        }
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"output": str(output), "initialMedianReduction": result["initialMedianReduction"], "liveModelCalls": 0}, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "research/frontend-loading-comparison.json")
    parser.add_argument("--repetitions", type=int, default=3)
    args = parser.parse_args()
    run(args.output.resolve(), args.repetitions)
