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

from __future__ import annotations

import logging
import math

from typing import Dict, Generator, Set, Tuple, TYPE_CHECKING

from src.policy.herocache.model import HRCSystemState

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform, Storage, Task

from src.placement.scheduler import Scheduler


class HRCScheduler(Scheduler):
    def placement(self, system_state: HRCSystemState, task: Task) -> Generator:
        # Scheduling functions called in a Simpy Process must be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        replicas: Set[Tuple[Node, Platform]] = system_state.replicas[task.type["name"]]

        logging.warning(f"replicas = {replicas}")

        scores: Dict[str, Dict[Tuple[Node, Platform], float]] = {
            "penalty": {},
            "energy_consumption": {},
            "consolidation": {},
        }

        for node, platform in replicas:
            # FIXME: Get node-local storage (which one?)
            some_node_storage: Storage = yield node.storage.get(
                lambda storage: not storage.type["remote"]
            )
            # Current task cold start
            current_task_cold_start = (
                platform.current_task.type["coldStartDuration"][
                    platform.type["shortName"]
                ]
                - (self.env.now - platform.current_task.arrived_time)
                if platform.current_task
                and platform.current_task.cold_started
                and not hasattr(platform.current_task, "started_time")
                else 0
            )
            # Current task execution time
            current_task_execution_time = (
                platform.current_task.type["executionTime"][platform.type["shortName"]]
                - (self.env.now - getattr(platform.current_task, "started_time", 0))
                if platform.current_task
                else 0
            )
            # FIXME: We would need task storage to be fixed before task execution
            # Current task communications time
            current_task_communications_time = (
                platform.current_task.type["stateSize"][
                    platform.current_task.application.type["name"]
                ]["output"]
                / (some_node_storage.type["throughput"]["write"] * 1024 * 1024)
                + some_node_storage.type["latency"]["write"]
                if platform.current_task
                else 0
            )
            # Platform task queue (QoS weighted)
            platform_task_queue = sum(
                queued_task.type["executionTime"][platform.type["shortName"]]
                for queued_task in platform.queue.items
                if queued_task.application.qos["maxDurationDeviation"]
                >= task.application.qos["maxDurationDeviation"]
            )
            # Next task cold start
            next_task_cold_start = (
                task.type["coldStartDuration"][platform.type["shortName"]]
                if not platform.current_task and not platform.previous_task
                else 0
            )
            # Next task execution time
            next_task_execution_time = task.type["executionTime"][
                platform.type["shortName"]
            ]
            # Next task communications time
            # FIXME: We would need task storage to be fixed before task scheduling
            next_task_communications_time = (
                task.type["stateSize"][task.application.type["name"]]["input"]
                / (some_node_storage.type["throughput"]["read"] * 1024 * 1024)
                + some_node_storage.type["latency"]["read"]
            ) + (
                task.type["stateSize"][task.application.type["name"]]["output"]
                / (some_node_storage.type["throughput"]["write"] * 1024 * 1024)
                + some_node_storage.type["latency"]["write"]
            )
            yield node.storage.put(some_node_storage)
            # Task deadline
            task_deadline = (
                max(task.type["executionTime"].values())
                * task.application.qos["maxDurationDeviation"]
            )

            scores["penalty"][(node, platform)] = (
                current_task_cold_start
                + current_task_execution_time
                + current_task_communications_time
                + platform_task_queue
                + next_task_cold_start
                + next_task_execution_time
                + next_task_communications_time
            ) > task_deadline

            """
            # FIXME: PENALTY PER APPLICATION
            remaining_tasks = list(task.application.tasks)
            remaining_tasks.remove(task)
            """

            scores["energy_consumption"][(node, platform)] = task.type["energy"][
                platform.type["shortName"]
            ]

            # Platform-level consolidation
            concurrency_target: float = (
                system_state.scheduler_state.target_concurrencies[task.type["name"]][
                    platform.type["shortName"]
                ]
            )
            platform_concurrency = len(platform.queue.items)
            platform_usage_ratio = platform_concurrency / concurrency_target

            scores["consolidation"][(node, platform)] = (
                math.exp(platform_usage_ratio)
                if platform_usage_ratio <= self.policy.queue_length
                else math.exp(self.policy.queue_length)
            )

            """
            scores["consolidation"][(node, platform)] = (
                1
                - platform_usage_ratio
                + 2 * (math.trunc(platform_usage_ratio)) * platform_usage_ratio
            )
            """

        # logging.error(f"scores = {scores}")

        # Weights?
        weights: Dict[str, float] = {
            "penalty": 2 / 3,
            "energy_consumption": 0.5 / 6,
            "consolidation": 1.5 / 6,
        }

        # Normalize scores?
        normalized_scores: Dict[str, Dict[Tuple[Node, Platform], float]] = dict(scores)
        for metric, values in scores.items():
            t_min = 1
            t_max = 100

            v_min = min(scores[metric].values())
            v_max = max(scores[metric].values())

            # TODO if v_min == v_max...
            denominator = v_max - v_min
            denominator_safe = denominator if denominator != 0.0 else 0.01

            for couple, value in values.items():
                normalized_scores[metric][couple] = (
                    # FIXME
                    ((value - v_min) / denominator_safe) * (t_max - t_min)
                    + t_min
                )

        # logging.error(f"{self.env.now} normalized_scores = {normalized_scores}")
        # pprint.pprint(normalized_scores)

        consolidated_scores: Dict[Tuple[Node, Platform], float] = {}

        for metric, values in normalized_scores.items():
            for couple, value in values.items():
                if couple not in consolidated_scores:
                    consolidated_scores[couple] = 0

                consolidated_scores[couple] += weights[metric] * value

        # logging.error(f"consolidated_scores = {consolidated_scores}")

        selected = min(consolidated_scores, key=consolidated_scores.__getitem__)

        # logging.error(f"selected = {selected}")

        return selected
