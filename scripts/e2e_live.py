#!/usr/bin/env python3
"""Live end-to-end check of tripo3d against a real apiv3 endpoint. Creates billable tasks.

Usage:
    TRIPO_API_KEY=tsk_... python scripts/e2e_live.py --region global --report out.json
    TRIPO_API_KEY=tsk_... python scripts/e2e_live.py --region cn --budget 800

Each case prints PASS/FAIL; the JSON report lists every task_id and credits_consumed.
The run stops creating tasks once the balance drop exceeds --budget.
"""

import argparse
import asyncio
import json
import os
import sys
import tempfile
import time
import warnings
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from tripo3d import TaskStatus, TripoClient  # noqa: E402


class Budget(Exception):
    pass


class Run:
    def __init__(self, client, budget, start_balance, workdir):
        self.client = client
        self.budget = budget
        self.start_balance = start_balance
        self.workdir = workdir
        self.cases = []

    async def guard(self):
        balance = (await self.client.get_balance()).balance
        if self.start_balance - balance > self.budget:
            raise Budget(f"spent {self.start_balance - balance:.2f} > budget {self.budget}")

    async def task(self, name, create, expect_files=("model",)):
        await self.guard()
        started = time.time()
        record = {"case": name, "ok": False}
        try:
            task_id = await create
            record["task_id"] = task_id
            task = await self.client.wait_for_task(task_id, timeout=1800)
            record.update(status=task.status.value, credits=task.credits_consumed,
                          error_code=task.error_code, error_msg=task.error_msg)
            if task.status != TaskStatus.SUCCESS:
                raise RuntimeError(f"status={task.status.value} code={task.error_code} msg={task.error_msg}")
            files = await self.client.download_task_models(task, self.workdir) if expect_files else {}
            for key in expect_files:
                path = files.get(key)
                if not path or os.path.getsize(path) == 0:
                    raise RuntimeError(f"missing downloaded {key}: {files}")
            record["files"] = {k: os.path.basename(v) for k, v in files.items() if v}
            record["output_keys"] = sorted(task.output.raw)
            record["ok"] = True
            return task
        except Budget:
            raise
        except Exception as exc:  # noqa: BLE001
            record["error"] = f"{type(exc).__name__}: {exc}"
            return None
        finally:
            record["elapsed_sec"] = round(time.time() - started, 1)
            self.cases.append(record)
            print(f"[{'PASS' if record['ok'] else 'FAIL'}] {name} {record.get('task_id', '')} "
                  f"{record.get('credits')} {record.get('error', '')}", flush=True)

    def check(self, name, ok, detail=None):
        self.cases.append({"case": name, "ok": bool(ok), "detail": detail})
        print(f"[{'PASS' if ok else 'FAIL'}] {name} {detail or ''}", flush=True)


async def main(region, budget, report_path):
    warnings.simplefilter("ignore", DeprecationWarning)
    workdir = tempfile.mkdtemp(prefix=f"tripo-e2e-{region}-")
    async with TripoClient(IS_GLOBAL=(region == "global")) as client:
        start = (await client.get_balance()).balance
        run = Run(client, budget, start, workdir)
        try:
            base = await run.task("text_to_model", client.text_to_model(
                prompt="a small wooden chair", model_version="v3.1-20260211", texture=False, pbr=False))
            image = await run.task("text_to_image", client.text_to_image("a cute cartoon fox, white background"),
                                   expect_files=("image",))
            if base:
                tid = base.task_id
                textured = await run.task("texture_model", client.texture_model(
                    tid, model_version="v3.0-20250812", text_prompt="oak wood"))
                check = await run.task("check_riggable", client.check_riggable(tid), expect_files=())
                if check:
                    run.check("rig_check.rig_type", check.output.rig_type, check.output.raw)
                # v2.5 rigs reject humanoid presets (algorithm side, since 2026-09-23); v1.0 accepts them.
                rig = await run.task("rig_model", client.rig_model(tid, model_version="v1.0-20240301"))
                if rig:
                    retarget = await run.task("retarget_animation", client.retarget_animation(
                        rig.task_id, "preset:walk", bake_animation=True))
                    if retarget:
                        await run.task("convert_model", client.convert_model(retarget.task_id, "FBX", face_limit=-1))
                lowpoly = await run.task("smart_lowpoly_v3_smart_uv", client.smart_lowpoly(
                    tid, model_version="v3.0", face_limit=5000, smart_uv=True))
                # Smart UV accepts at most 80,000 equivalent triangles, so it runs on the low-poly result.
                if lowpoly:
                    await run.task("mesh_uv", client.mesh_uv(lowpoly.task_id), expect_files=("model", "uv_render"))
                seg = await run.task("mesh_segmentation_v2", client.mesh_segmentation(
                    tid, model_version="v2.0-20260430", segmentation_granularity="simple"))
                if seg:
                    await run.task("mesh_completion", client.mesh_completion(seg.task_id))
                await run.task("import_model_url", client.import_model(base.output.model_url), expect_files=())
            if image:
                local = os.path.join(workdir, f"{image.task_id}_image_local.png")
                await client.download_file(image.output.image, local)
                await run.task("image_to_model_local_upload", client.image_to_model(
                    local, model_version="v2.5-20250123", texture=False, pbr=False))
            for retired in (client.refine_model("00000000-0000-0000-0000-000000000000"),
                            client.stylize_model("00000000-0000-0000-0000-000000000000", "voxel")):
                try:
                    await retired
                    run.check("retired_method_raises", False, "no error")
                except ValueError as exc:
                    run.check("retired_method_raises", "no longer supported" in str(exc), str(exc)[:80])
            ids = [c["task_id"] for c in run.cases if c.get("task_id")]
            if ids:
                batch = await client.list_tasks(ids[:10])
                run.check("list_tasks", len(batch.tasks) == min(len(ids), 10), {"missed": batch.missed})
            usage = await client.get_usage(limit=5)
            run.check("get_usage", isinstance(usage, list), {"rows": len(usage)})
        except Budget as exc:
            run.check("budget", False, str(exc))
        end = (await client.get_balance()).balance
    summary = {
        "region": region, "base_url": client.BASE_URL, "balance_before": start, "balance_after": end,
        "spent": round(start - end, 2), "passed": sum(c["ok"] for c in run.cases),
        "failed": sum(not c["ok"] for c in run.cases), "cases": run.cases,
    }
    print(json.dumps({k: v for k, v in summary.items() if k != "cases"}))
    if report_path:
        Path(report_path).write_text(json.dumps(summary, indent=2, ensure_ascii=False))
    return summary["failed"] == 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--region", choices=("global", "cn"), default="global")
    parser.add_argument("--budget", type=float, default=1500)
    parser.add_argument("--report")
    args = parser.parse_args()
    sys.exit(0 if asyncio.run(main(args.region, args.budget, args.report)) else 1)
