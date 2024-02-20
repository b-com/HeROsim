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
from abc import abstractmethod

import logging
from timeit import default_timer

from simpy.core import Environment
from simpy.events import Process
from simpy.resources.store import Store, FilterStore

from typing import Dict, Generator, Set, Tuple, TYPE_CHECKING

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform, Task
    from src.placement.autoscaler import Autoscaler

from src.placement.model import SimulationData, SimulationPolicy, SystemState
from src.placement.resources import PriorityFilterStore


class Scheduler:
    def __init__(
        self,
        env: Environment,
        mutex: Store,
        data: SimulationData,
        policy: SimulationPolicy,
        autoscaler: Autoscaler,
        nodes: FilterStore,
    ):
        self.env = env
        self.mutex = mutex
        self.data = data
        self.policy = policy
        self.autoscaler = autoscaler

        self.run: Process

        self.nodes = nodes
        self.tasks = PriorityFilterStore(env)

    def scheduler_process(self):
        logging.info(
            f"[ {self.env.now} ] Orchestrator Scheduler started with policy"
            f" {self.policy}"
        )

        while True:
            # TODO: Get tasks for which dependencies are satisfied (finished events)
            # Scheduler will consider tasks with satisfied dependencies,
            # then select according to task priority policy
            # See src.placement.resources.PriorityFilterStore for queue management
            # See Task.__lt__ for selection policies (i.e. EDF and FIFO)
            task: Task = yield self.tasks.get(
                lambda queued_task: all(
                    dependency.finished for dependency in queued_task.dependencies
                )
            )

            logging.info(f"[ {self.env.now} ] Scheduler woken up")

            # Get available replicas
            system_state: SystemState = yield self.mutex.get()
            replicas: Dict[str, Set[Tuple[Node, Platform]]] = system_state.replicas
            task_replicas = replicas[task.type["name"]]

            # Scaling from zero must be forced
            # In-system concurrency cannot increase without replicas
            if not task_replicas:
                logging.warning(
                    f"[ {self.env.now} ] Scheduler did not find available replica for"
                    f" {task}"
                )

                # Put task back in queue
                task.postponed_count += 1
                yield self.tasks.put(task)

                # Request a new replica from the Autoscaler
                stop = yield self.env.process(
                    self.autoscaler.create_first_replica(system_state, task.type)
                )

                # FIXME: Log when no hardware resources available
                # if isinstance(stop, StopIteration):
                # logging.error( ... )

                # Next event
                self.env.step()

                # Release mutex
                yield self.mutex.put(system_state)

                # Next step
                continue

            # Measure wall-clock time for the scheduling decision
            start = default_timer()

            # Schedule tasks according to policy
            (sched_node, sched_platform) = yield self.env.process(
                self.placement(system_state, task)
            )

            # Update node
            node: Node = yield self.nodes.get(lambda node: node.id == sched_node.id)
            task.node = node
            node.unused = False
            # Update platform
            platform: Platform = yield node.platforms.get(
                lambda platform: platform.id == sched_platform.id
            )
            task.platform = platform
            # Update state
            yield self.mutex.put(system_state)

            # End wall-clock time measurement
            end = default_timer()
            elapsed_clock_time = end - start
            node.wall_clock_scheduling_time += elapsed_clock_time

            # TODO: Node cache management?

            yield platform.queue.put(task)
            yield task.scheduled.succeed()

            # Release platform
            yield node.platforms.put(platform)

            # Node is released
            yield self.nodes.put(node)

    @abstractmethod
    def placement(self, system_state: SystemState, task: Task) -> Generator:
        pass
