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

from src.policy.herofake.model import HROSchedulerState, HROSystemState

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform

from src.placement.model import (
    DurationSecond,
    PlatformVector,
    SizeGigabyte,
    SpeedMBps,
    SystemState,
    TaskType,
)

from src.placement.autoscaler import Autoscaler


class HROAutoscaler(Autoscaler):
    def scaling_level(
        self, system_state: HROSystemState, task_type: TaskType
    ) -> Generator:
        # Scheduling functions called in a Simpy Process must be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        state: HROSchedulerState = system_state.scheduler_state
        function_replicas: Set[Tuple[Node, Platform]] = system_state.replicas[
            task_type["name"]
        ]
        in_system_concurrencies: PlatformVector = state.average_hardware_contention[
            task_type["name"]
        ]
        target_concurrencies: PlatformVector = state.target_concurrencies[
            task_type["name"]
        ]

        hardware_replicas = {
            platform: [
                replica
                for replica in function_replicas
                if replica[1].type["shortName"] == platform
            ]
            for platform in self.data.platform_types
        }

        # Per-resource/function concurrency level
        concurrency_results = {
            hardware_short_name: math.ceil(
                in_system_concurrencies.get(hardware_short_name, 0)
                / target_concurrencies.get(
                    hardware_short_name, self.policy.queue_length
                )
            ) - len(hardware_replicas[hardware_short_name])
            for hardware_short_name in set(target_concurrencies)
            | set(in_system_concurrencies)
        }

        # logging.error(f"[ {self.env.now} ] {task_type['name']} {concurrency_results}")

        # Result > 0 means scaling up
        # Result < 0 means scaling down
        # Result == 0 means current scaling level is adequate
        return concurrency_results

    def create_first_replica(
        self, system_state: SystemState, task_type: TaskType
    ) -> Generator:
        stop = yield self.env.process(
            self.scale_up(1, system_state, task_type["name"], "any")
        )

        return stop

        """
        # Tie break -- max hardware price
        # Maybe node consolidation instead?
        available_hardware: Set[str] = set()
        for _, platforms in system_state.available_resources.items():
            for platform in platforms:
                if (
                    platform.type["shortName"] in task_type["platforms"]
                    and platform.type["shortName"] not in available_hardware
                ):
                    available_hardware.add(platform.type["shortName"])

        sorted_hardware = sorted(
            # self.data.platform_types.values(),
            available_hardware,
            key=lambda platform_name: self.data.platform_types[platform_name]["price"],
            reverse=True,
        )

        stop = None
        # FIXME: What if no available hardware?
        for platform_name in sorted_hardware:
            stop = yield self.env.process(
                self.scale_up(
                    1, system_state, task_type["name"], self.data.platform_types[platform_name]["shortName"]
                )
            )

            if not isinstance(stop, StopIteration):
                # Resource found, stop iterating
                break
                
        return stop
    """

    def create_replica(
        self, couples_suitable: Set[Tuple[Node, Platform]], task_type: TaskType
    ) -> Generator:
        # Scaling functions that do not yield values must still be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        task_times: Dict[str, Dict[Tuple[Node, Platform], float]] = {
            "cold_start": {},
            "execution_time": {},
        }

        scores: Dict[str, Dict[Tuple[Node, Platform], float]] = {
            "total_time": {},
            "energy_consumption": {},
            "price": {},
        }

        for node, platform in couples_suitable:
            task_times["cold_start"][(node, platform)] = task_type["coldStartDuration"][
                platform.type["shortName"]
            ]

            task_times["execution_time"][(node, platform)] = task_type["executionTime"][
                platform.type["shortName"]
            ]

            scores["total_time"][(node, platform)] = (
                task_times["cold_start"][(node, platform)]
                + task_times["execution_time"][(node, platform)]
            )

            scores["energy_consumption"][(node, platform)] = task_type["energy"][
                platform.type["shortName"]
            ]

            # FIXME: Inverse?
            scores["price"][(node, platform)] = (
                scores["total_time"][(node, platform)] * platform.type["price"]
            )

        # Weights?
        weights: Dict[str, float] = {
            "total_time": 2 / 3,
            "energy_consumption": 1.5 / 6,
            "price": 0.5 / 6,
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

        consolidated_scores: Dict[Tuple[Node, Platform], float] = {}

        for metric, values in normalized_scores.items():
            for couple, value in values.items():
                if couple not in consolidated_scores:
                    consolidated_scores[couple] = 0

                consolidated_scores[couple] += weights[metric] * value

        # logging.error(f"consolidated_scores = {consolidated_scores}")

        selected = min(consolidated_scores, key=consolidated_scores.__getitem__)

        return selected

    def initialize_replica(
        self,
        new_replica: Tuple[Node, Platform],
        function_replicas: Set[Tuple[Node, Platform]],
        task_type: TaskType,
        system_state: HROSystemState,
    ) -> Generator:
        node: Node = new_replica[0]
        platform: Platform = new_replica[1]

        # Check node RAM cache
        warm_function: bool = (
            platform.previous_task is not None
            and platform.previous_task.type["name"] == task_type["name"]
        )

        # Initialize image retrieval duration
        retrieval_duration: DurationSecond = 0.0

        # Retrieve image if function not in RAM cache
        if not warm_function:
            logging.info(
                f"[ {self.env.now} ] 💾 {node} needs to pull image for {task_type}"
            )

            # Update image retrieval duration
            retrieval_size: SizeGigabyte = task_type["imageSize"][
                platform.type["shortName"]
            ]
            # Depends on storage performance
            # FIXME: What's the policy for storage selection?
            node_storage = yield node.storage.get(
                lambda storage: not storage.type["remote"]
            )
            # Depends on network link speed
            retrieval_speed: SpeedMBps = min(
                node_storage.type["throughput"]["write"], node.network["bandwidth"]
            )
            retrieval_duration += (
                retrieval_size / (retrieval_speed / 1024)
                + node_storage.type["latency"]["write"]
            )

            # print(f"retrieval size = {retrieval_size}")
            # print(f"retrieval speed = {retrieval_speed}")

            # Update disk usage
            stored = node_storage.store_function(platform.type["shortName"], task_type)

            if not stored:
                logging.error(
                    f"[ {self.env.now} ] 💾 {node_storage} has no available capacity to"
                    f" cache image for {self}"
                )

            # Release storage
            yield node.storage.put(node_storage)

        # print(f"retrieval duration = {retrieval_duration}")

        # Update state
        state: HROSchedulerState = system_state.scheduler_state
        # HRO policy
        state.average_hardware_contention[task_type["name"]][
            new_replica[1].type["shortName"]
        ] += 1.0
        """
        # Round Robin placement
        state.scheduled_count[task_type["name"]][
            (new_replica[0].id, new_replica[1].id)
        ] = 0
        """

        # Retrieve function image
        yield self.env.timeout(retrieval_duration)

        # Update platform time spent on storage
        platform.storage_time += retrieval_duration

        # FIXME: Double initialize bug...
        try:
            # Set platform to ready state
            yield platform.initialized.succeed()
        except RuntimeError:
            logging.error(
                f"[ {self.env.now} ] Autoscaler tried to initialize "
                f"{new_replica[1]} ({new_replica[0]}) but it was already initialized."
            )

            logging.error(
                f"[ {self.env.now} ] Last allocation time: "
                f"{new_replica[1].last_allocated} "
                " -- Last removal time: "
                f"{new_replica[1].last_removed}"
            )

        # Statistics (Node)
        node.cache_hits += 0

    def remove_replica(
        self,
        function_replicas: Set[Tuple[Node, Platform]],
        task_type: TaskType,
        state: HROSystemState,
    ) -> Generator:
        # Scaling functions that do not yield values must still be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        # Sort function replicas by in-flight requests count
        sorted_replicas = sorted(
            function_replicas, key=lambda couple: len(couple[1].queue.items)
        )

        # FIXME: cost function with cold start!
        # The longest the cold start, the lowest the scale down

        # Mark replica for removal if:
        # - its task queue is empty
        # - its keep alive delay has been exceeded
        # Return None if no replica can be removed
        removed_couple = next(
            (
                replica
                for replica in sorted_replicas
                if not replica[1].queue.items
                and not replica[1].current_task
                and (self.env.now - replica[1].idle_since) > self.policy.keep_alive
            ),
            None,
        )

        return removed_couple
