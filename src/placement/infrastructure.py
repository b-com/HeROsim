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

from typing import Callable, Dict, List, Tuple

from simpy.core import Environment, SimTime
from simpy.resources.store import FilterStore, Store

from src.placement.model import (
    ApplicationResult,
    ApplicationType,
    CacheEvictionError,
    DurationSecond,
    EnergykWh,
    MomentSecond,
    NetworkDescription,
    NodeResult,
    PlatformResult,
    PlatformType,
    QoSType,
    SimulationData,
    SimulationPolicy,
    SizeByte,
    SizeGigabyte,
    SpeedMBps,
    StorageResult,
    StorageType,
    TaskType,
    TaskResult,
)


class Application:
    def __init__(
        self,
        id: int,
        dispatched_time: MomentSecond,
        application_type: ApplicationType,
        qos_type: QoSType,
        tasks: List[Task],
    ):
        self.id = id
        self.type = application_type
        self.qos = qos_type
        self.tasks = tasks

        self.finished = False

        self.dispatched_time: SimTime = dispatched_time
        self.elapsed_time: SimTime = 0
        self.pull_time: SimTime = 0
        self.cold_start_time: SimTime = 0
        self.execution_time: SimTime = 0
        self.communications_time: SimTime = 0
        self.penalty = False

    def __repr__(self):
        return f"Application {self.id} ({self.type['name']})"

    def result(self) -> ApplicationResult:
        # Application total time
        self.elapsed_time = sum(task.elapsed_time for task in self.tasks)
        self.pull_time = sum(task.pull_time for task in self.tasks)
        self.cold_start_time = sum(task.cold_start_time for task in self.tasks)
        self.execution_time = sum(task.execution_time for task in self.tasks)
        self.communications_time = sum(task.communications_time for task in self.tasks)

        """
        # FIXME: Store retrieval duration to avoid re-computing it
        for task in self.tasks:
            if task.node is None or task.platform is None:
                raise KeyError(f"{task} has no Node or Platform")

            retrieval_size: SizeGigabyte = task.type["imageSize"][
                task.platform.type["shortName"]
            ]
            # retrieval_speed: SizeGigabyte = 1.25  # Gigabit link (10 Gbps = 1250 MB/s)
            retrieval_speed: SpeedMBps = task.node.network["bandwidth"]
            retrieval_duration = retrieval_size / (retrieval_speed / 1024)

            self.pull_time += retrieval_duration if not task.cache_hit else 0.0
        """

        # Penalty is True if application finished later than worst case response time
        # Application response time is the sum of the response time of its tasks
        # Values are weighted by QoS maximum allowed deviation
        tasks_wcet: float = sum(
            max(task.type["executionTime"].values()) * self.qos["maxDurationDeviation"]
            for task in self.tasks
        )

        """
        logging.error(f"Application elapsed time: {self.elapsed_time}")
        logging.error(f"Application WCET: {tasks_wcet}")
        logging.error(f"Penalty delta: {self.elapsed_time - tasks_wcet}")
        """

        self.penalty = self.elapsed_time > tasks_wcet

        return {
            "applicationId": self.id,
            "dispatchedTime": self.dispatched_time,
            "elapsedTime": self.elapsed_time,
            "pullTime": self.pull_time,
            "coldStartTime": self.cold_start_time,
            "executionTime": self.execution_time,
            "communicationsTime": self.communications_time,
            "penalty": self.penalty,
        }


class Task:
    def __init__(
        self,
        env: Environment,
        task_id: int,
        task_type: TaskType,
        application: Application,
        dependencies: List[Task],
        policy: SimulationPolicy,
    ):
        self.id = task_id
        self.type = task_type
        self.policy = policy

        self.env = env
        self.run = env.process(self.task_process())

        self.node: Node | None = None
        self.platform: Platform | None = None
        self.storage: Dict[str, Storage | None] = {
            "input": None,
            "output": None,
        }

        self.dispatched = env.event()
        self.scheduled = env.event()
        self.arrived = env.event()
        self.started = env.event()
        self.done = env.event()

        self.application = application
        self.dependencies = dependencies
        self.finished = False

        self.dispatched_time: SimTime
        self.scheduled_time: SimTime
        self.arrived_time: SimTime
        self.started_time: SimTime
        self.done_time: SimTime

        self.energy: EnergykWh = 0.0
        self.cold_started = False
        self.penalty = False
        self.cache_hit = False
        self.local_dependencies = False
        self.local_communications = False

        self.postponed_count: int = 0

        self.wait_time: DurationSecond = 0.0
        self.queue_time: DurationSecond = 0.0
        self.initialization_time: DurationSecond = 0.0

        self.elapsed_time: DurationSecond = 0.0
        self.pull_time: DurationSecond = 0.0
        self.cold_start_time: DurationSecond = 0.0
        self.execution_time: DurationSecond = 0.0
        self.compute_time: DurationSecond = 0.0
        self.communications_time: DurationSecond = 0.0

    def __repr__(self):
        return f"Task {self.id} ({self.type['name']})"

    def __lt__(self, other: Task) -> bool:
        policies: Dict[str, Callable[[], bool]] = {
            # First In, First Out
            "fifo": lambda: self.application.id < other.application.id,
            # Select task with the earliest worse-case deadline first
            "least_penalty": lambda: (
                max(self.type["executionTime"].values())
                * self.application.qos["maxDurationDeviation"]
                < max(other.type["executionTime"].values())
                * other.application.qos["maxDurationDeviation"]
                or self.dispatched_time < other.dispatched_time
            ),
            # Naive least penalty policy
            "naive_least_penalty": lambda: (
                self.dispatched_time < other.dispatched_time
            ),
        }

        return policies[self.policy.priority.tasks]()

    def task_process(self):
        yield self.dispatched
        self.dispatched_time = self.env.now

        logging.info(f"[ {self.env.now} ] 👋 {self} dispatched")

        yield self.scheduled
        self.scheduled_time = self.env.now

        logging.info(
            f"[ {self.env.now} ] ⏲️ {self} scheduled on {self.node}, {self.platform}"
        )

        yield self.arrived
        self.arrived_time = self.env.now

        logging.info(
            f"[ {self.env.now} ] 📦 {self} arrived on {self.node}, {self.platform}"
        )

        yield self.started
        self.started_time = self.env.now

        logging.info(f"[ {self.env.now} ] 🚀 {self} started on {self.platform}")

        yield self.done
        self.done_time = self.env.now

        logging.info(f"[ {self.env.now} ] ✔️ {self} done")

        # Dependencies management
        self.finished = True

        # Assert invariant
        assert self.node is not None and self.platform is not None

        # Save task metrics after completion
        # Task total time, including time to dispatch and task cold start (seconds)
        self.elapsed_time = self.done_time - self.dispatched_time

        # Debug
        self.wait_time = self.scheduled_time - self.dispatched_time
        self.queue_time = self.arrived_time - self.scheduled_time
        self.initialization_time = self.started_time - self.arrived_time
        # Actual task compute time (seconds)
        self.compute_time = self.done_time - self.started_time

        # Assert invariant
        """
        logging.error(f"Elapsed time: {self.elapsed_time}")
        logging.error(f"Compute time: {self.compute_time}")
        logging.error(f"Pull time: {self.pull_time}")
        logging.error(f"Cold start time: {self.cold_start_time}")
        logging.error(f"Execution time: {self.execution_time}")
        logging.error(f"Communications time: {self.communications_time}")

        # FIXME: Pull time is not precise enough
        # Tasks can be scheduled at any point during replica initialization
        task_expected_time = (
            self.pull_time
            + self.cold_start_time
            + self.execution_time
            + self.communications_time
        )

        logging.error(f"[ {self.env.now} ] Task postponed: {self.postponed_count} times")
        logging.error(f"[ {self.env.now} ] {self.type["name"]} Elapsed to expected delta: {self.elapsed_time - task_expected_time}")
        # assert self.elapsed_time == task_expected_time
        """

        # Consumed energy is task energy (kWh) * task compute time (hours)
        self.energy = self.type["energy"][self.platform.type["shortName"]]

    def result(self) -> TaskResult:
        # Null check
        if self.node is None or self.platform is None:
            raise KeyError(f"[ {self.env.now} ] {self} has no Node or Platform")

        return {
            "taskId": self.id,
            "dispatchedTime": self.dispatched_time,
            "scheduledTime": self.scheduled_time,
            "arrivedTime": self.arrived_time,
            "startedTime": self.started_time,
            "doneTime": self.done_time,
            "applicationType": self.application.type,
            "taskType": self.type,
            "platform": self.platform.type,
            "elapsedTime": self.elapsed_time,
            "pullTime": self.pull_time,
            "coldStartTime": self.cold_start_time,
            "executionTime": self.execution_time,
            "waitTime": self.wait_time,
            "queueTime": self.queue_time,
            "initializationTime": self.initialization_time,
            "computeTime": self.compute_time,
            "communicationsTime": self.communications_time,
            "coldStarted": self.cold_started,
            "cacheHit": self.cache_hit,
            "localDependencies": self.local_dependencies,
            "localCommunications": self.local_communications,
            "energy": self.energy,
        }


class Storage:
    def __init__(
        self,
        env: Environment,
        storage_id: int,
        storage_type: StorageType,
        node: Node,
    ):
        self.id = storage_id
        self.type = storage_type
        self.node = node

        self.used: SizeByte = 0
        self.writes: SizeByte = 0
        self.erases: SizeByte = 0

        self.functions_cache: List[Tuple[str, TaskType]] = []
        self.data_store: Dict[int, SizeByte] = {}

        self.total_usage: List[Tuple[SimTime, float]] = []
        self.cache_usage: List[Tuple[SimTime, float]] = []
        self.data_usage: List[Tuple[SimTime, float]] = []

        self.env = env

        self.eviction_policies: Dict[str, Callable[[], None]] = {
            "fifo": self.eviction_fifo,
        }

    def __repr__(self):
        return (
            f"Storage {self.id} ({self.type['name']} (@ {self.node})) --"
            f" {self.get_usage() * 100:.2f}%"
        )

    def result(self) -> StorageResult:
        return {
            "storageId": self.id,
            "totalUsage": self.total_usage,
            "cacheUsage": self.cache_usage,
            "dataUsage": self.data_usage,
        }

    def cache_eviction(self) -> bool:
        try:
            self.eviction_policies[self.node.policy.cache]()
            return True
        except CacheEvictionError as e:
            logging.error(f"[ {self.env.now} ] {e.message}")
            return False

    def eviction_fifo(self) -> None:
        # Pop first element from dictionary
        # first_key = next(iter(self.functions_cache))
        # removed = self.functions_cache.pop(first_key)

        # Pop oldest function image from functions cache
        try:
            removed_platform, removed_type = self.functions_cache.pop(0)

            logging.info(
                f"[ {self.env.now} ] Removed {removed_type} ({removed_platform}) from"
                f" {self}"
            )

            # Update disk usage
            self.used -= int(removed_type["imageSize"][removed_platform] * 1e9)
        except IndexError:
            raise CacheEvictionError(f"{self} function cache is already empty")

    def has_function(self, platform: str, task_type: TaskType) -> bool:
        return (platform, task_type) in self.functions_cache

    def has_data(self, task_id: int) -> bool:
        return task_id in self.data_store

    def get_cache_volume(self) -> SizeGigabyte:
        current_function_volume: SizeGigabyte = sum(
            task_type["imageSize"][platform]
            for (platform, task_type) in self.functions_cache
        )

        return current_function_volume

    def get_data_volume(self) -> SizeGigabyte:
        current_data_volume: SizeByte = sum(self.data_store.values())

        return current_data_volume * 1e-9

    def get_usage(self) -> float:
        current_function_volume: SizeGigabyte = self.get_cache_volume()
        current_data_volume: SizeGigabyte = self.get_data_volume()

        total_gigabytes: SizeGigabyte = current_function_volume + current_data_volume

        return total_gigabytes / self.type["capacity"]

    def store_function(self, platform: str, task_type: TaskType) -> bool:
        if (platform, task_type) not in self.functions_cache:
            while (self.used * 1e-9) + task_type["imageSize"][platform] > self.type[
                "capacity"
            ]:
                try:
                    self.cache_eviction()
                except CacheEvictionError as e:
                    logging.error(f"[ {self.env.now} ] {e.message}")
                    return False

            self.functions_cache.append((platform, task_type))
            self.used += int(task_type["imageSize"][platform] * 1e9)

            # Statistics
            self.writes += int(task_type["imageSize"][platform] * 1e9)
            self.cache_usage.append(
                (self.env.now, (self.get_cache_volume() / self.type["capacity"]) * 100)
            )
            self.total_usage.append((self.env.now, self.get_usage() * 100))

        return True

    def remove_function(self, platform: str, task_type: TaskType) -> bool:
        try:
            self.functions_cache.remove((platform, task_type))
        except ValueError:
            logging.error(
                f"[ {self.env.now} ] Error trying to remove {task_type['name']} from"
                f" {self}"
            )
            return False

        # Update disk usage
        self.used -= int(task_type["imageSize"][platform] * 1e9)

        logging.info(f"[ {self.env.now} ] Removed {task_type['name']} from {self}")

        # Statistics
        self.erases += int(task_type["imageSize"][platform] * 1e9)
        self.cache_usage.append(
            (self.env.now, (self.get_cache_volume() / self.type["capacity"]) * 100)
        )
        self.total_usage.append((self.env.now, self.get_usage() * 100))

        return True

    def store_data(self, task: Task) -> bool:
        task_state = task.type["stateSize"][task.application.type["name"]]
        # Cache eviction if disk capacity is reached
        while (self.used + task_state["output"]) * 1e-9 > self.type["capacity"]:
            try:
                self.cache_eviction()
            except CacheEvictionError as e:
                logging.error(f"[ {self.env.now} ] {e.message}")
                return False

        # Store data
        self.data_store[task.id] = task_state["output"]

        # Update disk usage
        self.used += task_state["output"]

        logging.info(
            f"[ {self.env.now} ] Stored {task_state['output']}"
            f" bytes for {task} on {self}"
        )

        # Statistics
        self.writes += task_state["output"]
        self.data_usage.append(
            (self.env.now, (self.get_data_volume() / self.type["capacity"]) * 100)
        )
        self.total_usage.append((self.env.now, self.get_usage() * 100))

        return True

    def remove_data(self, task: Task) -> bool:
        try:
            del self.data_store[task.id]
        except KeyError:
            logging.error(
                f"[ {self.env.now} ] Data for {task} was not stored on {self}"
            )
            return False

        # Update disk usage
        task_state = task.type["stateSize"][task.application.type["name"]]
        self.used -= task_state["output"]

        logging.info(
            f"[ {self.env.now} ] Removed {task_state['output']}"
            f" bytes for {task} from {self}"
        )

        # Statistics
        self.erases += task_state["output"]
        self.data_usage.append(
            (self.env.now, (self.get_data_volume() / self.type["capacity"]) * 100)
        )
        self.total_usage.append((self.env.now, self.get_usage() * 100))

        return True


class Platform:
    def __init__(
        self,
        env: Environment,
        platform_id: int,
        platform_type: PlatformType,
        node: Node,
    ):
        self.id = platform_id
        self.type = platform_type
        self.node = node

        self.env = env
        self.run = env.process(self.platform_process())

        self.queue = Store(env)

        self.previous_task: Task | None = None
        self.current_task: Task | None = None
        self.idle_since: SimTime = math.inf

        self.last_allocated: SimTime = math.inf
        self.last_removed: SimTime = math.inf

        self.load_time: SimTime = 0
        self.storage_time: SimTime = 0

        self.initialized = env.event()
        self.tasks_count: int = 0
        self.local_dependencies: int = 0
        self.cache_hits: int = 0

    def __repr__(self):
        return f"Platform {self.id} ({self.type['name']})"

    def result(self) -> PlatformResult:
        idle_time = self.env.now - self.load_time

        """
        print(
            f"{self} local dependencies % = "
            f"{(self.local_dependencies / self.tasks_count) * 100}"
        )
        """

        return {
            "platformId": self.id,
            "platformType": self.type,
            "energy": self.type["idleEnergy"] * (self.env.now / 3600),
            "energyIdle": self.type["idleEnergy"] * (idle_time / 3600),
            "idleTime": idle_time,
            "idleProportion": (idle_time / self.env.now) * 100,
            "storageTime": self.storage_time,
        }

    def platform_process(self):
        logging.info(f"[ {self.env.now} ] {self} started")

        while True:
            # Wait for replica initialization
            before_initialize = self.env.now
            yield self.initialized
            after_initialize = self.env.now

            # FIFO task selection in platform queue
            task: Task = yield self.queue.get()

            # Statistics (Task)
            task.cache_hit = after_initialize == before_initialize
            task.pull_time = (
                after_initialize - before_initialize if not task.cache_hit else 0.0
            )

            # Initialize the task
            yield task.arrived.succeed()

            # Update platform cache
            self.current_task = task

            # Check node RAM cache
            warm_function: bool = (
                self.previous_task is not None
                and self.previous_task.type["name"] == task.type["name"]
            )

            # Cold start penalty is not incurred if task sandbox was in cache
            initialization_duration = (
                task.type["coldStartDuration"][self.type["shortName"]]
                if not warm_function
                else 0.0
            )

            # Compute total cold start duration
            cold_start_duration: float = initialization_duration

            if cold_start_duration > 0:
                task.cold_started = True

                logging.info(
                    f"[ {self.env.now} ] ❄️ {task} cold start (duration:"
                    f" {cold_start_duration}) on {self}"
                )

            # Cold start timeout
            yield self.env.timeout(cold_start_duration)
            task.cold_start_time = cold_start_duration

            # Retrieve input data
            input_storage: Storage
            output_storage: Storage
            local_dependencies = True

            # Does the task have dependencies?
            if task.dependencies:
                # If task dependencies were executed on the same node,
                # local storage is used to retrieve input values
                # FIXME: Check node storage to ensure data are indeed stored locally
                local_dependencies = all(
                    [
                        dependency.storage["output"] in self.node.storage.items
                        for dependency in task.dependencies
                    ]
                )

            # Statistics (Platform)
            self.tasks_count += 1
            # Statistics (Node)
            self.node.local_dependencies += local_dependencies
            # Statistics (Task)
            task.local_dependencies = local_dependencies

            # FIXME: First task gets input data from remote storage
            if task.dependencies and local_dependencies:
                # Local storage
                # We read input data from the output storage of the previous task
                # FIXME: Support more complex application DAGs
                input_storage = yield self.node.storage.get(
                    # lambda storage: not storage.type["remote"]
                    lambda storage: storage
                    == task.dependencies[-1].storage["output"]
                )
            else:
                # Remote storage
                logging.warning(
                    f"[ {self.env.now} ] {task} input fetched from remote storage"
                )
                input_storage = yield self.node.storage.get(
                    lambda storage: storage.type["remote"]
                )

            # Update task
            task.storage["input"] = input_storage
            yield self.node.storage.put(input_storage)

            # Process input
            # FIXME: First task of an application gets input from network!
            input_speed: SpeedMBps = (
                (input_storage.type["throughput"]["read"])
                if not input_storage.type["remote"]
                else min(
                    input_storage.type["throughput"]["read"],
                    self.node.network["bandwidth"],
                )
            )
            input_duration: SimTime = (
                task.type["stateSize"][task.application.type["name"]]["input"]
                / (input_speed * 1024 * 1024)
                + input_storage.type["latency"]["read"]
            )

            # Start the task
            yield task.started.succeed()

            # Retrieve input data
            yield self.env.timeout(input_duration)
            # task.application.communications_time += input_duration

            # Retrieve task duration according to platform hardware
            task_duration = task.type["executionTime"][self.type["shortName"]]

            logging.info(f"[ {self.env.now} ] {self} started {task} execution")

            # Run the task to completion
            yield self.env.timeout(task_duration)
            task.execution_time = task_duration

            # Store output data
            # FIXME: Remote storage? Local node?
            if local_dependencies:
                # Local storage
                output_storage = yield self.node.storage.get(
                    lambda storage: not storage.type["remote"]
                )
            else:
                # Remote storage
                output_storage = yield self.node.storage.get(
                    lambda storage: storage.type["remote"]
                )
                logging.info(
                    f"[ {self.env.now} ] {task} output stored in remote storage"
                )

            # TODO: Store output data
            output_stored = output_storage.store_data(task)

            if not output_stored:
                # FIXME: Resort to remote storage
                output_storage = yield self.node.storage.get(
                    lambda storage: storage.type["remote"]
                )
                pass

            # FIXME: Update task
            task.storage["output"] = output_storage
            yield self.node.storage.put(output_storage)

            # FIXME: Network link performance!
            output_speed: SpeedMBps = (
                (output_storage.type["throughput"]["write"])
                if not input_storage.type["remote"]
                else min(
                    output_storage.type["throughput"]["write"],
                    self.node.network["bandwidth"],
                )
            )
            output_duration: SimTime = (
                task.type["stateSize"][task.application.type["name"]]["output"]
                / (output_speed * 1024 * 1024)
                + output_storage.type["latency"]["write"]
            )
            # Wait for I/O completion
            # It allows workflow_process() to dispatch next task in workflow
            # without checking for input data
            yield self.env.timeout(output_duration)
            # task.application.communications_time += output_duration

            # Update platform cache
            self.previous_task = self.current_task
            self.current_task = None
            self.idle_since = self.env.now

            # Update platform load time
            self.load_time += cold_start_duration + task_duration

            # TODO: Update platform storage time
            # task_storage_time = retrieval_duration + input_duration + output_duration
            task_storage_time = input_duration + output_duration
            self.storage_time += task_storage_time

            # Statistics (Task)
            task.local_communications = all(
                [
                    not storage.type["remote"] if storage is not None else False
                    for storage in task.storage.values()
                ]
            )
            # task.storage_time = task_storage_time
            task.communications_time = task_storage_time

            # Notify scheduler of task completion
            yield task.done.succeed()


class Node:
    def __init__(
        self,
        env: Environment,
        node_id: int,
        memory: float,
        platforms: FilterStore,
        storage: FilterStore,
        network: NetworkDescription,
        policy: SimulationPolicy,
        data: SimulationData,
    ):
        self.id = node_id
        self.memory = memory
        self.platforms = platforms
        self.storage = storage
        self.network = network
        self.policy = policy
        self.data = data

        self.env = env

        self.available_platforms = 0
        self.available_memory = memory

        self.unused = True

        self.wall_clock_scheduling_time: float = 0

        self.local_dependencies: int = 0
        self.cache_hits: int = 0

    def __repr__(self):
        return f"Node {self.id}"

    def result(self) -> NodeResult:
        platform_results: List[PlatformResult] = [
            platform.result() for platform in self.platforms.items
        ]

        storage_results: List[StorageResult] = [
            storage.result() for storage in self.storage.items
        ]

        return {
            "nodeId": self.id,
            "unused": self.unused,
            "energy": {
                platform.type["shortName"]: sum(
                    platform_result["energy"]
                    for platform_result in platform_results
                    if platform_result["platformType"]["shortName"]
                    == platform.type["shortName"]
                )
                for platform in self.platforms.items
            },
            "energyIdle": {
                platform.type["shortName"]: sum(
                    platform_result["energyIdle"]
                    for platform_result in platform_results
                    if platform_result["platformType"]["shortName"]
                    == platform.type["shortName"]
                )
                for platform in self.platforms.items
            },
            "idleTime": {
                platform.type["shortName"]: sum(
                    platform_result["idleTime"]
                    for platform_result in platform_results
                    if platform_result["platformType"]["shortName"]
                    == platform.type["shortName"]
                )
                for platform in self.platforms.items
            },
            "schedulingTime": self.wall_clock_scheduling_time,
            "storageTime": sum(
                platform_result["storageTime"] for platform_result in platform_results
            ),
            "localDependencies": self.local_dependencies,
            "cacheHits": self.cache_hits,
            "platformResults": platform_results,
            "storageResults": storage_results,
        }
