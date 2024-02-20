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

from typing import Set, Tuple, TYPE_CHECKING


from src.policy.knative.model import KnativeSchedulerState, KnativeSystemState

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform

from src.placement.model import (
    DurationSecond,
    PlatformVector,
    SchedulerState,
    SizeGigabyte,
    SpeedMBps,
    SystemState,
    TaskType,
)

from src.placement.autoscaler import Autoscaler


class KnativeAutoscaler(Autoscaler):
    def scaling_level(self, system_state: KnativeSystemState, task_type: TaskType):
        # Scheduling functions called in a Simpy Process must be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        # Knative default values (cf. https://knative.dev/docs/serving/autoscaling/concurrency/)
        # Lambda is 1 (cf. https://notes.crmarsh.com/isolates-microvms-and-webassembly)
        state: KnativeSchedulerState = system_state.scheduler_state
        target_concurrencies: PlatformVector = state.target_concurrencies[
            task_type["name"]
        ]
        function_concurrencies = state.average_contention[task_type["name"]].values()
        function_replicas: Set[Tuple[Node, Platform]] = system_state.replicas[
            task_type["name"]
        ]

        """
        target_concurrencies: PlatformVector = {
            platform: self.policy.queue_length if platform == baseline_platform else 0
            for platform in self.data.platform_types
        }
        """

        platform_count = len(
            [
                platform
                for platform in self.data.platform_types.values()
                # if platform["hardware"] == "cpu"
            ]
        )

        # Per-function concurrency level
        # Knative only allocates CPUs (baseline platform)
        in_system_concurrencies: PlatformVector = {
            platform_type["shortName"]: (
                0.0
                if not function_concurrencies
                else sum(function_concurrencies) / platform_count
                # if platform_type["hardware"] == "cpu"
                # else 0.0
            )
            for platform_type in self.data.platform_types.values()
        }

        replica_count = len(function_replicas)

        # Result > 0 means scaling up
        # Result < 0 means scaling down
        # Result == 0 means current scaling level is adequate
        concurrency_results: PlatformVector = {
            platform_type["shortName"]: (
                math.ceil(
                    in_system_concurrencies[platform_type["shortName"]]
                    / target_concurrencies[platform_type["shortName"]]
                )
                - replica_count
                # if platform_type["hardware"] == "cpu"
                # else 0
            )
            for platform_type in self.data.platform_types.values()
        }

        """
        logging.error(f"[ {self.env.now} ] ===")
        logging.error(f"[ {self.env.now} ] {task_type['name']} {in_system_concurrencies}")
        logging.error(f"[ {self.env.now} ] {task_type['name']} {function_replicas}")
        logging.error(f"[ {self.env.now} ] {task_type['name']} {target_concurrencies}")
        logging.error(f"[ {self.env.now} ] {task_type['name']} {concurrency_results}")
        logging.error(f"[ {self.env.now} ] ===")
        """

        return concurrency_results

    def create_first_replica(self, system_state: SystemState, task_type: TaskType):
        # Knative will allocate a new CPU replica
        available_hardware: Set[str] = set()
        for _, platforms in system_state.available_resources.items():
            for platform in platforms:
                if (
                    # platform.type["hardware"] == "cpu"
                    # and platform.type["shortName"] in task_type["platforms"]
                    platform.type["shortName"]
                    in task_type["platforms"]
                ):
                    available_hardware.add(platform.type["shortName"])

        stop = None
        # FIXME: What if no available hardware?
        for platform_name in available_hardware:
            stop = yield self.env.process(
                self.scale_up(
                    1,
                    system_state,
                    task_type["name"],
                    self.data.platform_types[platform_name]["shortName"],
                )
            )

            if not isinstance(stop, StopIteration):
                # Resource found, stop iterating
                break

        return stop

    def create_replica(
        self, couples_suitable: Set[Tuple[Node, Platform]], task_type: TaskType
    ):
        # Scaling functions that do not yield values must still be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        """
        # Knative only allocates CPUs
        filtered_couples = set(filter(
            lambda couple: couple[1].type["hardware"] == "cpu",
            couples_suitable
        ))
        """

        # Knative selects a replica on the most available node (cf. ENSURE)
        available_couple = max(
            # filtered_couples, key=lambda couple: couple[0].available_platforms
            couples_suitable,
            key=lambda couple: couple[0].available_platforms,
        )

        return available_couple

    def initialize_replica(
        self,
        new_replica: Tuple[Node, Platform],
        function_replicas: Set[Tuple[Node, Platform]],
        task_type: TaskType,
        system_state: KnativeSystemState,
    ):
        node: Node = new_replica[0]
        platform: Platform = new_replica[1]

        # Check node RAM cache
        warm_function: bool = (
            platform.previous_task is not None
            and platform.previous_task.type["name"] == task_type["name"]
        )

        # Initialize image retrieval duration
        retrieval_duration: DurationSecond = 0.0

        # TODO: Retrieve image if function not in RAM cache nor in disk cache
        # FIXME: Should be factored in superclass
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

            # TODO: Update disk usage
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
        # FIXME: Move to state update methods
        state: KnativeSchedulerState = system_state.scheduler_state
        # Knative policy
        state.average_contention[task_type["name"]][
            (new_replica[0].id, new_replica[1].id)
        ] = 1.0

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
        node.cache_hits += 0

    def remove_replica(
        self,
        function_replicas: Set[Tuple[Node, Platform]],
        task_type: TaskType,
        system_state: KnativeSystemState,
    ):
        # Scaling functions that do not yield values must still be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489&
        if False:
            yield

        # Sort function replicas by in-flight requests count
        sorted_replicas = sorted(
            function_replicas, key=lambda couple: len(couple[1].queue.items)
        )

        # Mark replica for removal if its task queue is empty
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

        if removed_couple:
            # Update state
            # FIXME: Move to state update methods
            state: SchedulerState = system_state.scheduler_state
            try:
                # Knative policy
                del state.average_contention[task_type["name"]][
                    (removed_couple[0].id, removed_couple[1].id)
                ]
            except KeyError:
                """
                logging.error(
                    f"[ {self.env.now} ] Autoscaler tried to scale down "
                    f"{task_type['name']}, but {removed_couple[1]} was already removed"
                )
                """
                pass

        return removed_couple
