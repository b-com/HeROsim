"""
Copyright 2024 b<>com

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    http://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

import uuid
import random

from typing import Dict, List

from src.placement.model import (
    ApplicationType,
    PlatformType,
    PlatformVector,
    StorageType,
    TaskType,
)


def make_random_dag(
    task_types: List[TaskType], max_sample_size: int
) -> Dict[str, List[str]]:
    dag: Dict[str, List[str]] = {}

    sample_size = random.randint(1, max_sample_size)
    application_tasks = random.sample(task_types, sample_size)

    previous_task_type: TaskType = application_tasks[0]
    for task_type in application_tasks:
        if previous_task_type != task_type:
            dag[task_type["name"]] = [previous_task_type["name"]]
        else:
            dag[task_type["name"]] = []
        previous_task_type = task_type

    return dag


def generate_application_types(
    count: int, task_types: Dict[str, TaskType], max_sample_size: int
) -> Dict[str, ApplicationType]:
    application_types: Dict[str, ApplicationType] = {}

    for _ in range(count):
        name = str(uuid.uuid4())

        dag = make_random_dag(list(task_types.values()), max_sample_size)

        application_type: ApplicationType = {
            "name": name,
            "dag": dag,
        }

        application_types[name] = application_type

    return application_types


def generate_task_types(
    count: int,
    platform_types: Dict[str, PlatformType],
    storage_types: Dict[str, StorageType],
) -> Dict[str, TaskType]:
    # FIXME: how to select baseline platform?
    baseline_platform = min(
        platform_types,
        key=lambda name: platform_types[name]["price"],
    )

    other_platforms = set(platform_types.keys())
    other_platforms.remove(baseline_platform)

    considered_platforms = list(
        filter(lambda name: platform_types[name]["hardware"] != "dla", other_platforms)
    )

    # Establish performance ratios between platforms
    ratios = {
        "xavierGpu": {
            "memoryRequirements": 13.5,
            "coldStartDuration": 18,
            "executionTime": 7.5,
            "energy": 4.5,
            "imageSize": 0.95,
            "stateSize": {
                "input": 1,
                "output": 1,
            },
        },
        "xavierCpu": {
            "memoryRequirements": 1.05,
            "coldStartDuration": 0.2,
            "executionTime": 0.35,
            "energy": 0.92,
            "imageSize": 0.95,
            "stateSize": {
                "input": 1,
                "output": 1,
            },
        },
        "pynqFpga": {
            "memoryRequirements": 0,
            "coldStartDuration": 3,
            "executionTime": 0.2,
            "energy": 0.02,
            "imageSize": 0.001,
            "stateSize": {
                "input": 1,
                "output": 1,
            },
        },
    }

    task_types: Dict[str, TaskType] = {}

    for _ in range(count):
        name = str(uuid.uuid4())

        # raise NotImplementedError("TODO")

        mean_cpu_duration = 2.90875e-05
        baseline_requirements = {
            "memoryRequirements": random.uniform(0.06, 0.07),
            "coldStartDuration": random.uniform(0.3, 0.4),
            "executionTime": random.uniform(
                0.9 * mean_cpu_duration, 1.1 * mean_cpu_duration
            ),
            "energy": random.uniform(1.3e-5, 1.4e-5),
            "imageSize": random.uniform(3, 3.1),
            "stateSize": {
                "input": 1536,
                "output": 80,
            },
        }

        memory_requirements: PlatformVector[float] = {
            baseline_platform: baseline_requirements["memoryRequirements"],
        } | {
            platform: (
                baseline_requirements["memoryRequirements"]
                * ratios[platform]["memoryRequirements"]
            )
            for platform in considered_platforms
        }

        cold_start_duration: PlatformVector[float] = {
            baseline_platform: baseline_requirements["coldStartDuration"],
        } | {
            platform: (
                baseline_requirements["coldStartDuration"]
                * ratios[platform]["coldStartDuration"]
            )
            for platform in considered_platforms
        }

        execution_time: PlatformVector[float] = {
            baseline_platform: baseline_requirements["executionTime"],
        } | {
            platform: (
                baseline_requirements["executionTime"]
                * ratios[platform]["executionTime"]
            )
            for platform in considered_platforms
        }

        energy: PlatformVector[float] = {
            baseline_platform: baseline_requirements["energy"],
        } | {
            platform: baseline_requirements["energy"] * ratios[platform]["energy"]
            for platform in considered_platforms
        }

        image_size: PlatformVector[float] = {
            baseline_platform: baseline_requirements["imageSize"],
        } | {
            platform: baseline_requirements["imageSize"] * ratios[platform]["imageSize"]
            for platform in considered_platforms
        }

        """
        state_size: PlatformVector[IOVector] = {
            baseline_platform: baseline_requirements["stateSize"],
        } | {
            platform: {
                "input": (
                    baseline_requirements["stateSize"]["input"]
                    * ratios[platform]["stateSize"]["input"]
                ),
                "output": (
                    baseline_requirements["stateSize"]["output"]
                    * ratios[platform]["stateSize"]["output"]
                ),
            }
            for platform in considered_platforms
        }
        """

        task_type: TaskType = {
            "name": name,
            "platforms": ["rpiCpu", "xavierCpu", "xavierGpu", "pynqFpga"],
            "memoryRequirements": memory_requirements,
            "coldStartDuration": cold_start_duration,
            "executionTime": execution_time,
            "energy": energy,
            "imageSize": image_size,
            "stateSize": {},
        }

        task_types[name] = task_type

    return task_types


def fix_tasks_state_size(
    task_types: Dict[str, TaskType], application_types: Dict[str, ApplicationType]
) -> None:
    for application_type_name, application_type in application_types.items():
        for application_task_name in application_type["dag"]:
            if (
                application_type_name
                not in task_types[application_task_name]["stateSize"]
            ):
                task_types[application_task_name]["stateSize"][
                    application_type_name
                ] = {"input": 153600, "output": 8000}
