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

from datetime import datetime
from typing import Dict, List

from src.placement.model import (
    ChartsData,
    Infrastructure,
    SimulationData,
    SimulationPolicy,
    SimulationStats,
    TimeSeries,
    dir_path,
    scheduling_strategies,
)

from src.charts.charts import (
    plot_boxes,
    plot_boxes_apart,
    plot_penalty_over_time,
    plot_quantiles,
    get_charts_data,
    plot_cost_structure,
)

from src.parser.parser import parse_simulation_data


def main() -> int:
    # Parser
    parser = argparse.ArgumentParser(
        description=(
            "☁️ Tasks Scheduling on Heterogeneous Resources "
            "for Serverless Cloud Computing"
        )
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
        help="Workload trace filename",
        type=argparse.FileType("r"),
        required=True,
    )
    parser.add_argument(
        "-p",
        "--paper-charts",
        help="Generate invidual charts for integration in papers",
        action="store_true",
    )
    parser.add_argument(
        "-l",
        "--policies-list",
        help="List the policies for which you wish to generate individual charts",
        nargs="+",
        choices=scheduling_strategies.values(),
        type=str,
    )
    args = parser.parse_args()

    # Check if output directories need to be created
    chart_time = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    chart_dir = os.path.join("chart", f"{chart_time}")
    individual_chart_dir = os.path.join(chart_dir, "figures")
    if not os.path.exists(chart_dir):
        os.makedirs(chart_dir)
    if not os.path.exists(individual_chart_dir):
        os.makedirs(individual_chart_dir)

    # Read infrastructure
    with args.infrastructure as infile:
        infrastructure: Infrastructure = json.load(infile)

    # Read time series
    with args.workload_trace as infile:
        time_series = TimeSeries.from_dict(json.load(infile))

    # Parse simulation data
    simulation_data: SimulationData = parse_simulation_data(args.data_directory)

    # Plot time series
    # time_series_file = plot_time_series(chart_dir, time_series)

    # Plot tasks
    # tasks_time_file = plot_tasks_time(chart_dir, simulation_data.task_types)

    # Read simulation stats from the result files
    # Sort them by simulation policy
    stats: Dict[SimulationPolicy, List[SimulationStats]] = {}
    for result in glob.glob("result/*.json"):
        with open(result) as infile:
            cur_stats = json.load(infile)
            cur_stats_policy = SimulationPolicy.from_dict(cur_stats["policy"])

            if cur_stats_policy not in stats:
                stats[cur_stats_policy] = []

            stats[cur_stats_policy].append(cur_stats)

    # Arrange data for charts generation
    data: Dict[SimulationPolicy, ChartsData] = {}
    # Policies are orderable so we can keep a consistent order across charts
    for policy in sorted(stats):
        data[policy] = get_charts_data(infrastructure, stats[policy])
        """
        # FIXME: Debug charts generation should be improved
        plot_node_storage(infrastructure, stats[policy])
        # Plot response times over time
        plot_response_times(infrastructure, stats[policy])
        # Plot response time
        plot_task_times(infrastructure, stats[policy])
        """

    # Plot the evaluation metrics
    box_chart_file: str = plot_boxes(
        chart_dir, infrastructure, data, simulation_data.platform_types
    )

    # Plot cost structures quantiles
    cost_structures_file: str = plot_cost_structure(chart_dir, infrastructure, data)

    # Plot response time distribution
    response_times_files: List[str] = plot_quantiles(chart_dir, infrastructure, data)

    # Plot application penalties distribution over time
    penalties_over_time_file: str = plot_penalty_over_time(
        chart_dir, infrastructure, data
    )

    # Plot storage usage distribution
    # storage_distribution_file: str = plot_storage_distribution(infrastructure, data)

    # Plot autoscaler events and replica counts
    # scale_events_file: str = plot_scale_events(chart_dir, infrastructure, data)

    if args.paper_charts:
        # Individual files for paper charts
        eval_data: Dict[SimulationPolicy, ChartsData] = {}
        # Policies are orderable so we can keep a consistent order across charts
        for policy in sorted(stats):
            if args.policies_list is not None and str(policy) not in args.policies_list:
                continue
            eval_data[policy] = data[policy]

        eval_chart_files: List[str] = plot_boxes_apart(
            individual_chart_dir, infrastructure, eval_data
        )

        print(eval_chart_files)

    print(box_chart_file)
    print(cost_structures_file)

    for response_time_file in response_times_files:
        print(response_time_file)

    return os.EX_OK


if __name__ == "__main__":
    sys.exit(main())
