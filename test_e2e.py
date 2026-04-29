"""
End-to-end smoke test for SDK v0.4.0 new methods.
Tests against the live overseas API.
"""

import asyncio
import sys
import os

sys.path.insert(0, os.path.dirname(__file__))

from tripo3d import TripoClient, TaskStatus

API_KEY = "tsk_IgE_sMn5YmOk18ID7nEiSaZLwZ9Ra5CW8s"

RESULTS = {}


def report(name, ok, detail=""):
    status = "PASS" if ok else "FAIL"
    RESULTS[name] = ok
    print(f"  [{status}] {name}" + (f" — {detail}" if detail else ""))


async def main():
    print("=" * 60)
    print("SDK v0.4.0 E2E Smoke Test (overseas)")
    print("=" * 60)

    # --- Phase 0: region init ---
    print("\n[Phase 0] Region initialization")

    client_ov = TripoClient(api_key=API_KEY)
    report("region=ov base_url", "api.tripo3d.ai" in client_ov.base_url, client_ov.base_url)
    await client_ov.close()

    client_cn = TripoClient(api_key=API_KEY, region="cn")
    report("region=cn base_url", "api.tripo3d.com" in client_cn.base_url, client_cn.base_url)
    await client_cn.close()

    client_compat = TripoClient(api_key=API_KEY, IS_GLOBAL=False)
    report("IS_GLOBAL=False compat", client_compat.region == "cn", f"region={client_compat.region}")
    await client_compat.close()

    # --- Phase 1: balance check (verifies auth + connectivity) ---
    print("\n[Phase 1] Auth & connectivity")

    async with TripoClient(api_key=API_KEY) as client:
        try:
            balance = await client.get_balance()
            report("get_balance", True, f"balance={balance.balance}")
        except Exception as e:
            report("get_balance", False, str(e))

        # --- Phase 2: text_to_image ---
        print("\n[Phase 2] text_to_image")
        try:
            task_id = await client.text_to_image(prompt="a cute orange cat, white background")
            report("text_to_image create", True, f"task_id={task_id}")

            task = await client.wait_for_task(task_id, timeout=120, verbose=True)
            report("text_to_image result", task.status == TaskStatus.SUCCESS, f"status={task.status}")
            if task.output.image:
                report("text_to_image has image output", True, task.output.image[:80] + "...")
        except Exception as e:
            report("text_to_image", False, str(e))

        # --- Phase 3: generate_image ---
        print("\n[Phase 3] generate_image (text only)")
        try:
            task_id = await client.generate_image(prompt="a 3d cartoon robot, isometric view")
            report("generate_image create", True, f"task_id={task_id}")

            task = await client.wait_for_task(task_id, timeout=120, verbose=True)
            report("generate_image result", task.status == TaskStatus.SUCCESS, f"status={task.status}")
        except Exception as e:
            report("generate_image", False, str(e))

        # --- Phase 4: text_to_model with new params ---
        print("\n[Phase 4] text_to_model (with export_uv)")
        try:
            task_id = await client.text_to_model(
                prompt="a simple wooden chair",
                model_version="v2.5-20250123",
                export_uv=False,
                texture=False,
                pbr=False,
            )
            report("text_to_model create", True, f"task_id={task_id}")

            task = await client.wait_for_task(task_id, timeout=300, verbose=True)
            report("text_to_model result", task.status == TaskStatus.SUCCESS, f"status={task.status}")
        except Exception as e:
            report("text_to_model", False, str(e))

        # --- Phase 5: image_to_model with enable_image_autofix ---
        print("\n[Phase 5] image_to_model (URL input + enable_image_autofix)")
        try:
            task_id = await client.image_to_model(
                image="https://tripo-public.cdn.bcebos.com/assets/doc/task-sample.jpg",
                model_version="v2.5-20250123",
                enable_image_autofix=True,
                texture=False,
                pbr=False,
            )
            report("image_to_model create", True, f"task_id={task_id}")

            task = await client.wait_for_task(task_id, timeout=300, verbose=True)
            report("image_to_model result", task.status == TaskStatus.SUCCESS, f"status={task.status}")
        except Exception as e:
            report("image_to_model", False, str(e))

    # --- Summary ---
    print("\n" + "=" * 60)
    total = len(RESULTS)
    passed = sum(1 for v in RESULTS.values() if v)
    failed = total - passed
    print(f"TOTAL: {total}  PASSED: {passed}  FAILED: {failed}")
    if failed:
        print("\nFailed tests:")
        for name, ok in RESULTS.items():
            if not ok:
                print(f"  - {name}")
    print("=" * 60)

    return 0 if failed == 0 else 1


if __name__ == "__main__":
    exit(asyncio.run(main()))
