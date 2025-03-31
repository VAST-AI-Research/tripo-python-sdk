#!/usr/bin/env python
"""
Example of using the Tripo API to create a 3D model from multiple view images.
"""

import os
import asyncio
import argparse
from typing import Optional

from tripo3d import TripoClient
from tripo3d.models import TaskStatus


async def main(front: Optional[str], back: Optional[str], left: Optional[str], right: Optional[str], output_dir: str):
    """
    Create a 3D model from multiple view images.

    Args:
        front: Path to the front view image (optional).
        back: Path to the back view image (optional).
        left: Path to the left view image (optional).
        right: Path to the right view image (optional).
        output_dir: Directory to save output files.
    """
    # 准备图片列表，保持顺序：前、后、左、右
    images = [left, back, right]

    # 检查是否至少提供了一张图片
    if not any(images):
        raise ValueError("At least one image must be provided")

    images.insert(0, front)
    async with TripoClient() as client:
        # 创建任务
        task_id = await client.multiview_to_model(
            images=images,
        )

        # 等待任务完成并显示进度
        task = await client.wait_for_task(task_id, verbose=True)

        if task.status == TaskStatus.SUCCESS:
            print(f"Task completed successfully!")

            # 创建输出目录（如果不存在）
            os.makedirs(output_dir, exist_ok=True)

            # 下载模型文件
            try:
                print("Downloading model files...")
                downloaded_files = await client.download_task_models(task, output_dir)

                # 打印下载的文件路径
                for model_type, file_path in downloaded_files.items():
                    if file_path:
                        print(f"Downloaded {model_type}: {file_path}")

            except Exception as e:
                print(f"Failed to download models: {str(e)}")
        else:
            print(f"Task failed with status: {task.status}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Create a 3D model from multiple view images using Tripo API",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("front", help="Path to the front view image (required)")
    parser.add_argument("--back", help="Path to the back view image (optional)")
    parser.add_argument("--left", help="Path to the left view image (optional)")
    parser.add_argument("--right", help="Path to the right view image (optional)")
    parser.add_argument("--output-dir", default="./output", help="Directory to save output files")

    args = parser.parse_args()

    # 检查是否至少提供了一张图片
    if not any([args.front, args.back, args.left, args.right]):
        parser.error("At least one view image must be provided")

    # Run the main function
    asyncio.run(main(
        front=args.front,
        back=args.back,
        left=args.left,
        right=args.right,
        output_dir=args.output_dir
    )) 