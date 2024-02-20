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

from typing import Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform, Task

from src.placement.model import SchedulerState, SystemState

from src.placement.scheduler import Scheduler


class RoundRobinScheduler(Scheduler):
    def placement(self, system_state: SystemState, task: Task):
        # Scheduling functions called in a Simpy Process must be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        replicas: Set[Tuple[Node, Platform]] = system_state.replicas[task.type["name"]]
        state: SchedulerState = system_state.scheduler_state

        # Find least scheduled replica
        least_scheduled = min(
            replicas,
            key=lambda couple: state.scheduled_count[task.type["name"]][
                (couple[0].id, couple[1].id)
            ],
        )

        # Update scheduler state
        state.scheduled_count[task.type["name"]][
            (least_scheduled[0].id, least_scheduled[1].id)
        ] += 1

        return least_scheduled
