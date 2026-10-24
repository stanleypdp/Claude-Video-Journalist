"""Read for one video: ingest -> mechanics -> one Claude call -> OUTPUT files. Cache: sha256 + role + schema."""

import json
import time
from datetime import UTC, datetime
from pathlib import Path

from vjournalist import llm
from vjournalist.bridge.cards import export_read
from vjournalist.bridge.transcript import chapters
from vjournalist.config import Config
from vjournalist.pipeline.ingest import ingest
from vjournalist.pipeline.media import prepare
from vjournalist.pipeline.payload import SCHEMA_VERSION, build_payload
from vjournalist.roles import schema_for_role
from vjournalist.storage import Jobs, atomic_json, check_quota, pipeline_lock, read_json, slug

ROLE = "knowledge"


def token_count(usage):
    if not usage:
        return None
    keys = ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")
    return sum(usage.get(key, 0) for key in keys)


def reuse_common(base_cache, cache):
    """Mechanics (ASR, OCR, scenes) of an earlier schema version, if stored.

    The cache key of mechanics is the SHA-256 only; a new schema version repeats the LLM call, not these.
    """
    found = sorted(
        (p for p in (base_cache / "roles" / ROLE).glob("v*/common.json") if p.parent != cache),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    for path in found:
        common = read_json(path)
        if {"transcript", "scan", "metadata", "platform_info"} <= common.keys():
            return {**common, "mechanics_reused": [f"common.json ({path.parent.name})"]}
    return None


def render(config, result, common, provenance):
    """Cards, articles, archives and INDEX inputs for one result. Returns the written paths."""
    analysis = result["analysis"]
    id_ = slug(provenance["name"]) + "-" + provenance["sha256"][:12]
    root = config.bridge or config.data.parent / "OUTPUT"
    export_read(id_, analysis, common, root)
    chapters(id_, common["transcript"], common["metadata"]["duration_s"], config, root)
    return [str(root / sub / f"{id_}.md") for sub in ("cards", "articles")]


def analyze_video(source, role=ROLE, force=False, prepare_only=False, config=None, captions=None):
    if role != ROLE:
        raise ValueError("Only the knowledge role (Read) is supported.")
    config = config or Config.load()
    version = SCHEMA_VERSION
    start = time.monotonic()
    with pipeline_lock(config.data):
        jobs = Jobs(config.data)
        job = jobs.create(Path(source).name, role, schema_version=version)

        def log(step, message):
            return jobs.log(job, step, message)

        try:
            check_quota(config)
            log("ingest", "file and SHA-256")
            video, digest, url, name = ingest(source, config)
            jobs.update(job, sha256=digest)
            work = config.data / "work" / digest
            base_cache = config.data / "cache" / digest
            cache = base_cache / "roles" / role / f"v{version}"
            if force and cache.exists():
                archive = cache.with_name(f"v{version}-run-" + datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f"))
                cache.rename(archive)
            work.mkdir(parents=True, exist_ok=True)
            cache.mkdir(parents=True, exist_ok=True)
            provenance_path = base_cache / "provenance.json"
            if not provenance_path.exists():
                atomic_json(
                    provenance_path,
                    {
                        "name": name,
                        "sha256": digest,
                        "source_url": url,
                        "platform": "local",
                        "created": datetime.now(UTC).isoformat(),
                    },
                )
            provenance = read_json(provenance_path)
            result_path = cache / "analysis.json"
            payload_path = cache / "payload.json"
            cached = result_path.exists()
            if cached:
                result = read_json(result_path)
                payload = read_json(payload_path)
                log("cache", "HIT: no mechanics, no LLM call")
            else:
                if not prepare_only:
                    llm.preflight(config)
                common = reuse_common(base_cache, cache)
                if common:
                    log("media", "mechanics reused from an earlier schema version (no ASR/OCR)")
                else:
                    common = prepare(video, work, config, log, captions=captions)
                atomic_json(cache / "common.json", common)
                payload = build_payload(common, video, work)
                atomic_json(payload_path, payload)
                check_quota(config)
                if prepare_only:
                    jobs.update(job, status="done", step="prepared", elapsed_s=time.monotonic() - start)
                    return {"job_id": job, "status": "prepared", "sha256": digest}
                log("analysis", "Claude CLI: Read")
                payload["_receipt_dir"] = str(cache / "llm")
                result = llm.analyze(payload, schema_for_role(role, payload))
                atomic_json(result_path, result)
            if prepare_only:
                return {"job_id": job, "status": "prepared", "sha256": digest, "cache": "HIT"}
            log("render", "Markdown to OUTPUT")
            common = read_json(cache / "common.json")
            outputs = render(config, result, common, provenance)
            usages = [item["usage"] for item in result["usage"]]
            report = {
                "job_id": job,
                "status": "done",
                "schema_version": result["analysis"].get("schema_version", 1),
                "role": role,
                "frame_count": common["scan"]["frame_count"],
                "images_sent": 0 if cached else len(payload["images"]),
                "mechanics_reused": common.get("mechanics_reused", []),
                "sha256": digest,
                "cache": "HIT" if cached else "MISS",
                "elapsed_s": round(time.monotonic() - start, 3),
                "outputs": outputs,
                "tokens_first_call": 0 if cached else token_count(usages[0]) if usages else None,
                "tokens_retries": 0 if cached else sum(token_count(u) or 0 for u in usages[1:]),
                "llm_invocations": 0 if cached else result["invocations"],
                "cost_usd_first_call": 0 if cached else result["usage"][0].get("cost_usd") if usages else None,
                "cost_usd_retries": 0
                if cached
                else sum(item.get("cost_usd") or 0 for item in result["usage"][1:]),
            }
            jobs.update(
                job,
                status="done",
                step="done",
                elapsed_s=report["elapsed_s"],
                usage=json.dumps(report),
                outputs=json.dumps(outputs),
                cached=int(cached),
            )
            atomic_json(config.data / "reports" / f"job-{job}.json", report)
            return report
        except Exception as exc:
            jobs.update(job, status="failed", error=str(exc), elapsed_s=time.monotonic() - start)
            raise
        finally:
            jobs.close()
