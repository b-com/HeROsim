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

import random

from typing import Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform, Task

from src.placement.model import SystemState

from src.placement.scheduler import Scheduler


class RandomScheduler(Scheduler):
    def placement(self, system_state: SystemState, task: Task):
        # Scheduling functions called in a Simpy Process must be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        replicas: Set[Tuple[Node, Platform]] = system_state.replicas[task.type["name"]]

        # Select random platform
        found = random.randint(0, len(replicas) - 1)
        random_couple = list(replicas)[found]

        return random_couple
