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
import statistics

from graphlib import TopologicalSorter

from simpy.core import Environment, SimTime
from simpy.events import Event, Process
from simpy.resources.store import Store, FilterStore

from typing import Dict, Generator, List, Tuple, Type

from src.placement.infrastructure import Application, Task
from src.placement.autoscaler import Autoscaler
from src.placement.scheduler import Scheduler

from src.placement.model import (
    ApplicationResult,
    MomentSecond,
    NodeResult,
    PlatformResult,
    SimulationData,
    SimulationPolicy,
    SystemState,
    TaskResult,
    SimulationStats,
    TimeSeries,
    WorkloadEvent,
)


class Orchestrator:
    def __init__(
        self,
        env: Environment,
        data: SimulationData,
        policy: SimulationPolicy,
        autoscaler: Type[Autoscaler],
        scheduler: Type[Scheduler],
        time_series: TimeSeries,
        nodes: FilterStore,
        end_event: Event,
    ):
        self.env = env
        self.mutex = Store(env, capacity=1)
        self.data = data
        self.policy = policy

        self.time_series = time_series
        self.nodes = nodes

        self.gateway: Process
        self.monitor: Process
        self.autoscaler = autoscaler(self.env, self.mutex, self.data, self.policy)
        self.scheduler = scheduler(
            self.env, self.mutex, self.data, self.policy, self.autoscaler, self.nodes
        )
        self.initializer = env.process(self.initializer_process())

        self.end_event = end_event
        self.end_time: SimTime

        self.application_archive: List[Application] = []
        self.task_archive: List[Task] = []

    def stats(self) -> SimulationStats:
        try:
            application_results: List[ApplicationResult] = [
                application.result() for application in self.application_archive
            ]
            task_results: List[TaskResult] = [
                task.result() for task in self.task_archive
            ]
            node_results: List[NodeResult] = [
                node.result() for node in self.nodes.items
            ]
            platform_results: List[PlatformResult] = [
                platform.result()
                for node in self.nodes.items
                for platform in node.platforms.items
            ]
        except KeyError as e:
            raise e

        # Unused platforms (% of platform count)
        unused_platforms = len(
            [
                platform_result
                for platform_result in platform_results
                if platform_result["idleProportion"] == 100
            ]
        ) / len(platform_results)

        # Unused nodes (% of node count)
        unused_nodes = len(
            [node_result for node_result in node_results if node_result["unused"]]
        ) / len(node_results)

        # Average resource occupation time
        resources_occupation: Dict[int, float] = {}
        for platform_result in sorted(
            platform_results, key=lambda result: result["platformId"]
        ):
            """
            logging.error(
                f"{platform_result['platformId']}"
                f" ({platform_result['platformType']['hardware']})"
                f" -- {round(100 - platform_result['idleProportion'], 2)}%"
            )
            """
            resources_occupation[platform_result["platformId"]] = (
                100 - platform_result["idleProportion"]
            )

        average_occupation = sum(resources_occupation.values()) / len(
            resources_occupation
        )

        print("Scheduling times on each node:")
        print(
            *(node_result["schedulingTime"] for node_result in node_results), sep="\n"
        )

        average_elapsed_time = sum(
            task_result["elapsedTime"] for task_result in task_results
        ) / len(task_results)
        average_pull_time = sum(
            task_result["pullTime"] for task_result in task_results
        ) / len(task_results)
        average_cold_start_time = sum(
            task_result["coldStartTime"] for task_result in task_results
        ) / len(task_results)
        average_execution_time = sum(
            task_result["executionTime"] for task_result in task_results
        ) / len(task_results)
        average_wait_time = sum(
            task_result["waitTime"] for task_result in task_results
        ) / len(task_results)
        average_queue_time = sum(
            task_result["queueTime"] for task_result in task_results
        ) / len(task_results)
        average_initialization_time = sum(
            task_result["initializationTime"] for task_result in task_results
        ) / len(task_results)
        average_compute_time = sum(
            task_result["computeTime"] for task_result in task_results
        ) / len(task_results)
        average_communications_time = sum(
            task_result["communicationsTime"] for task_result in task_results
        ) / len(task_results)

        energy_total = sum(task_result["energy"] for task_result in task_results) + sum(
            platform_result["energyIdle"] for platform_result in platform_results
        )

        unused_nodes_idle_energy = [
            node_result["energyIdle"]
            for node_result in node_results
            if node_result["unused"]
        ]
        unused_platforms_idle_energy = [
            sum(unused_platforms.values())
            for unused_platforms in unused_nodes_idle_energy
        ]
        reclaimable_energy = sum(unused_platforms_idle_energy)

        penalty_proportion = sum(
            application_result["penalty"] for application_result in application_results
        ) / len(application_results)

        local_dependencies_proportion = sum(
            task_result["localDependencies"] for task_result in task_results
        ) / len(task_results)
        local_communications_proportion = sum(
            task_result["localCommunications"] for task_result in task_results
        ) / len(task_results)

        cold_start_proportion = sum(
            task_result["coldStarted"] for task_result in task_results
        ) / len(task_results)
        node_cache_hits_proportion = sum(
            node_result["cacheHits"] for node_result in node_results
        ) / len(task_results)
        task_cache_hit_proportion = sum(
            task_result["cacheHit"] for task_result in task_results
        ) / len(task_results)

        task_response_time_quantiles = statistics.quantiles(
            [task["elapsedTime"] for task in task_results], n=100
        )
        application_response_time_quantiles = statistics.quantiles(
            [application["elapsedTime"] for application in application_results], n=100
        )

        # Sort task results by arrival time
        # Filter out non-penalty tasks
        penalty_distribution_over_time: List[Tuple[MomentSecond, float]] = []
        applications_count = 0
        distribution = 0
        for application_result in sorted(
            application_results, key=lambda app_res: app_res["dispatchedTime"]
        ):
            applications_count += 1
            if application_result["penalty"]:
                distribution += 1
                penalty_distribution_over_time.append(
                    (
                        application_result["dispatchedTime"],
                        distribution / applications_count,
                    )
                )

        return {
            "policy": self.policy,
            "endTime": self.end_time,
            "unusedPlatforms": unused_platforms * 100,
            "unusedNodes": unused_nodes * 100,
            "averageOccupation": average_occupation,
            "averageElapsedTime": average_elapsed_time,
            "averagePullTime": average_pull_time,
            "averageColdStartTime": average_cold_start_time,
            "averageExecutionTime": average_execution_time,
            "averageWaitTime": average_wait_time,
            "averageQueueTime": average_queue_time,
            "averageInitializationTime": average_initialization_time,
            "averageComputeTime": average_compute_time,
            "averageCommunicationsTime": average_communications_time,
            "penaltyProportion": penalty_proportion * 100,
            "localDependenciesProportion": local_dependencies_proportion * 100,
            "localCommunicationsProportion": local_communications_proportion * 100,
            "nodeCacheHitsProportion": node_cache_hits_proportion * 100,
            "taskCacheHitsProportion": task_cache_hit_proportion * 100,
            "coldStartProportion": cold_start_proportion * 100,
            "taskResponseTimeDistribution": task_response_time_quantiles,
            "applicationResponseTimeDistribution": application_response_time_quantiles,
            "penaltyDistributionOverTime": penalty_distribution_over_time,
            "energy": energy_total,
            "reclaimableEnergy": reclaimable_energy,
            "applicationResults": application_results,
            "nodeResults": node_results,
            "taskResults": task_results,
            "scaleEvents": self.autoscaler.scale_events,
        }

    def create_application(
        self, env: Environment, app_id: int, task_id: int, event: WorkloadEvent
    ) -> Application:
        application_type = event["application"]
        qos_type = event["qos"]

        application_tasks: List[Task] = []
        application = Application(
            id=app_id,
            dispatched_time=event["timestamp"],
            application_type=application_type,
            qos_type=qos_type,
            tasks=application_tasks,
        )

        # TODO: Traverse application DAG
        sorter = TopologicalSorter(application_type["dag"])
        ordered = tuple(sorter.static_order())

        # TODO: Create dependencies
        dependencies: Dict[str, List[Task]] = {}
        function_tasks: Dict[str, Task] = {}

        for function_name in ordered:
            if function_name not in dependencies:
                dependencies[function_name] = []

            function_task = Task(
                env=env,
                task_id=task_id,
                task_type=self.data.task_types[function_name],
                application=application,
                dependencies=dependencies[function_name],
                policy=self.policy,
            )

            task_id += 1
            application_tasks.append(function_task)
            function_tasks[function_name] = function_task

        for function_name in ordered:
            predecessors = application_type["dag"][function_name]

            for predecessor_name in predecessors:
                dependencies[function_name].append(function_tasks[predecessor_name])

        return application

    @abstractmethod
    def initialize_state(self) -> SystemState:
        pass

    def initializer_process(self) -> Generator:
        # Initialize shared data structures according to simulation policy
        system_state: SystemState = self.initialize_state()
        # Putting it all together...
        yield self.mutex.put(system_state)

        # Begin orchestration
        self.gateway = self.env.process(self.gateway_process())
        self.monitor = self.env.process(self.monitor_process())
        self.autoscaler.run = self.env.process(self.autoscaler.autoscaler_process())
        self.scheduler.run = self.env.process(self.scheduler.scheduler_process())

    @abstractmethod
    def monitor_process(self) -> Generator:
        pass

    def workflow_process(self, task: Task) -> Generator:
        # Find next task in the application
        task_dag = task.application.type["dag"]
        sorter = TopologicalSorter(task_dag)
        ordered = tuple(sorter.static_order())
        current_index = ordered.index(task.type["name"])

        # If current task is the last task of the application, clear application data
        # FIXME
        # first_task = task.application.tasks[0]
        # first_task.storage["input"].remove_data(first_task)
        if current_index == len(ordered) - 1:
            for application_task in task.application.tasks:
                application_task.storage["input"]
                output_storage = application_task.storage["output"]

                if output_storage:
                    output_storage.remove_data(application_task)

            return

        # Else, schedule next task to be run after current task finishes its execution
        next_task_name = ordered[current_index + 1]
        next_task = next(
            filter(
                lambda app_task: app_task.type["name"] == next_task_name,
                task.application.tasks,
            )
        )

        # Wait for current task execution
        yield task.done

        # Dispatch next task
        yield next_task.dispatched.succeed()

        # Put next task in scheduler queue
        yield self.scheduler.tasks.put(next_task)

        # Monitor workflow execution
        self.env.process(self.workflow_process(next_task))

    def gateway_process(self) -> Generator:
        logging.info(f"[ {self.env.now} ] API Gateway started")

        app_id = 0
        task_id = 0

        while self.time_series.events:
            # Process workload events (FIFO)
            workload_event: WorkloadEvent = self.time_series.events.pop(0)

            # Timeout until event timestamp
            yield self.env.timeout(workload_event["timestamp"] - self.env.now)

            # Create the application according to the event properties
            app = self.create_application(
                env=self.env,
                app_id=app_id,
                task_id=task_id,
                event=workload_event,
            )

            # Increment application and task IDs
            app_id += 1
            task_id += len(app.tasks)

            # Tasks are stored in an archive for further analysis
            self.application_archive.append(app)
            self.task_archive.extend(app.tasks)

            # Start counting first task time from here
            first_task: Task = app.tasks[0]
            yield first_task.dispatched.succeed()

            # Subsequent tasks in application DAG will be dispatched later
            # workflow_process waits for task completion before dispatching next task
            self.env.process(self.workflow_process(first_task))

            # Tasks are stored in a queue to be scheduled on execution platforms
            # See scheduler_process()
            yield self.scheduler.tasks.put(first_task)

        # Simulation ends when:
        #  - all platforms are released
        #  - all tasks are done
        yield self.env.all_of([task.done for task in self.task_archive])

        # End simulation
        self.end_time = self.env.now
        yield self.end_event.succeed()
