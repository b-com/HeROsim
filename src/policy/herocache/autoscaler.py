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


from src.policy.herocache.model import HRCSchedulerState, HRCSystemState

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform, Storage

from src.placement.model import (
    DurationSecond,
    PlatformVector,
    SizeGigabyte,
    SpeedMBps,
    SystemState,
    TaskType,
)

from src.placement.autoscaler import Autoscaler


class HRCAutoscaler(Autoscaler):
    def scaling_level(
        self, system_state: HRCSystemState, task_type: TaskType
    ) -> Generator:
        # Scheduling functions called in a Simpy Process must be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        state: HRCSchedulerState = system_state.scheduler_state
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
        # Filter out nodes by task requirements
        couples_suitable: Set[Tuple[Node, Platform]] = set()

        available_resources: Dict[Node, Set[Platform]] = (
            system_state.available_resources
        )
        for node, platforms in available_resources.items():
            for platform in platforms:
                if (
                    platform.type["shortName"]
                    not in self.data.task_types[task_type["name"]]["platforms"]
                ):
                    continue
                if (
                    node.memory
                    < self.data.task_types[task_type["name"]]["memoryRequirements"][
                        platform.type["shortName"]
                    ]
                ):
                    continue
                couples_suitable.add((node, platform))

        yield self.env.process(self.create_replica(couples_suitable, task_type))
        """

        """
        available_hardware: Set[str] = set()
        for _, platforms in system_state.available_resources.items():
            for platform in platforms:
                if (
                    platform.type["shortName"] in task_type["platforms"]
                    and platform.type["shortName"] not in available_hardware
                ):
                    available_hardware.add(platform.type["shortName"])

        # FIXME: Consolidate on application basis
        sorted_hardware = sorted(
            available_hardware,
            key=lambda platform_name: task_type["coldStartDuration"][platform_name],
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
                logging.error(f"[ {self.env.now} ] SUCCESS! {platform_name} replica created for {task_type['name']}")
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
            "pull_time": {},
            "cold_start": {},
            "execution_time": {},
        }

        scores: Dict[str, Dict[Tuple[Node, Platform], float]] = {
            "total_time": {},
            "cache_proportion": {},
            "energy_consumption": {},
            "consolidation": {},
        }

        for node, platform in couples_suitable:
            # TODO: Check node cache for function image
            cache_storage: bool = False
            node_storage: Storage
            for node_storage in node.storage.items:
                if node_storage.has_function(platform.type["shortName"], task_type):
                    cache_storage = True
                    break

            retrieval_duration: float = 0.0

            if not cache_storage:
                retrieval_size: SizeGigabyte = task_type["imageSize"][
                    platform.type["shortName"]
                ]
                # retrieval_speed: SizeGigabyte = 1.25  # Gigabit link (10 Gbps = 1250 MB/s)
                retrieval_speed: SpeedMBps = node.network["bandwidth"]
                retrieval_duration += retrieval_size / (retrieval_speed / 1024)

            # Storage (image pull time)
            task_times["pull_time"][(node, platform)] = retrieval_duration

            # Storage (replica initialization)
            task_times["cold_start"][(node, platform)] = task_type["coldStartDuration"][
                platform.type["shortName"]
            ]

            # TODO: Storage (function communications)
            # Impact the "node part" of scoring
            # Best-case? Worst-case?
            task_times["execution_time"][(node, platform)] = task_type["executionTime"][
                platform.type["shortName"]
            ]

            scores["total_time"][(node, platform)] = (
                task_times["pull_time"][(node, platform)]
                + task_times["cold_start"][(node, platform)]
                + task_times["execution_time"][(node, platform)]
            )

            scores["energy_consumption"][(node, platform)] = task_type["energy"][
                platform.type["shortName"]
            ]

            # TODO: Node-level application consolidation (image cache)
            # List applications that include considered task type
            # FIXME: Compute once and keep in SystemState
            applications_of_task: Set[str] = set()
            for application_type_name in self.data.application_types:
                for task_type_name in self.data.application_types[
                    application_type_name
                ]["dag"]:
                    if task_type_name == task_type["name"]:
                        applications_of_task.add(application_type_name)

            # logging.error(f"[ {self.env.now} ] {task_type['name']}")
            # logging.error(f"[ {self.env.now} ] {applications_of_task}")

            # Compute the % of function images from each application cached on node
            local_tasks: Dict[str, int] = {
                app_name: 0 for app_name in applications_of_task
            }
            local_proportions: Dict[str, float] = {
                app_name: 0.0 for app_name in applications_of_task
            }
            for application_type_name in applications_of_task:
                application_type = self.data.application_types[application_type_name]
                application_tasks = application_type["dag"]

                for task_type_name in application_tasks:
                    storage: Storage
                    for storage in node.storage.items:
                        if storage.has_function(platform.type["shortName"], task_type):
                            local_tasks[application_type_name] += 1

                local_proportions[application_type_name] = local_tasks[
                    application_type_name
                ] / len(application_tasks)

            # logging.error(f"[ {self.env.now} ] {local_tasks}")
            # logging.error(f"[ {self.env.now} ] {local_proportions}")

            # FIXME: Consolidate proportions across applications
            consolidated_cache_proportions: float = sum(
                local_proportions.values()
            ) / len(local_proportions)

            scores["cache_proportion"][(node, platform)] = (
                1 / consolidated_cache_proportions
                if consolidated_cache_proportions != 0.0
                else 100.0
            )

            # TODO: Infrastructure-level node consolidation (reclaimable energy)
            scores["consolidation"][(node, platform)] = 1.0 if node.unused else 0.0

        # logging.error(f"{self.env.now} scores = {scores}")
        # pprint.pprint(scores)

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

        # FIXME: Magic number
        weights: Dict[str, float] = {
            "total_time": 3 / 8,
            "cache_proportion": 1 / 8,
            "energy_consumption": 1 / 8,
            "consolidation": 3 / 8,
        }

        consolidated_scores: Dict[Tuple[Node, Platform], float] = {}

        for metric, values in normalized_scores.items():
            for couple, value in values.items():
                if couple not in consolidated_scores:
                    consolidated_scores[couple] = 0

                consolidated_scores[couple] += weights[metric] * value

        # logging.error(f"consolidated_scores = {consolidated_scores}")
        # pprint.pprint(consolidated_scores)

        selected = min(consolidated_scores, key=consolidated_scores.__getitem__)

        # pprint.pprint(selected)

        return selected

    def initialize_replica(
        self,
        new_replica: Tuple[Node, Platform],
        function_replicas: Set[Tuple[Node, Platform]],
        task_type: TaskType,
        system_state: HRCSystemState,
    ) -> Generator:
        node: Node = new_replica[0]
        platform: Platform = new_replica[1]

        # Check node RAM cache
        warm_function: bool = (
            platform.previous_task is not None
            and platform.previous_task.type["name"] == task_type["name"]
        )

        # TODO: Check if function image is cached on one of the node's storage devices
        # cache_storage: Storage | None = None
        cache_storage: bool = False
        node_storage: Storage
        for node_storage in node.storage.items:
            if node_storage.has_function(platform.type["shortName"], task_type):
                cache_storage = True
                break

        # Initialize image retrieval duration
        retrieval_duration: DurationSecond = 0.0

        # TODO: Retrieve image if function not in RAM cache nor in disk cache
        # FIXME: Should be factored in superclass
        if not warm_function and not cache_storage:
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

            # TODO: Update disk usage
            stored = node_storage.store_function(platform.type["shortName"], task_type)

            if not stored:
                logging.error(
                    f"[ {self.env.now} ] 💾 {node_storage} has no available capacity to"
                    f" cache image for {self}"
                )

            # Proactively cache next functions
            # FIXME: Compute once and keep in SystemState
            applications_of_task: Set[str] = set()
            for application_type_name in self.data.application_types:
                for task_type_name in self.data.application_types[
                    application_type_name
                ]["dag"]:
                    if task_type_name == task_type["name"]:
                        applications_of_task.add(application_type_name)

            # List applications that include considered task type
            for application_name in applications_of_task:
                application = self.data.application_types[application_name]
                for function_name in application["dag"]:
                    function = self.data.task_types[function_name]

                    # Intersect task compatibility and node-available platforms
                    prefetch_function_platforms = set(function["platforms"])
                    prefetch_node_platforms = [
                        node_platform.type["name"]
                        for node_platform in node.platforms.items
                    ]
                    prefetch_platforms = prefetch_function_platforms.intersection(
                        prefetch_node_platforms
                    )

                    # Prefetch images for the next functions in the application
                    # FIXME: Retrieval time, timeout...
                    for prefetch_platform in prefetch_platforms:
                        stored = node_storage.store_function(
                            prefetch_platform, function
                        )

                        if not stored:
                            logging.error(
                                f"[ {self.env.now} ] 💾 {node_storage} has no available"
                                f" capacity to cache image for {self}"
                            )

            # Release storage
            yield node.storage.put(node_storage)

        # print(f"retrieval duration = {retrieval_duration}")

        # Update state
        state: HRCSchedulerState = system_state.scheduler_state
        # HRC policy
        state.average_hardware_contention[task_type["name"]][
            new_replica[1].type["shortName"]
        ] += 1.0
        """
        # Round Robin placement
        state.scheduled_count[task_type["name"]][
            (new_replica[0].id, new_replica[1].id)
        ] = 0
        """

        # FIXME: Retrieve function image
        yield self.env.timeout(retrieval_duration)

        # FIXME: Update platform time spent on storage
        platform.storage_time += retrieval_duration

        # FIXME: Double initialize bug...
        try:
            # Set platform to ready state
            yield platform.initialized.succeed()
        except RuntimeError:
            """
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
            """
            pass

        # Statistics (Node)
        node.cache_hits += cache_storage

    def remove_replica(
        self,
        function_replicas: Set[Tuple[Node, Platform]],
        task_type: TaskType,
        state: HRCSystemState,
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
