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

import json
import logging
import os
import sys

from datetime import datetime
from typing import Dict, Tuple, Type

from src.placement.infrastructure import Node, Platform, Storage

from simpy.core import Environment
from simpy.resources.store import FilterStore

from src.placement.model import (
    DataclassJSONEncoder,
    Infrastructure,
    SimulationData,
    SimulationPolicy,
    TimeSeries,
)

from src.placement.evaluation import find_component, find_time

from src.placement.orchestrator import Orchestrator

from src.placement.autoscaler import Autoscaler
from src.placement.scheduler import Scheduler

from src.policy.herofake.orchestrator import HROOrchestrator
from src.policy.herofake.autoscaler import HROAutoscaler
from src.policy.herofake.scheduler import HROScheduler

from src.policy.herocache.orchestrator import HRCOrchestrator
from src.policy.herocache.autoscaler import HRCAutoscaler
from src.policy.herocache.scheduler import HRCScheduler

from src.policy.knative.orchestrator import KnativeOrchestrator
from src.policy.knative.autoscaler import KnativeAutoscaler
from src.policy.knative.scheduler import KnativeScheduler

from src.policy.random.scheduler import RandomScheduler

from src.policy.bpff.scheduler import BPFFScheduler



def create_nodes(
    env: Environment,
    scenario,
    simulation_data: SimulationData,
    simulation_policy: SimulationPolicy,
    infrastructure: Infrastructure,
) -> FilterStore:
    node_id = 0
    platform_id = 0
    storage_id = 0

    nodes_store = FilterStore(env)

    # Building the path to the "platform-types.json" file
    base_dir = os.path.dirname(os.path.dirname(__file__))
    platform_file = os.path.join(os.path.dirname(base_dir), "data", scenario, "platform-types.json")

    if not os.path.exists(platform_file):
        raise FileNotFoundError(f"{platform_file} file is not to be found. PLease check it.")

    with open (platform_file) as f2:
        data = json.load(f2)

    print(data)

    for node in infrastructure["nodes"]:
        platforms_store = FilterStore(env)
        storage_store = FilterStore(env)

        # Initialize node
        current_node = Node(
            env=env,
            node_id=node_id,
            memory=node["memory"],
            platforms=platforms_store,
            storage=storage_store,
            network=infrastructure["network"],
            policy=simulation_policy,
            data=simulation_data,
        )
        nodes_store.put(current_node)

        for name in node["platforms"]:
            parameters = find_component(data, name)
            lifespan = parameters["lifespan"] * 3600 * 24  *  365.2425
            total_time = find_time(data)
            print("Time : ", total_time)
            print ("mass = ", parameters["mass"], flush = True)
            
                
            platforms_store.put(
                Platform(
                    env=env,
                    platform_id=platform_id,
                    platform_type=simulation_data.platform_types[name],
                    mass=parameters["mass"],
                    lifespan=lifespan,
                    total_time=total_time,
                    node=current_node,
                )
            )

            platform_id += 1

        current_node.available_platforms = len(platforms_store.items)

        for name in node["storage"]:
            storage_store.put(
                Storage(
                    env=env,
                    storage_id=storage_id,
                    storage_type=simulation_data.storage_types[name],
                    node=current_node,
                )
            )

            storage_id += 1

        node_id += 1

    return nodes_store


def start_simulation(
    running_scenario,
    simulation_data: SimulationData,
    simulation_policy: SimulationPolicy,
    infrastructure: Infrastructure,
    time_series: TimeSeries,
) -> None:
    # Logger
    simulation_time = datetime.now().strftime("%Y%m%d-%H%M%S-%f")

    file_handler = logging.FileHandler(f"log/{simulation_time}.log")
    file_handler.setLevel(logging.DEBUG)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(logging.ERROR)

    logging.basicConfig(
        level=logging.DEBUG,
        format="%(levelname)s [%(funcName)18s() ] %(message)s",
        handlers=[file_handler, console_handler],
    )

    # Simulation
    env = Environment()
    finished = env.event()

    # Initialize infrastructure
    nodes: FilterStore = create_nodes(
        env=env,
        scenario=running_scenario,
        simulation_data=simulation_data,
        simulation_policy=simulation_policy,
        infrastructure=infrastructure,
    )

    # TODO: Could be discovered at runtime
    policies: Dict[
        str, Tuple[Type[Orchestrator], Type[Autoscaler], Type[Scheduler]]
    ] = {
        "hro_hro": (HROOrchestrator, HROAutoscaler, HROScheduler),
        "hro_hrc": (HROOrchestrator, HROAutoscaler, HRCScheduler),
        "hro_kn": (HROOrchestrator, HROAutoscaler, KnativeScheduler),
        "hro_rp": (HROOrchestrator, HROAutoscaler, RandomScheduler),
        "hro_bpff": (HROOrchestrator, HROAutoscaler, BPFFScheduler),
        "hrc_hrc": (HRCOrchestrator, HRCAutoscaler, HRCScheduler),
        "hrc_hro": (HRCOrchestrator, HRCAutoscaler, HROScheduler),
        "hrc_kn": (HRCOrchestrator, HRCAutoscaler, KnativeScheduler),
        "hrc_rp": (HRCOrchestrator, HRCAutoscaler, RandomScheduler),
        "hrc_bpff": (HRCOrchestrator, HRCAutoscaler, BPFFScheduler),
        "kn_kn": (KnativeOrchestrator, KnativeAutoscaler, KnativeScheduler),
        "kn_hro": (KnativeOrchestrator, KnativeAutoscaler, HROScheduler),
        "kn_hrc": (KnativeOrchestrator, KnativeAutoscaler, HRCScheduler),
        "kn_rp": (KnativeOrchestrator, KnativeAutoscaler, RandomScheduler),
        "kn_bpff": (KnativeOrchestrator, KnativeAutoscaler, BPFFScheduler),
    }

    # Retrieve relevant Autoscaler and Scheduler classes
    # Both will be instantiated by the Orchestrator
    orchestrator_type, autoscaler_type, scheduler_type = policies[
        simulation_policy.scheduling
    ]

    orchestrator = orchestrator_type(
        env=env,
        scenario=running_scenario,
        data=simulation_data,
        policy=simulation_policy,
        autoscaler=autoscaler_type,
        scheduler=scheduler_type,
        time_series=time_series,
        nodes=nodes,
        end_event=finished,
    )

    env.run(until=finished)

    logging.info(f"[ {orchestrator.end_time} ] ✨ Simulation finished")

    # Statistics
    stats = orchestrator.stats()

    with open(os.path.join("result", f"{simulation_time}.json"), "w") as outfile:
        json.dump(stats, outfile, indent=2, cls=DataclassJSONEncoder)

    logging.warning(f"Total time: {env.now / 3600} hours")
    logging.warning(f"Average elapsed time: {stats['averageElapsedTime']}")
    logging.warning(f"Average compute time: {stats['averageComputeTime']}")
    logging.warning(f"Total energy: {stats['energy']}")
    logging.warning(f"Penalty proportion: {stats['penaltyProportion']}")
    logging.warning(f"Cold start proportion: {stats['coldStartProportion']}")
