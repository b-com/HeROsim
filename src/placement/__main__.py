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

import argparse
import glob
import json
import os
import sys

from src.parser.parser import parse_simulation_data

from src.placement.model import (
    Infrastructure,
    PriorityPolicy,
    SimulationPolicy,
    SimulationData,
    TimeSeries,
    dir_path,
    restricted_float,
    positive_int,
)
from src.placement.model import priority_policies, scheduling_strategies, cache_policies
from src.placement.simulation import start_simulation


def main() -> int:
    # Parser
    parser = argparse.ArgumentParser(
        description=(
            "☁️ Tasks Scheduling on Heterogeneous Resources for Serverless Cloud"
            " Computing"
        )
    )
    parser.add_argument(
        "--clear", help="Clear log and result folders", action="store_true"
    )
    parser.add_argument(
        "-i",
        "--infrastructure",
        help="Infrastructure JSON filename",
        type=argparse.FileType("r"),
        required=True,
    )
    parser.add_argument(
        "-d",
        "--data-directory",
        help="Simulation data JSON files directory",
        type=dir_path,
        required=True,
    )
    parser.add_argument(
        "-w",
        "--workload-trace",
        help="Workload trace JSON filename",
        type=argparse.FileType("r"),
        required=True,
    )
    parser.add_argument(
        "-s",
        "--scheduling-strategy",
        help="Select the scheduling strategy for task placement",
        choices=scheduling_strategies,
        type=str,
        required=True,
    )
    parser.add_argument(
        "-t",
        "--task-priority-policy",
        help="Select the priority policy for task selection",
        choices=priority_policies["tasks"],
        type=str,
        required=True,
    )
    parser.add_argument(
        "-c",
        "--cache-policy",
        help="Select the cache eviction policy for node storage",
        choices=cache_policies,
        type=str,
        required=True,
    )
    parser.add_argument(
        "-k",
        "--keep-alive",
        help="Select the replica keep-alive duration",
        type=restricted_float,
        required=True,
    )
    parser.add_argument(
        "-q",
        "--queue-length",
        help="Select the queue length (# tasks) on baseline platform",
        type=positive_int,
        required=True,
    )
    args = parser.parse_args()

    # Check if output directories need to be created
    if not os.path.exists("log"):
        os.makedirs("log")
    if not os.path.exists("result"):
        os.makedirs("result")

    # Clear log and result folders if so flagged
    if args.clear:
        for log in glob.glob("log/*.log"):
            os.remove(log)
        for result in glob.glob("result/*.json"):
            os.remove(result)

    # Read infrastructure and policy
    with args.infrastructure as infile:
        infrastructure: Infrastructure = json.load(infile)

    simulation_policy = SimulationPolicy(
        priority=PriorityPolicy(tasks=args.task_priority_policy),
        scheduling=args.scheduling_strategy,
        cache=args.cache_policy,
        keep_alive=args.keep_alive,
        queue_length=args.queue_length,
        short_name=scheduling_strategies[args.scheduling_strategy],
    )

    # Parse simulation data
    simulation_data: SimulationData = parse_simulation_data(args.data_directory)

    # Read time series
    with args.workload_trace as infile:
        time_series: TimeSeries = TimeSeries.from_dict(json.load(infile))

    # Run simulation
    start_simulation(simulation_data, simulation_policy, infrastructure, time_series)

    return os.EX_OK


if __name__ == "__main__":
    sys.exit(main())
