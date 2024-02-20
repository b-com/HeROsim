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

import dataclasses
import json
import os

from dataclasses import dataclass
from typing import (
    Dict,
    List,
    Literal,
    Set,
    Tuple,
    TypedDict,
    TYPE_CHECKING,
    final,
)

if TYPE_CHECKING:
    from src.placement.infrastructure import Node, Platform

from dataclasses_json import DataClassJsonMixin, LetterCase, dataclass_json

from simpy.core import SimTime


type MoneyEuro = float

type EnergykWh = float

type SizeByte = int
type SizeMegabyte = float
type SizeGigabyte = float

type SpeedMBps = float

type DurationMillisecond = SimTime
type DurationSecond = SimTime

type MomentSecond = SimTime


def dir_path(string):
    if os.path.isdir(string):
        return string
    else:
        raise NotADirectoryError(string)


def restricted_float(x):
    try:
        x = float(x)
    except ValueError:
        return 0

    if x < 0.0:
        return 0.0

    return x


def positive_int(x):
    try:
        x = int(x)
    except ValueError:
        return 0

    if x < 1:
        return 1

    return x


def normalize(vector: PlatformVector, t_min: int, t_max: int) -> PlatformVector:
    # https://stats.stackexchange.com/a/281164
    # https://stats.stackexchange.com/a/178629

    # FIXME
    denominator = max(vector.values()) - min(vector.values())
    if denominator == 0:
        denominator = 1

    return {
        platform: ((value - min(vector.values())) / denominator) * (
            t_max - t_min
        ) + t_min
        for platform, value in vector.items()
    }


type PlatformVector[T] = Dict[str, T]


@final
class IOVector(TypedDict):
    input: SizeByte
    output: SizeByte


@final
class RWVector[T](TypedDict):
    read: T
    write: T


@final
class PlatformType(TypedDict):
    shortName: str
    name: str
    hardware: str
    price: MoneyEuro
    idleEnergy: EnergykWh


@final
class StorageType(TypedDict):
    name: str
    hardware: str
    price: MoneyEuro
    remote: bool
    idleEnergy: EnergykWh
    capacity: SizeGigabyte
    iops: RWVector[int]
    throughput: RWVector[SpeedMBps]
    latency: RWVector[DurationSecond]


@final
class QoSType(TypedDict):
    name: str
    maxDurationDeviation: float


@final
class TaskType(TypedDict):
    name: str
    platforms: List[str]
    memoryRequirements: PlatformVector
    coldStartDuration: PlatformVector
    executionTime: PlatformVector
    energy: PlatformVector
    imageSize: PlatformVector
    stateSize: Dict[str, IOVector]


@final
class ApplicationType(TypedDict):
    name: str
    dag: Dict[str, List[str]]


@final
class NodeDescription(TypedDict):
    memory: SizeGigabyte
    platforms: List[str]
    storage: List[str]


@final
class NetworkDescription(TypedDict):
    bandwidth: SpeedMBps


@final
class MinMax(TypedDict):
    min: float
    max: float


@final
class Infrastructure(TypedDict):
    network: NetworkDescription
    nodes: List[NodeDescription]


@final
class PlatformResult(TypedDict):
    platformId: int
    platformType: PlatformType
    energy: EnergykWh
    energyIdle: EnergykWh
    idleTime: DurationSecond
    idleProportion: float
    storageTime: DurationSecond


@final
class NodeResult(TypedDict):
    nodeId: int
    unused: bool
    energy: PlatformVector
    energyIdle: PlatformVector
    idleTime: PlatformVector
    schedulingTime: DurationSecond
    storageTime: DurationSecond
    localDependencies: int
    cacheHits: int
    platformResults: List[PlatformResult]
    storageResults: List[StorageResult]


@final
class ApplicationResult(TypedDict):
    applicationId: int
    dispatchedTime: MomentSecond
    elapsedTime: DurationSecond
    pullTime: DurationSecond
    coldStartTime: DurationSecond
    executionTime: DurationSecond
    communicationsTime: DurationSecond
    penalty: bool


@final
class TaskResult(TypedDict):
    taskId: int
    dispatchedTime: MomentSecond
    scheduledTime: MomentSecond
    arrivedTime: MomentSecond
    startedTime: MomentSecond
    doneTime: MomentSecond
    applicationType: ApplicationType
    taskType: TaskType
    platform: PlatformType
    elapsedTime: DurationSecond
    pullTime: DurationSecond
    coldStartTime: DurationSecond
    executionTime: DurationSecond
    waitTime: DurationSecond
    queueTime: DurationSecond
    initializationTime: DurationSecond
    computeTime: DurationSecond
    communicationsTime: DurationSecond
    coldStarted: bool
    cacheHit: bool
    localDependencies: bool
    localCommunications: bool
    energy: EnergykWh


@final
class StorageResult(TypedDict):
    storageId: int
    totalUsage: List[Tuple[MomentSecond, float]]
    cacheUsage: List[Tuple[MomentSecond, float]]
    dataUsage: List[Tuple[MomentSecond, float]]


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(frozen=True)
class PriorityPolicy(DataClassJsonMixin):
    tasks: str


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(frozen=True)
class SimulationPolicy(DataClassJsonMixin):
    priority: PriorityPolicy
    scheduling: str
    cache: str
    keep_alive: DurationSecond
    queue_length: int
    short_name: str

    def __lt__(self, other: SimulationPolicy):
        return str(self) < str(other)

    def __str__(self):
        return f"{self.short_name}"


class WorkloadEvent(TypedDict):
    timestamp: MomentSecond
    application: ApplicationType
    qos: QoSType
    # data: SizeByte


@dataclass_json(letter_case=LetterCase.CAMEL)
@dataclass(frozen=True)
class TimeSeries(DataClassJsonMixin):
    rps: int
    duration: int
    events: List[WorkloadEvent]


@final
class ScaleEvent(TypedDict):
    name: str
    timestamp: MomentSecond
    action: Literal["up"] | Literal["down"]
    count: int
    average_queue_length: float


@dataclass
class SimulationData:
    platform_types: Dict[str, PlatformType]
    storage_types: Dict[str, StorageType]
    qos_types: Dict[str, QoSType]
    application_types: Dict[str, ApplicationType]
    task_types: Dict[str, TaskType]


@dataclass
class SchedulerState:
    target_concurrencies: Dict[str, PlatformVector]


@dataclass
class SystemState:
    scheduler_state: SchedulerState
    available_resources: Dict["Node", Set["Platform"]]
    replicas: Dict[str, Set[Tuple["Node", "Platform"]]]


@final
class SimulationStats(TypedDict):
    policy: SimulationPolicy
    endTime: MomentSecond
    unusedPlatforms: float
    unusedNodes: float
    averageOccupation: float
    averageElapsedTime: DurationSecond
    averagePullTime: DurationSecond
    averageColdStartTime: DurationSecond
    averageExecutionTime: DurationSecond
    averageWaitTime: DurationSecond
    averageQueueTime: DurationSecond
    averageInitializationTime: DurationSecond
    averageComputeTime: DurationSecond
    averageCommunicationsTime: DurationSecond
    penaltyProportion: float
    coldStartProportion: float
    localDependenciesProportion: float
    localCommunicationsProportion: float
    nodeCacheHitsProportion: float
    taskCacheHitsProportion: float
    taskResponseTimeDistribution: List[float]
    applicationResponseTimeDistribution: List[float]
    penaltyDistributionOverTime: List[Tuple[MomentSecond, float]]
    energy: EnergykWh
    reclaimableEnergy: EnergykWh
    applicationResults: List[ApplicationResult]
    nodeResults: List[NodeResult]
    taskResults: List[TaskResult]
    scaleEvents: List[ScaleEvent]


@final
class ChartsResults(TypedDict):
    energyTotals: List[EnergykWh]
    unusedPlatforms: List[float]
    unusedNodes: List[float]
    averageOccupations: List[float]
    penaltyProportions: List[float]
    coldStartProportions: List[float]
    totalTimes: List[DurationSecond]
    elapsedTimes: List[DurationSecond]
    pullTimes: List[DurationSecond]
    coldStartTimes: List[DurationSecond]
    executionTimes: List[DurationSecond]
    computeTimes: List[DurationSecond]
    communicationsTimes: List[DurationSecond]
    taskQuantiles: List[List[float]]
    applicationQuantiles: List[List[float]]
    localDependenciesProportions: List[float]
    localCommunicationsProportions: List[float]
    nodeCacheProportions: List[float]
    taskCacheProportions: List[float]
    costStructuresQuantiles: List[Dict[str, List[float]]]
    storageDistributions: List[Dict[str, float]]
    penaltyDistributionOverTime: List[List[Tuple[MomentSecond, float]]]
    scaleEvents: List[List[ScaleEvent]]
    reclaimableEnergy: List[EnergykWh]


@final
class ChartsMeans(TypedDict):
    penaltyProportions: List[float]
    coldStartProportions: List[float]
    totalTimes: List[float]


@dataclass
class ChartsData:
    results: ChartsResults
    means: ChartsMeans


class DataclassJSONEncoder(json.JSONEncoder):
    def default(self, o):
        if dataclasses.is_dataclass(o):
            return o.to_dict()
        return super().default(o)


class Error(Exception):
    pass


class CacheEvictionError(Error):
    def __init__(self, message: str):
        self.message = message


priority_policies: Dict[str, Set[str]] = {
    "tasks": {"fifo", "least_penalty", "naive_least_penalty"},
}

scheduling_strategies: Dict[str, str] = {
    "hro_hro": "HRO-HRO",
    "hro_hrc": "HRO-HRC",
    "hro_kn": "HRO-KN",
    "hro_rp": "HRO-RP",
    "hro_bpff": "HRO-BPFF",
    "hrc_hrc": "HRC-HRC",
    "hrc_hro": "HRC-HRO",
    "hrc_kn": "HRC-KN",
    "hrc_rp": "HRC-RP",
    "hrc_bpff": "HRC-BPFF",
    "kn_kn": "KN-KN",
    "kn_hro": "KN-HRO",
    "kn_hrc": "KN-HRC",
    "kn_rp": "KN-RP",
    "kn_bpff": "KN-BPFF",
}

cache_policies: Set[str] = {
    "fifo",
}
