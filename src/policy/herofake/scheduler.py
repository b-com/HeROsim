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

from typing import Dict, Generator, Set, Tuple, TYPE_CHECKING

from src.policy.herofake.model import HROSystemState

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform, Task

from src.placement.scheduler import Scheduler


class HROScheduler(Scheduler):
    def placement(self, system_state: HROSystemState, task: Task) -> Generator:
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
            # Task deadline
            task_deadline = (
                max(task.type["executionTime"].values())
                * task.application.qos["maxDurationDeviation"]
            )

            scores["penalty"][(node, platform)] = (
                current_task_cold_start
                + current_task_execution_time
                + platform_task_queue
                + next_task_cold_start
                + next_task_execution_time
            ) > task_deadline

            scores["energy_consumption"][(node, platform)] = task.type["energy"][
                platform.type["shortName"]
            ]

            # Platform-level consolidation
            scores["consolidation"][(node, platform)] = 1 / (
                len(platform.queue.items) if platform.queue.items else 1
            )

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
