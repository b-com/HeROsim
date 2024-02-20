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

import logging
import math

from typing import TYPE_CHECKING, Dict, Set, Tuple

from src.placement.model import PlatformVector, normalize
from src.policy.herocache.model import HRCSchedulerState, HRCSystemState

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform

from src.placement.orchestrator import Orchestrator


class HRCOrchestrator(Orchestrator):
    def initialize_state(self) -> HRCSystemState:
        # Initialize scheduler state
        scheduler_state = HRCSchedulerState(
            average_hardware_contention={
                task_type: {
                    platform: 0.0
                    for platform in self.data.task_types[task_type]["platforms"]
                }
                for task_type in self.data.task_types
            },
            target_concurrencies={
                task_type: {
                    platform: 0.0
                    for platform in self.data.task_types[task_type]["platforms"]
                }
                for task_type in self.data.task_types
            },
        )
        # Initialize target concurrency levels for each task type
        for task_type_name, task_type in self.data.task_types.items():
            # TODO: documentation
            task_platform_values: Dict[str, PlatformVector[float]] = {
                metric: {
                    platform: task_type[metric][platform]
                    for platform in task_type["platforms"]
                }
                for metric in ["coldStartDuration", "executionTime"]
            }

            # print(task_platform_values)

            # FIXME: magic number
            # Bound concurrency targets between CPU level (100 * 1) and (100 * 14)
            # With 14 being the average performance ratio for the three functions
            # between CPU and FPGA platforms
            # t_min = 1
            # t_max = 14
            normalized_values = {
                metric: normalize(vector, 1, 10)
                for metric, vector in task_platform_values.items()
            }

            # FIXME: Do not normalize values before normalizing ratios?
            # normalized_values = task_platform_values

            # FIXME: how to select baseline platform?
            baseline_platform = min(
                self.data.platform_types,
                key=lambda name: self.data.platform_types[name]["price"],
            )

            comparison: Dict[str, PlatformVector] = {
                metric: {
                    platform: (
                        normalized_values[metric][baseline_platform]
                        / normalized_values[metric][platform]
                    )
                    for platform in task_type["platforms"]
                }
                for metric in ["coldStartDuration", "executionTime"]
                # for metric in ["memoryRequirements", "coldStartDuration", "executionTime", "energy"]
            }

            # FIXME: magic number
            # Bound concurrency targets between CPU level (100 * 1) and (100 * 14)
            # With 14 being the average performance ratio for the three functions
            # between CPU and FPGA platforms
            # t_min = 1
            # t_max = 14
            normalized_comparison = {
                metric: normalize(vector, 1, 10)
                for metric, vector in comparison.items()
            }

            # FIXME: Do not normalize ratios?
            normalized_comparison = comparison

            # TODO: Move to JSON configuration file
            # FIXME: magic number
            weights: Dict[str, float] = {
                "coldStartDuration": 4 / 8,
                "executionTime": 4 / 8,
            }

            # Knative default CPU concurrency value (cf. https://knative.dev/docs/serving/autoscaling/concurrency/)
            # FIXME: Compute ideal queue length based on task characterization
            # baseline_concurrency_target = self.policy.queue_length
            """
            baseline_concurrency_targets: Dict[str, float] = {}
            for platform_type_name in task_type["platforms"]:
                # FIXME: Initialization time
                # FIXME: Communications time
                task_total_time: DurationSecond = (
                    task_type["coldStartDuration"][platform_type_name]
                    + task_type["executionTime"][platform_type_name]
                )
                # QoS weight
                buffer_size: DurationSecond = task_total_time * max([qos_type["maxDurationDeviation"] for qos_type in self.data.qos_types.values()])
                # Sum until Q length > WCET
                baseline_concurrency_targets[platform_type_name] = buffer_size / task_total_time
            """

            # FIXME
            baseline_concurrency_target = self.policy.queue_length

            # Compute target concurrencies for all execution platforms
            # FIXME: Tasks are not implemented in all execution platforms!
            scheduler_state.target_concurrencies[task_type_name] = {
                platform: (
                    baseline_concurrency_target
                    if platform == baseline_platform
                    else baseline_concurrency_target
                    * sum(
                        weights[metric] * normalized_comparison[metric][platform]
                        for metric in ["coldStartDuration", "executionTime"]
                    )
                )
                for platform in task_type["platforms"]
            }

            """
            logging.error(
                f"{task_type['name']} target_concurrencies ="
                f" {scheduler_state.target_concurrencies[task_type_name]}"
            )
            """

        # Initialize available resources to all Tuple[Node, Platform]
        available_resources: Dict[Node, Set[Platform]] = {
            node: {platform for platform in set(node.platforms.items)}
            for node in set(self.nodes.items)
        }
        # Initialize function replicas to empty sets
        replicas: Dict[str, Set[Tuple[Node, Platform]]] = {
            task_type: set() for task_type in self.data.task_types
        }
        system_state = HRCSystemState(
            scheduler_state=scheduler_state,
            available_resources=available_resources,
            replicas=replicas,
        )

        return system_state

    def monitor_process(self):
        logging.info(f"[ {self.env.now} ] Orchestrator Monitor started")

        # Initialize time-window average
        latest_window_start = self.env.now

        while True:
            # Step
            step = math.floor(self.env.now - latest_window_start) + 1

            system_state: HRCSystemState = yield self.mutex.get()
            replicas: Dict[str, Set[Tuple[Node, Platform]]] = system_state.replicas
            state: HRCSchedulerState = system_state.scheduler_state

            # Clear average using time-window bounds if necessary
            # FIXME: Implement panic mode (60- vs 6-second time windows)
            if step == 7:
                # Store averages at the granularity of replicas
                for function_name, function_replicas in replicas.items():
                    initial_contention: PlatformVector = {
                        platform: 0.0
                        for platform in self.data.task_types[function_name]["platforms"]
                    }
                    state.average_hardware_contention[function_name] = (
                        initial_contention
                    )
                    # Accumulators
                    for node, platform in function_replicas:
                        # HRC policy
                        state.average_hardware_contention[function_name][
                            platform.type["shortName"]
                        ] += len(platform.queue.items)
                    # Means
                    for hardware_short_name in state.average_hardware_contention[
                        function_name
                    ]:
                        hardware_replicas = [
                            replica
                            for replica in function_replicas
                            if replica[1].type["shortName"] == hardware_short_name
                        ]
                        replicas_count = (
                            len(hardware_replicas) if hardware_replicas else 1
                        )
                        state.average_hardware_contention[function_name][
                            hardware_short_name
                        ] /= replicas_count

                # Update tick time
                latest_window_start = self.env.now
            else:
                # Update contention rolling means
                for function_name, function_replicas in replicas.items():
                    # Accumulators
                    avg_acc: PlatformVector = {
                        platform: 0.0
                        for platform in self.data.task_types[function_name]["platforms"]
                    }

                    for node, platform in function_replicas:
                        # HRC policy
                        hardware_replicas = [
                            replica
                            for replica in function_replicas
                            if replica[1].type["shortName"]
                            == platform.type["shortName"]
                        ]
                        replicas_count = (
                            len(hardware_replicas) if hardware_replicas else 1
                        )
                        avg_acc[platform.type["shortName"]] += (
                            len(platform.queue.items) / replicas_count
                        )

                    for hardware_short_name in avg_acc:
                        hardware_value = (
                            state.average_hardware_contention[function_name][
                                hardware_short_name
                            ]
                            * (step - 1)
                            + avg_acc[hardware_short_name]
                        ) / step
                        state.average_hardware_contention[function_name][
                            hardware_short_name
                        ] = hardware_value

                    # logging.error(f"[ {self.env.now} ] {function_name}: {avg_acc}")

            yield self.mutex.put(system_state)

            # Wake Monitor up once per second
            yield self.env.timeout(1)
