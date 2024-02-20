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

from src.policy.knative.model import KnativeSchedulerState, KnativeSystemState

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform

from src.placement.orchestrator import Orchestrator


class KnativeOrchestrator(Orchestrator):
    def initialize_state(self) -> KnativeSystemState:
        # Initialize scheduler state
        scheduler_state = KnativeSchedulerState(
            average_contention={task_type: {} for task_type in self.data.task_types},
            panic_contention={task_type: {} for task_type in self.data.task_types},
            target_concurrencies={
                task_type: {
                    # platform_type["shortName"]: self.policy.queue_length if platform_type["hardware"] == "cpu" else 0.0
                    platform_type["shortName"]: self.policy.queue_length
                    for platform_type in self.data.platform_types.values()
                }
                for task_type in self.data.task_types
            },
        )
        # Initialize available resources to all Tuple[Node, Platform]
        available_resources: Dict[Node, Set[Platform]] = {
            node: {platform for platform in set(node.platforms.items)}
            for node in set(self.nodes.items)
        }
        # Initialize function replicas to empty sets
        replicas: Dict[str, Set[Tuple[Node, Platform]]] = {
            task_type: set() for task_type in self.data.task_types
        }
        system_state = KnativeSystemState(
            scheduler_state=scheduler_state,
            available_resources=available_resources,
            replicas=replicas,
        )

        return system_state

    def monitor_process(self):
        # TODO: State initialization and update methods should be made abstract
        # and moved to policy package
        logging.info(f"[ {self.env.now} ] Orchestrator Monitor started")

        # Initialize time-window average
        latest_window_start = self.env.now

        while True:
            # Step
            step = math.floor(self.env.now - latest_window_start) + 1

            system_state: KnativeSystemState = yield self.mutex.get()
            replicas: Dict[str, Set[Tuple[Node, Platform]]] = system_state.replicas
            state: KnativeSchedulerState = system_state.scheduler_state

            # Clear average using time-window bounds if necessary
            # FIXME: Implement panic mode (60- vs 6-second time windows)
            if step == 7:
                # Store averages at the granularity of replicas
                for function_name, function_replicas in replicas.items():
                    # Accumulators
                    for node, platform in function_replicas:
                        # Knative policy
                        state.average_contention[function_name][
                            (node.id, platform.id)
                        ] = len(platform.queue.items)

                # Update tick time
                latest_window_start = self.env.now
            else:
                # Update contention rolling means
                for function_name, function_replicas in replicas.items():
                    for node, platform in function_replicas:
                        # Knative policy
                        value = (
                            state.average_contention[function_name][
                                (node.id, platform.id)
                            ]
                            * (step - 1)
                            + len(platform.queue.items)
                        ) / step
                        state.average_contention[function_name][
                            (node.id, platform.id)
                        ] = value

            yield self.mutex.put(system_state)

            # Wake Monitor up once per second
            yield self.env.timeout(1)
