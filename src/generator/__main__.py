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
import json
import os
import sys

from typing import Dict

from src.parser.parser import parse_infrastructure_data, parse_simulation_data

from src.placement.model import (
    ApplicationType,
    DataclassJSONEncoder,
    SimulationData,
    TaskType,
    TimeSeries,
    dir_path,
)

from src.generator.stats import get_workload_stats
from src.generator.traces import generate_time_series
from src.generator.workloads import (
    fix_tasks_state_size,
    generate_application_types,
    generate_task_types,
)


def main() -> int:
    # Parser
    parser = argparse.ArgumentParser(
        description=(
            "☁️ Tasks Scheduling on Heterogeneous Resources for Serverless Cloud"
            " Computing"
        )
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
        "--generate-workloads",
        help="Generate task types and application DAGs",
        action="store_true",
    )
    parser.add_argument(
        "-t", "--generate-traces", help="Generate execution traces", action="store_true"
    )
    parser.add_argument(
        "-r",
        "--rps",
        help="Average number of requests per second",
        type=int,
        required=False,
    )
    parser.add_argument(
        "-s",
        "--seconds",
        help="Duration of the scenario in seconds",
        type=int,
        required=False,
    )
    args = parser.parse_args()

    if not args.generate_traces and not args.generate_workloads:
        parser.error(
            "You must specify is you wish to generate workloads (-w)"
            " and/or traces (-t)."
        )

    # Parse infrastructure data
    (platform_types, storage_types) = parse_infrastructure_data(args.data_directory)

    if args.generate_workloads:
        generated_tasks_path = os.path.join(args.data_directory, "task-types.json")
        generated_applications_path = os.path.join(
            args.data_directory, "application-types.json"
        )

        if os.path.exists(generated_tasks_path) or os.path.exists(
            generated_applications_path
        ):
            raise IOError(
                "Task types and/or application types already exist"
                f" in {args.data_directory}."
            )

        # TODO: JSON configuration
        # Create task types
        task_types: Dict[str, TaskType] = generate_task_types(
            30,
            platform_types,
            storage_types,
        )

        # Create application types
        # max_sample_size = math.ceil(len(task_types) / 50)
        max_sample_size = 3
        application_types: Dict[str, ApplicationType] = generate_application_types(
            15, task_types, max_sample_size
        )

        # FIXME
        fix_tasks_state_size(task_types, application_types)

        with open(generated_tasks_path, "w") as outfile:
            json.dump(task_types, outfile, indent=2)

        with open(generated_applications_path, "w") as outfile:
            json.dump(application_types, outfile, indent=2)

    if args.generate_traces:
        if args.rps is None or args.seconds is None:
            parser.error("--generate-traces requires --rps and --seconds")

        generated_traces_path = os.path.join(args.data_directory, "traces")

        if not os.path.exists(generated_traces_path):
            os.makedirs(generated_traces_path)

        generated_trace_path = os.path.join(
            generated_traces_path, f"workload-{args.rps}-{args.seconds}.json"
        )

        if os.path.exists(generated_trace_path):
            raise IOError(
                f"workload-{args.rps}-{args.seconds}.json already exists"
                f" in {generated_traces_path}."
            )

        # Parse simulation data
        simulation_data: SimulationData = parse_simulation_data(args.data_directory)

        # Create time series
        time_series: TimeSeries = generate_time_series(
            simulation_data, args.rps, args.seconds
        )

        with open(f"{generated_trace_path}", "w") as outfile:
            json.dump(time_series, outfile, indent=2, cls=DataclassJSONEncoder)

        # Generate stats related to workloads and time series
        get_workload_stats(
            simulation_data.application_types, simulation_data.task_types, time_series
        )

    return os.EX_OK


if __name__ == "__main__":
    sys.exit(main())
