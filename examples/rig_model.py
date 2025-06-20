#!/usr/bin/env python
"""
Example of using the Tripo API to rig a 3D model for animation.
"""

import os
import asyncio
import argparse

from tripo3d import TripoClient
from tripo3d.models import TaskStatus, RigType, RigSpec


async def main(model_task_id: str, output_dir: str, rig_type: str, spec: str, out_format: str):
    """
    Rig a 3D model for animation.

    Args:
        model_task_id: Task ID of the model to rig.
        output_dir: Directory to save output files.
        rig_type: Type of rigging (biped, quadruped, etc.).
        spec: Rigging specification (mixamo or tripo).
        out_format: Output format (glb or fbx).
    """
    async with TripoClient() as client:
        # Rig the model
        print(f"Rigging model with type: {rig_type}, spec: {spec}, format: {out_format}")
        rig_task_id = await client.rig_model(
            original_model_task_id=model_task_id,
            out_format=out_format,
            rig_type=RigType(rig_type) if rig_type else None,
            spec=RigSpec(spec) if spec else None
        )

        # Wait for rigging completion and show progress
        rig_result = await client.wait_for_task(rig_task_id, verbose=True)

        if rig_result.status == TaskStatus.SUCCESS:
            print(f"Rigging completed successfully!")

            # Create output directory (if it doesn't exist)
            os.makedirs(output_dir, exist_ok=True)

            # Download rigged model files
            try:
                print("Downloading rigged model files...")
                downloaded_files = await client.download_task_models(rig_result, output_dir)

                # Print downloaded file paths
                for model_type, file_path in downloaded_files.items():
                    if file_path:
                        print(f"Downloaded {model_type}: {file_path}")

            except Exception as e:
                print(f"Failed to download rigged models: {str(e)}")
        else:
            print(f"Rigging failed with status: {rig_result.status}")
            if rig_result.error_msg:
                print(f"Error message: {rig_result.error_msg}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Rig a 3D model for animation using Tripo API")
    parser.add_argument("model_task_id", help="Task ID of the model to rig")
    parser.add_argument("--output-dir", default="./output", help="Directory to save output files")
    parser.add_argument("--rig-type", choices=["biped", "quadruped", "hexapod", "octopod", "avian", "serpentine", "aquatic", "others"],
                       help="Type of rigging (optional, will be auto-detected if not specified)")
    parser.add_argument("--spec", choices=["mixamo", "tripo"], default="tripo",
                       help="Rigging specification (default: tripo)")
    parser.add_argument("--format", choices=["glb", "fbx"], default="glb",
                       help="Output format (default: glb)")

    args = parser.parse_args()

    # Run the main function
    asyncio.run(main(args.model_task_id, args.output_dir, args.rig_type, args.spec, args.format)) 