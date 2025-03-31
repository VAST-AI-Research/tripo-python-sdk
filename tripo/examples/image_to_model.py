#!/usr/bin/env python
"""
Example of using the Tripo API to create a 3D model from an image.
"""

import os
import asyncio
import argparse

from tripo import TripoClient
from tripo.models import TaskStatus


async def main(image_path: str, output_dir: str):
    """
    Create a 3D model from an image.

    Args:
        image_path: Path to the input image file.
        output_dir: Directory to save output files.
    """
    async with TripoClient() as client:
        # 创建任务
        task_id = await client.image_to_model(
            image=image_path,
        )

        # 等待任务完成并显示进度
        task = await client.wait_for_task(task_id, verbose=True)

        if task.status == TaskStatus.SUCCESS:
            print(f"\nTask completed successfully!")

            # 创建输出目录（如果不存在）
            os.makedirs(output_dir, exist_ok=True)

            # 下载模型文件
            try:
                print("\nDownloading model files...")
                downloaded_files = await client.download_task_models(task, output_dir)

                # 打印下载的文件路径
                for model_type, file_path in downloaded_files.items():
                    if file_path:
                        print(f"Downloaded {model_type}: {file_path}")
      
            except Exception as e:
                print(f"Failed to download models: {str(e)}")
        else:
            print(f"\nTask failed with status: {task.status}")


if __name__ == "__main__":
    # Parse command line arguments
    parser = argparse.ArgumentParser(description="Create a 3D model from an image using Tripo API")
    parser.add_argument("image_path", help="Path to the image file")
    parser.add_argument("--output-dir", default="./output", help="Directory to save output files")

    args = parser.parse_args()

    # Run the main function
    asyncio.run(main(args.image_path, args.output_dir)) 