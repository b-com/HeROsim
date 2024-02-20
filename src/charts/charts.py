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

import itertools
import os
import statistics

from bisect import bisect
from typing import Dict, List

import matplotlib.pyplot as plt
import matplotlib.gridspec as gridspec

import numpy as np

from matplotlib.markers import MarkerStyle
from matplotlib.ticker import ScalarFormatter

from src.placement.model import (
    ChartsData,
    ChartsMeans,
    ChartsResults,
    Infrastructure,
    MomentSecond,
    PlatformType,
    SimulationPolicy,
    SimulationStats,
    TaskType,
    TimeSeries,
)


def get_charts_data(
    infrastructure: Infrastructure, input: List[SimulationStats]
) -> ChartsData:
    results: ChartsResults = {
        "energyTotals": [],
        "unusedPlatforms": [],
        "unusedNodes": [],
        "averageOccupations": [],
        "penaltyProportions": [],
        "coldStartProportions": [],
        "totalTimes": [],
        "elapsedTimes": [],
        "pullTimes": [],
        "coldStartTimes": [],
        "executionTimes": [],
        "computeTimes": [],
        "communicationsTimes": [],
        "taskQuantiles": [],
        "applicationQuantiles": [],
        "localDependenciesProportions": [],
        "localCommunicationsProportions": [],
        "nodeCacheProportions": [],
        "taskCacheProportions": [],
        "costStructuresQuantiles": [],
        "storageDistributions": [],
        "penaltyDistributionOverTime": [],
        "scaleEvents": [],
        "reclaimableEnergy": [],
    }

    means: ChartsMeans = {
        "penaltyProportions": [],
        "coldStartProportions": [],
        "totalTimes": [],
    }

    for stats in input:
        cur_energy_total = stats["energy"]
        cur_unused_platforms = stats["unusedPlatforms"]
        cur_unused_nodes = stats["unusedNodes"]
        cur_occupation = stats["averageOccupation"]
        cur_penalty_proportion = stats["penaltyProportion"]
        cur_cold_start_proportion = stats["coldStartProportion"]
        cur_total_time = stats["endTime"] / 3600
        cur_elapsed_time = stats["averageElapsedTime"]
        cur_pull_time = stats["averagePullTime"]
        cur_cold_start_time = stats["averageColdStartTime"]
        cur_execution_time = stats["averageExecutionTime"]
        cur_compute_time = stats["averageComputeTime"]
        cur_communications_time = stats["averageCommunicationsTime"]
        cur_task_quantiles = stats["taskResponseTimeDistribution"]
        cur_app_quantiles = stats["applicationResponseTimeDistribution"]
        cur_local_deps = stats["localDependenciesProportion"]
        cur_local_comms = stats["localCommunicationsProportion"]
        cur_node_cache = stats["nodeCacheHitsProportion"]
        cur_task_cache = stats["taskCacheHitsProportion"]
        cur_penalty_over_time = stats["penaltyDistributionOverTime"]
        cur_scale_events = stats["scaleEvents"]
        cur_reclaimable_energy = stats["reclaimableEnergy"]

        cur_cost_structure = {
            "Pull Time": statistics.quantiles(
                [
                    application_result["pullTime"]
                    for application_result in stats["applicationResults"]
                ],
                n=10,
            ),
            "Cold Start": statistics.quantiles(
                [
                    application_result["coldStartTime"]
                    for application_result in stats["applicationResults"]
                ],
                n=10,
            ),
            "Execution Time": statistics.quantiles(
                [
                    application_result["executionTime"]
                    for application_result in stats["applicationResults"]
                ],
                n=10,
            ),
            "Communications": statistics.quantiles(
                [
                    application_result["communicationsTime"]
                    for application_result in stats["applicationResults"]
                ],
                n=10,
            ),
        }

        cur_storage_values: Dict[str, float] = {
            key: 0.0 for key in ["totalUsage", "cacheUsage", "dataUsage"]
        }

        count = 0
        for node_result in stats["nodeResults"]:
            for storage_result in node_result["storageResults"]:
                count += 1

                # FIXME: Also get max value and timestamp?
                for key in cur_storage_values:
                    if storage_result[key]:
                        last_value = storage_result[key][-1][1]
                        cur_storage_values[key] += last_value

        # pprint.pprint(cur_storage_values)

        cur_storage_means = {
            key: value / count for key, value in cur_storage_values.items()
        }

        # pprint.pprint(cur_storage_means)

        # Sort data by ascending energy consumption
        index = bisect(results["energyTotals"], cur_energy_total)

        results["energyTotals"].insert(index, cur_energy_total)
        results["unusedPlatforms"].insert(index, cur_unused_platforms)
        results["unusedNodes"].insert(index, cur_unused_nodes)
        results["averageOccupations"].insert(index, cur_occupation)
        results["penaltyProportions"].insert(index, cur_penalty_proportion)
        results["coldStartProportions"].insert(index, cur_cold_start_proportion)
        results["totalTimes"].insert(index, cur_total_time)
        results["elapsedTimes"].insert(index, cur_elapsed_time)
        results["pullTimes"].insert(index, cur_pull_time)
        results["coldStartTimes"].insert(index, cur_cold_start_time)
        results["executionTimes"].insert(index, cur_execution_time)
        results["computeTimes"].insert(index, cur_compute_time)
        results["communicationsTimes"].insert(index, cur_communications_time)
        results["taskQuantiles"].insert(index, cur_task_quantiles)
        results["applicationQuantiles"].insert(index, cur_app_quantiles)
        results["localDependenciesProportions"].insert(index, cur_local_deps)
        results["localCommunicationsProportions"].insert(index, cur_local_comms)
        results["nodeCacheProportions"].insert(index, cur_node_cache)
        results["taskCacheProportions"].insert(index, cur_task_cache)
        results["costStructuresQuantiles"].insert(index, cur_cost_structure)
        results["storageDistributions"].insert(index, cur_storage_means)
        results["penaltyDistributionOverTime"].insert(index, cur_penalty_over_time)
        results["scaleEvents"].insert(index, cur_scale_events)
        results["reclaimableEnergy"].insert(index, cur_reclaimable_energy)

    # Compute rolling means
    # Inspired by true events: https://stackoverflow.com/a/37603972/9568489

    means["penaltyProportions"] = list(
        itertools.starmap(
            lambda a, b: b / a,
            enumerate(itertools.accumulate(results["penaltyProportions"]), 1),
        )
    )

    means["coldStartProportions"] = list(
        itertools.starmap(
            lambda a, b: b / a,
            enumerate(itertools.accumulate(results["coldStartProportions"]), 1),
        )
    )

    means["totalTimes"] = list(
        itertools.starmap(
            lambda a, b: b / a,
            enumerate(itertools.accumulate(results["totalTimes"]), 1),
        )
    )

    return ChartsData(results, means)


def plot_boxes_apart(
    chart_dir: str,
    infrastructure: Infrastructure,
    data: Dict[SimulationPolicy, ChartsData],
) -> List[str]:
    figure1, axis1 = plt.subplots()
    figure2, axis2 = plt.subplots()
    figure3, axis3 = plt.subplots()
    figure4, axis4 = plt.subplots()
    figure5, axis5 = plt.subplots()
    figure6, axis6 = plt.subplots()
    figure7, axis7 = plt.subplots()
    figure8, axis8 = plt.subplots()
    figure9, axis9 = plt.subplots()
    figure1.set_size_inches(2, 2)
    figure2.set_size_inches(2, 2)
    figure3.set_size_inches(2, 2)
    figure4.set_size_inches(2, 2)
    figure5.set_size_inches(2, 2)
    figure6.set_size_inches(2, 2)
    figure7.set_size_inches(2, 2)
    figure8.set_size_inches(2, 2)
    figure9.set_size_inches(2, 2)

    # FIXME: Quick and dirty way to configure CCGrid'24 charts output
    if len(data) == 4:
        # Figure 4 (d-f)
        colors = ["#dae8fc", "#f5f5f5", "#ffe6cc", "#fff2cc"]
        hatches = ["///", "|||", "---", "\\\\\\"]
    else:
        # Figure 4 (a-c)
        colors = ["#dae8fc", "#fff2cc", "#d5e8d4", "#f8cecc", "#e1d5e7"]
        hatches = ["///", "\\\\\\", "xxx", "ooo", "..."]

    axis1.bar(
        [str(policy) for policy in data],
        [data[policy].results["communicationsTimes"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    axis2.bar(
        [str(policy) for policy in data],
        [data[policy].results["unusedNodes"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    axis3.bar(
        [str(policy) for policy in data],
        [data[policy].results["penaltyProportions"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    axis4.bar(
        [str(policy) for policy in data],
        [data[policy].results["coldStartProportions"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    # Weird Y-axis scale... Go figure.
    non_sc_formatter = ScalarFormatter(useOffset=False)
    non_sc_formatter.set_scientific(False)
    axis5.get_yaxis().set_major_formatter(non_sc_formatter)

    axis5.bar(
        [str(policy) for policy in data],
        [data[policy].results["totalTimes"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    axis6.bar(
        [str(policy) for policy in data],
        [data[policy].results["energyTotals"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    axis7.bar(
        [str(policy) for policy in data],
        [
            data[policy].results["localCommunicationsProportions"][0]
            for policy in data.keys()
        ],
        color=colors,
        hatch=hatches,
    )

    axis8.bar(
        [str(policy) for policy in data],
        [data[policy].results["reclaimableEnergy"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    axis9.bar(
        [str(policy) for policy in data],
        [data[policy].results["nodeCacheProportions"][0] for policy in data.keys()],
        color=colors,
        hatch=hatches,
    )

    xticklabels = [str(policy) for policy in data.keys()]

    axis1.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis2.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis3.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis4.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis5.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis6.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis7.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis8.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )
    axis9.set_xticks(
        [str(policy) for policy in data],
        labels=xticklabels,
        fontsize=7,
        rotation=45,
        ha="right",
    )

    axis1.set_ylabel("Communications (seconds/task)", fontweight="bold", fontsize=7)
    axis2.set_ylabel("Unused Nodes (% nodes)", fontweight="bold", fontsize=7)
    axis3.set_ylabel("Penalty (% tasks)", fontweight="bold", fontsize=7)
    axis4.set_ylabel("Cold Start (% tasks)", fontweight="bold", fontsize=7)
    axis5.set_ylabel("Execution Time (hours)", fontweight="bold", fontsize=7)
    axis6.set_ylabel("Energy (kWh)", fontweight="bold", fontsize=7)
    axis7.set_ylabel("Local Communications (% tasks)", fontweight="bold", fontsize=7)
    axis8.set_ylabel("Reclaimable Energy (kWh)", fontweight="bold", fontsize=7)
    axis9.set_ylabel("Cache Hits (% replicas)", fontweight="bold", fontsize=7)

    axis1.tick_params(axis="y", labelsize=6)
    axis2.tick_params(axis="y", labelsize=6)
    axis3.tick_params(axis="y", labelsize=6)
    axis4.tick_params(axis="y", labelsize=6)
    axis5.tick_params(axis="y", labelsize=6)
    axis6.tick_params(axis="y", labelsize=6)
    axis7.tick_params(axis="y", labelsize=6)
    axis8.tick_params(axis="y", labelsize=6)
    axis9.tick_params(axis="y", labelsize=6)

    figure1.tight_layout()
    figure2.tight_layout()
    figure3.tight_layout()
    figure4.tight_layout()
    figure5.tight_layout()
    figure6.tight_layout()
    figure7.tight_layout()
    figure8.tight_layout()
    figure9.tight_layout()

    outfiles = [
        os.path.join(f"{chart_dir}", "1-communications-time.png"),
        os.path.join(f"{chart_dir}", "2-unused-nodes.png"),
        os.path.join(f"{chart_dir}", "3-penalty-proportions.png"),
        os.path.join(f"{chart_dir}", "4-cold-start-proportions.png"),
        os.path.join(f"{chart_dir}", "5-execution-time.png"),
        os.path.join(f"{chart_dir}", "6-energy-consumption.png"),
        os.path.join(f"{chart_dir}", "7-local-communications.png"),
        os.path.join(f"{chart_dir}", "8-reclaimable-energy.png"),
        os.path.join(f"{chart_dir}", "9-cache-hits.png"),
    ]

    figure1.savefig(f"{outfiles[0]}", format="png", dpi=300)
    figure2.savefig(f"{outfiles[1]}", format="png", dpi=300)
    figure3.savefig(f"{outfiles[2]}", format="png", dpi=300)
    figure4.savefig(f"{outfiles[3]}", format="png", dpi=300)
    figure5.savefig(f"{outfiles[4]}", format="png", dpi=300)
    figure6.savefig(f"{outfiles[5]}", format="png", dpi=300)
    figure7.savefig(f"{outfiles[6]}", format="png", dpi=300)
    figure8.savefig(f"{outfiles[7]}", format="png", dpi=300)
    figure9.savefig(f"{outfiles[8]}", format="png", dpi=300)

    return outfiles


def plot_cost_structure(
    chart_dir: str,
    infrastructure: Infrastructure,
    data: Dict[SimulationPolicy, ChartsData],
) -> str:
    cost_quantiles, cost_quantiles_axis = plt.subplots()

    width = 0.25
    multiplier = 0

    x_labels = ("Q1", "Q2", "Q3", "Q4", "Q5", "Q6", "Q7", "Q8", "Q9")
    x = np.arange(len(x_labels))

    for policy in data.keys():
        bottom = np.zeros(len(x_labels))

        for cost_structure in data[policy].results["costStructuresQuantiles"]:
            for metric, quantiles in cost_structure.items():
                offset = width * multiplier

                cost_quantiles_axis.bar(
                    x + offset,
                    quantiles,
                    width,
                    label=f"{policy}-{metric}",
                    bottom=bottom,
                )

                bottom += quantiles

            multiplier += 1

    cost_quantiles_axis.set_xticks(x + width / len(data), x_labels)

    cost_quantiles_axis.set_ylabel("Application Response Time (seconds)")
    cost_quantiles_axis.set_title("Application Response Time Distribution (Quantiles)")
    cost_quantiles_axis.legend()

    outfile = os.path.join(f"{chart_dir}", "cost-structure.png")

    cost_quantiles.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_quantiles(
    chart_dir: str,
    infrastructure: Infrastructure,
    data: Dict[SimulationPolicy, ChartsData],
) -> List[str]:
    task_quantiles, task_quantiles_axis = plt.subplots()
    app_quantiles, app_quantiles_axis = plt.subplots()

    # Task and Application Response Time distribution across policies
    task_quantiles_lines = []
    app_quantiles_lines = []

    for policy in data.keys():
        policy_task_quantiles = data[policy].results["taskQuantiles"]
        policy_app_quantiles = data[policy].results["applicationQuantiles"]

        averaged_policy_task_quantiles = [
            float(sum(col)) / len(col) for col in zip(*policy_task_quantiles)
        ]
        task_quantiles_lines.append(
            task_quantiles_axis.plot(averaged_policy_task_quantiles, label=policy)
        )

        averaged_policy_app_quantiles = [
            float(sum(col)) / len(col) for col in zip(*policy_app_quantiles)
        ]
        app_quantiles_lines.append(
            app_quantiles_axis.plot(averaged_policy_app_quantiles, label=policy)
        )

    task_quantiles_axis.legend()
    task_quantiles_axis.set_ylabel("Response Time (seconds)", fontweight="bold")
    task_quantiles_axis.set_xlabel("Quantiles", fontweight="bold")

    app_quantiles_axis.legend()
    app_quantiles_axis.set_ylabel("Response Time (seconds)", fontweight="bold")
    app_quantiles_axis.set_xlabel("Quantiles", fontweight="bold")

    task_outfile = os.path.join(f"{chart_dir}", "response-time-task-quantiles.png")
    app_outfile = os.path.join(
        f"{chart_dir}", "response-time-application-quantiles.png"
    )

    task_quantiles.savefig(f"{task_outfile}", format="png", dpi=300)
    app_quantiles.savefig(f"{app_outfile}", format="png", dpi=300)

    return [task_outfile, app_outfile]


def plot_boxes(
    chart_dir: str,
    infrastructure: Infrastructure,
    data: Dict[SimulationPolicy, ChartsData],
    platform_types: Dict[str, PlatformType],
) -> str:
    figure = plt.figure(constrained_layout=True, figsize=(12, 14))
    spec = gridspec.GridSpec(ncols=3, nrows=3, figure=figure)
    figure_axis1 = figure.add_subplot(spec[0, 0])
    figure_axis2 = figure.add_subplot(spec[0, 1])
    figure_axis3 = figure.add_subplot(spec[0, 2])
    figure_axis4 = figure.add_subplot(spec[1, 0])
    figure_axis5 = figure.add_subplot(spec[1, 1])
    figure_axis6 = figure.add_subplot(spec[1, 2])
    figure_axis7 = figure.add_subplot(spec[2, 0])
    figure_axis8 = figure.add_subplot(spec[2, 1])
    figure_axis9 = figure.add_subplot(spec[2, 2])

    figure_axis1.set_title("Communications Time (seconds/task)")
    figure_axis2.set_title("Unused Nodes (% node count)")
    figure_axis3.set_title("Penalty Proportions (% applications)")
    figure_axis4.set_title("Cold Start Proportions (% tasks)")
    figure_axis5.set_title("Execution Times (hours)")
    figure_axis6.set_title("Energy Consumption (kWh)")
    figure_axis7.set_title("Local Communications (% tasks)")
    # figure_axis8.set_title("Local Dependencies (% applications)")
    figure_axis8.set_title("Reclaimable Energy (kWh)")
    figure_axis9.set_title("Cache Hits (% replicas)")

    colors = ["tab:blue", "tab:orange", "tab:green", "tab:red", "tab:purple"]

    figure_axis1.bar(
        [str(policy) for policy in data],
        [data[policy].results["communicationsTimes"][0] for policy in data.keys()],
        color=colors,
    )

    figure_axis2.bar(
        [str(policy) for policy in data],
        [data[policy].results["unusedNodes"][0] for policy in data.keys()],
        color=colors,
    )

    figure_axis3.bar(
        [str(policy) for policy in data],
        [data[policy].results["penaltyProportions"][0] for policy in data.keys()],
        color=colors,
    )

    figure_axis4.bar(
        [str(policy) for policy in data],
        [data[policy].results["coldStartProportions"][0] for policy in data.keys()],
        color=colors,
    )

    figure_axis5.bar(
        [str(policy) for policy in data],
        [data[policy].results["totalTimes"][0] for policy in data.keys()],
        color=colors,
    )

    figure_axis6.bar(
        [str(policy) for policy in data],
        [data[policy].results["energyTotals"][0] for policy in data.keys()],
        color=colors,
    )

    figure_axis7.bar(
        [str(policy) for policy in data],
        [
            data[policy].results["localCommunicationsProportions"][0]
            for policy in data.keys()
        ],
        color=colors,
    )

    figure_axis8.bar(
        [str(policy) for policy in data],
        [data[policy].results["reclaimableEnergy"][0] for policy in data.keys()],
        # [data[policy].results["localDependenciesProportions"][0] for policy in data.keys()],
        color=colors,
    )

    figure_axis9.bar(
        [str(policy) for policy in data],
        [data[policy].results["nodeCacheProportions"][0] for policy in data.keys()],
        color=colors,
    )

    # Platforms counter for chart title
    platform_count = {}
    for node_description in infrastructure["nodes"]:
        for platform_name in node_description["platforms"]:
            platform = platform_types[platform_name]

            if platform["hardware"] not in platform_count:
                platform_count[platform["hardware"]] = 0

            platform_count[platform["hardware"]] += 1

    figure_title = "{node_count} nodes".format(
        node_count=len(infrastructure["nodes"]),
    )

    figure.suptitle(figure_title)

    outfile = os.path.join(f"{chart_dir}", "boxes.png")

    figure.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_penalty_over_time(
    chart_dir: str,
    infrastructure: Infrastructure,
    data: Dict[SimulationPolicy, ChartsData],
) -> str:
    penalties, penalties_axis = plt.subplots()

    for policy in data.keys():
        for policy_distribution in data[policy].results["penaltyDistributionOverTime"]:
            timestamps: List[MomentSecond]
            distribution: List[float]
            timestamps, distribution = zip(*policy_distribution)

            penalties_axis.plot(timestamps, distribution, label=str(policy))

    penalties_axis.set_ylabel("% applications over time")
    penalties_axis.set_xlabel("Time (seconds)")
    penalties_axis.set_title("Application Penalties Distribution")
    penalties_axis.legend()

    outfile = os.path.join(f"{chart_dir}", "penalties.png")

    penalties.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_scale_events(
    chart_dir: str,
    infrastructure: Infrastructure,
    data: Dict[SimulationPolicy, ChartsData],
) -> str:
    figure = plt.figure(constrained_layout=True, figsize=(15, 5))
    spec = gridspec.GridSpec(ncols=3, nrows=1, figure=figure)

    colors = [
        "tab:blue",
        "tab:orange",
        "tab:green",
        "tab:red",
        "tab:purple",
        "tab:pink",
        "tab:brown",
        "tab:gray",
        "tab:olive",
        "tab:cyan",
    ]
    markers = ["s", "o", "D", "v", "p", "|", "d", "x", "P", "^"]

    count = 0
    for policy in data.keys():
        scale_events_axis = figure.add_subplot(spec[0, count])
        count += 1

        for policy_events in data[policy].results["scaleEvents"]:
            functions = set([event["name"] for event in policy_events])

            for iter, function_name in enumerate(functions):
                timestamps = [
                    event["timestamp"]
                    for event in policy_events
                    if event["name"] == function_name
                ]
                actions = [
                    event["action"]
                    for event in policy_events
                    if event["name"] == function_name
                ]
                counts = [
                    event["count"]
                    for event in policy_events
                    if event["name"] == function_name
                ]

                scale_events_axis.plot(
                    timestamps,
                    counts,
                    label=f"{function_name}",
                    color=colors[iter],
                    marker=markers[iter],
                    markerfacecolor="None",
                    markeredgecolor=colors[iter],
                    linestyle="None",
                )

                scale_events_axis.plot(
                    timestamps, counts, color=colors[iter], alpha=0.5
                )

                for iter, event in enumerate(
                    [
                        policy_event
                        for policy_event in policy_events
                        if policy_event["name"] == function_name
                    ]
                ):
                    scale_events_axis.annotate(
                        f"{event['average_queue_length']}",
                        (timestamps[iter], counts[iter]),
                    )

        scale_events_axis.set_ylabel("Replica count")
        scale_events_axis.set_xlabel("Time (seconds)")
        scale_events_axis.set_title(f"{policy}")
        scale_events_axis.legend()

    outfile = os.path.join(f"{chart_dir}", "scale-events.png")

    figure.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_storage_distribution(
    chart_dir: str,
    infrastructure: Infrastructure,
    data: Dict[SimulationPolicy, ChartsData],
) -> str:
    storage, storage_axis = plt.subplots()

    width = 0.25

    x_labels = ()
    x = np.arange(len(x_labels))

    for policy in data.keys():
        bottom = np.zeros(len(x_labels))

        for storage_distribution in data[policy].results["storageDistributions"]:
            for usage, value in storage_distribution.items():
                pass

    storage_axis.set_xticks(x + width / len(data), x_labels)

    storage_axis.set_ylabel("% Storage Capacity")
    storage_axis.set_title("Storage Usage Distribution")
    storage_axis.legend()

    outfile = os.path.join(f"{chart_dir}", "storage.png")

    storage.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_time_series(chart_dir: str, time_series: TimeSeries) -> str:
    workload, workload_axis = plt.subplots()

    workload_axis.plot([event["timestamp"] for event in time_series.events])

    # workload_axis.legend()
    workload_axis.set_ylabel("Request Arrival Time (s)", fontweight="bold")
    workload_axis.set_xlabel("Request Number", fontweight="bold")

    outfile = os.path.join(f"{chart_dir}", "time-series.png")

    workload.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_tasks_time(chart_dir: str, task_types: Dict[str, TaskType]) -> str:
    tasks, tasks_axis = plt.subplots()

    data = []
    labels = []

    for task_type in task_types.values():
        for platform, execution_time in task_type["executionTime"].items():
            data.append(execution_time)
            labels.append(f"{task_type['name']} ({platform})")

    plt.xticks(range(len(data)), labels)
    plt.bar(range(len(data)), data)

    outfile = os.path.join(f"{chart_dir}", "tasks-time.png")

    tasks.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_node_storage(
    chart_dir: str, infrastructure: Infrastructure, input: List[SimulationStats]
) -> str:
    storage, storage_axis = plt.subplots()
    storage_lines = []

    for simulation_stats in input:
        for node_result in simulation_stats["nodeResults"]:
            for storage_result in node_result["storageResults"]:
                try:
                    x_total, y_total = zip(*storage_result["totalUsage"])
                    x_cache, y_cache = zip(*storage_result["cacheUsage"])
                    x_data, y_data = zip(*storage_result["dataUsage"])

                    storage_lines.extend(
                        [
                            storage_axis.plot(x_total, y_total, "-", label="Total"),
                            storage_axis.plot(x_cache, y_cache, "--", label="Cache"),
                            storage_axis.plot(x_data, y_data, ":", label="Data"),
                        ]
                    )
                except ValueError:
                    pass

    outfile = os.path.join(f"{chart_dir}", "storage.png")

    storage.savefig(f"{outfile}", format="png", dpi=300)

    return outfile


def plot_response_times(
    chart_dir: str, infrastructure: Infrastructure, input: List[SimulationStats]
) -> List[str]:
    response_times_applications, response_times_applications_axis = plt.subplots()
    response_times_tasks, response_times_tasks_axis = plt.subplots()

    response_times_applications_data = []
    response_times_tasks_data = []

    for simulation_stats in input:
        for application_result in simulation_stats["applicationResults"]:
            response_times_applications_data.append(application_result["elapsedTime"])

        for task_result in simulation_stats["taskResults"]:
            response_times_tasks_data.append(task_result["elapsedTime"])

    response_times_applications_axis.scatter(
        range(len(response_times_applications_data)),
        response_times_applications_data,
        marker=MarkerStyle("."),
    )

    response_times_tasks_axis.scatter(
        range(len(response_times_tasks_data)),
        response_times_tasks_data,
        marker=MarkerStyle("."),
    )

    app_outfile = os.path.join(f"{chart_dir}", "response-times-applications.png")
    task_outfile = os.path.join(f"{chart_dir}", "response-times-tasks.png")

    response_times_applications.savefig(f"{app_outfile}", format="png", dpi=300)

    response_times_tasks.savefig(f"{task_outfile}", format="png", dpi=300)

    return [
        app_outfile,
        task_outfile,
    ]


def plot_task_times(
    chart_dir: str, infrastructure: Infrastructure, input: List[SimulationStats]
) -> List[str]:
    task_times, task_times_axis = plt.subplots()

    task_pull_data = []
    task_cold_start_data = []
    task_execution_data = []
    task_communications_data = []

    for simulation_stats in input:
        for task_result in simulation_stats["taskResults"]:
            task_pull_data.append(task_result["pullTime"])
            task_cold_start_data.append(task_result["coldStartTime"])
            task_execution_data.append(task_result["executionTime"])
            task_communications_data.append(task_result["communicationsTime"])

    ind = np.arange(len(task_cold_start_data))

    bar1 = task_times_axis.bar(ind, task_pull_data)
    bar2 = task_times_axis.bar(ind, task_cold_start_data)
    bar3 = task_times_axis.bar(ind, task_execution_data)
    bar4 = task_times_axis.bar(ind, task_communications_data)

    task_times.legend(
        (bar1[0], bar2[0], bar3[0], bar4[0]),
        ("Pull Time", "Cold Start Time", "Execution Time", "Communications Time"),
    )

    outfile = os.path.join(f"{chart_dir}", "task-times.png")

    task_times.savefig(f"{outfile}", format="png", dpi=300)

    return [outfile]
