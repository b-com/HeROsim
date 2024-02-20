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

import json
import os

from typing import Dict

from src.placement.model import (
    ApplicationType,
    PlatformType,
    QoSType,
    SimulationData,
    StorageType,
    TaskType,
)


def parse_infrastructure_data(data_path: str):
    # Load input data
    platform_types_path = os.path.join(data_path, "platform-types.json")
    storage_types_path = os.path.join(data_path, "storage-types.json")

    with open(platform_types_path, "r") as infile:
        platform_types: Dict[str, PlatformType] = json.load(infile)

    with open(storage_types_path, "r") as infile:
        storage_types: Dict[str, StorageType] = json.load(infile)

    return (platform_types, storage_types)


def parse_workloads_data(data_path: str):
    # Load input data
    application_types_path = os.path.join(data_path, "application-types.json")
    task_types_path = os.path.join(data_path, "task-types.json")
    qos_types_path = os.path.join(data_path, "qos-types.json")

    with open(application_types_path, "r") as infile:
        application_types: Dict[str, ApplicationType] = json.load(infile)

    with open(task_types_path, "r") as infile:
        task_types: Dict[str, TaskType] = json.load(infile)

    with open(qos_types_path, "r") as infile:
        qos_types: Dict[str, QoSType] = json.load(infile)

    return (application_types, task_types, qos_types)


def parse_simulation_data(data_path: str) -> SimulationData:
    (platform_types, storage_types) = parse_infrastructure_data(data_path)
    (application_types, task_types, qos_types) = parse_workloads_data(data_path)

    simulation_data = SimulationData(
        platform_types=platform_types,
        storage_types=storage_types,
        qos_types=qos_types,
        application_types=application_types,
        task_types=task_types,
    )

    return simulation_data
