#!/usr/bin/env python
"""
Example of using the Tripo API to apply animations to a rigged 3D model.
"""

import os
import asyncio
import argparse

from tripo3d import TripoClient
from tripo3d.models import TaskStatus, Animation


async def main(rigged_model_task_id: str, output_dir: str, animations: list, out_format: str, bake_animation: bool, export_with_geometry: bool):
    """
    Apply animations to a rigged 3D model.

    Args:
        rigged_model_task_id: Task ID of the rigged model.
        output_dir: Directory to save output files.
        animations: List of animations to apply.
        out_format: Output format (glb or fbx).
        bake_animation: Whether to bake the animation.
        export_with_geometry: Whether to export with geometry.
    """
    async with TripoClient() as client:
        # Apply animations to the rigged model
        print(f"Applying animations {animations} to model {rigged_model_task_id}...")

        # Convert string animation names to Animation enum values
        animation_enums = []
        for anim in animations:
            try:
                animation_enums.append(Animation(anim))
            except ValueError:
                print(f"Warning: Unknown animation '{anim}', skipping...")
                continue

        if not animation_enums:
            print("No valid animations provided!")
            return

        # Use single animation if only one, otherwise use list
        animation_input = animation_enums[0] if len(animation_enums) == 1 else animation_enums

        retarget_task_id = await client.retarget_animation(
            original_model_task_id=rigged_model_task_id,
            animation=animation_input,
            out_format=out_format,
            bake_animation=bake_animation,
            export_with_geometry=export_with_geometry
        )

        # Wait for animation retargeting completion and show progress
        retarget_result = await client.wait_for_task(retarget_task_id, verbose=True)

        if retarget_result.status == TaskStatus.SUCCESS:
            print(f"Animation retargeting completed successfully!")

            # Create output directory (if it doesn't exist)
            os.makedirs(output_dir, exist_ok=True)

            # Download animated model files
            try:
                print("Downloading animated model files...")
                downloaded_files = await client.download_task_models(retarget_result, output_dir)

                # Print downloaded file paths
                for model_type, file_path in downloaded_files.items():
                    if file_path:
                        print(f"Downloaded {model_type}: {file_path}")

            except Exception as e:
                print(f"Failed to download animated models: {str(e)}")
        else:
            print(f"Animation retargeting failed with status: {retarget_result.status}")
            if retarget_result.error_msg:
                print(f"Error message: {retarget_result.error_msg}")


def get_available_animations():
    """Get list of available animations for help text."""
    return [anim.value for anim in Animation]


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Apply animations to a rigged 3D model using Tripo API")
    parser.add_argument("rigged_model_task_id", help="Task ID of the rigged model")
    parser.add_argument("--animations", nargs="+", required=True,
                       choices=get_available_animations(),
                       help="Animations to apply (can specify multiple)")
    parser.add_argument("--output-dir", default="./output", help="Directory to save output files")
    parser.add_argument("--format", choices=["glb", "fbx"], default="glb",
                       help="Output format (default: glb)")
    parser.add_argument("--no-bake", action="store_true",
                       help="Don't bake the animation (default: bake)")
    parser.add_argument("--with-geometry", action="store_true",
                       help="Export animation with geometry (default: False)")

    args = parser.parse_args()

    # Run the main function
    asyncio.run(main(
        args.rigged_model_task_id,
        args.output_dir,
        args.animations,
        args.format,
        not args.no_bake,
        args.with_geometry
    )) 