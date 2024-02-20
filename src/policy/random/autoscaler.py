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
    from src.placement.infrastructure import Node, Platform

from src.placement.model import TaskType

from src.placement.autoscaler import Autoscaler


class RandomAutoscaler(Autoscaler):
    def create_replica(
        self, couples_suitable: Set[Tuple[Node, Platform]], task_type: TaskType
    ):
        # Scaling functions that do not yield values must still be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        # Select random platform
        found = random.randint(0, len(couples_suitable) - 1)
        random_couple = list(couples_suitable)[found]

        return random_couple

    def remove_replica(
        self, function_replicas: Set[Tuple[Node, Platform]], task_type: TaskType
    ):
        # Scaling functions that do not yield values must still be Generators
        # No-op as per https://stackoverflow.com/a/68628599/9568489
        if False:
            yield

        # Array is shuffled in place...
        random.shuffle(list(function_replicas))

        # Mark replica for removal if its task queue is empty
        # Return None if no replica can be removed
        removed_couple = next(
            (
                replica
                for replica in function_replicas
                if not replica[1].queue.items and not replica[1].current_task
            ),
            None,
        )

        return removed_couple

    # TODO
    def create_first_replica(self):
        pass
