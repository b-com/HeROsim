☁️ Heterogeneous Resources Orchestration Simulator for Serverless Cloud Computing

**HeROsim** is an open source simulation environment for the evaluation of serverless resources allocation and tasks scheduling policies. Its main goal is to relieve researchers from the implementation of discrete-event simulation boilerplate in the context of the dynamic process of cloud orchestration.

We hope that by using HeROsim, researchers can focus their efforts on the core design of their allocation and scheduling policies. HeROsim provides the necessary environment for the evaluation of such policies against baselines and other state-of-the-art contributions, as well as the production of charts for inclusion in scientific papers.

## Overview

Serverless can be understood as both a programming model, sometimes called Function as a Service (FaaS), and a deployment model for the cloud. In such a model, developers design their applications as a composition of stateless functions which execution is event-driven. Serverless services free tenants from complex resource reservation as they are designed to handle on-demand scaling requirements. In the FaaS model, providers only bill customers according to their actual resources usage. They are fully responsible for deploying intelligent resource management and multiplexing at a finer granularity to optimize Quality of Service (QoS) metrics such as response time, energy consumption, etc.

In a serverless architecture, developers design their applications as a composition of stateless functions. Stateless means that the outcome of the computation depends exclusively on the inputs. These functions take a payload and an invocation context as input, and produce a result that is stored in a persistent network-accessible storage tier. For any function, an **autoscaler** can deploy multiple *replicas* to absorb the load. Scaling a serverless application consists in growing or shrinking the pool of replicas for the functions following the load peaks: the goal of the autoscaler is to determine how to automatically and reactively scale hardware resources in a cloud in adequacy with the applications' load.

Each replica is allocated on an execution platform (*e.g.* one CPU core, one GPU, etc.) and has a request queue of fixed length for incoming requests. The number of replicas for a given function at any moment determines its concurrency level. A **scheduler** places user requests in queue on function replicas. When a replica has no more requests to handle, it is deallocated. When a function is requested while no replica exists, it goes through a cold start. As functions are stateless, requests can be mapped to any available replica: the goal of the scheduler is to determine on which replica to queue user requests for a given function.

## Features

HeROsim replays an allocation and placement scenario under different orchestration policies. A simulator run requires the following inputs:

* a **workload description** -- details on the **characteristics of the functions** that will be invoked during the scenario, *i.e.* their execution time, cold start time, memory requirements, energy consumption, etc.;
* an **infrastructure description** -- the listing of the different **nodes available**, their different execution platforms (*i.e.* hardware resources), storage devices, network bandwidth, etc.;
* an **execution trace** -- the arrival times for all **user requests**, associated with the requested application and desired Quality of Service (QoS) level.

The user chooses their desired orchestration policy for the run and execute the main program. The simulator will:

* initialize the infrastructure as described: the scenario starts with all the nodes idle, waiting for new requests;
* follow the arrival times of events from the execution trace, and pass the user requests to the orchestrator;
* let the scheduler try to place these requests on function replicas;
* let the autoscaler allocate and deallocate hardware resources that will execute user requests.

The simulation advances when functions are invoked: it is a called a **task execution**. The simulator knows how long a function's response time is thanks to the metadata measured beforehand. These metadata concern the specific hardware and workloads the user is interested in scheduling. Details on the methodology we used to characterize various platforms and workloads can be found in our papers:

* V. Lannurien et al., ["HeROfake: Heterogeneous Resources Orchestration in a Serverless Cloud – An Application to Deepfake Detection"](https://hal.science/hal-04165179), 2023 IEEE/ACM 23rd International Symposium on Cluster, Cloud and Internet Computing (CCGrid), Bangalore, India, 2023, pp. 154-165, doi: 10.1109/CCGrid57682.2023.00024.
* V. Lannurien et al., "HeROcache: Storage-Aware Scheduling in Heterogeneous Serverless Edge -- The Case of IDS" (CCGrid 2024, accepted).

During the simulation, logs are written under the `log` directory. When all the user requests have been processed, the simulation stops and returns results summarizing the simulation run in the `result` directory.

To compare the outcomes of different policies, the user should call the `src.placement` module multiple times with different parameters -- once for each policy they want to evaluate. Each run will produces different results files in the output directory. These results allow comparing different orchestration policies according to various metrics, including (but not limited to) QoS violations, tasks consolidation across nodes, static and dynamic energy consumption, communication times, total makespan, etc. Finally, the user should call the `src.charts` module to generate the digest charts comparing the various results for the scenario.

Various example `scenario-*.sh` scripts are given at the root of the repository to guide you through HeROsim's usage.

## Usage

Two methods are proposed to run HeROsim:

1. Using Python on your host OS (tested under Ubuntu 22.04);
2. Using Docker and/or Docker Compose.

### Method 1: Ubuntu 22.04 and Python

#### Setup Python

You will need Python 3.12 to run the program. Although not necessary, we recommend using the following tools:
* `pyenv` to manage Python versions;
* `pipenv` to manage the project's dependencies.

Here are bootstrap instructions to setup `pyenv` and `pipenv` under Ubuntu 22.04:

```shell
# Install required library headers for pyenv
sudo apt-get install build-essential zlib1g-dev libffi-dev libssl-dev libbz2-dev libreadline-dev libsqlite3-dev liblzma-dev

# Install pip
sudo apt-get install python3-pip

# Install pyenv to manage Python versions
curl https://pyenv.run | bash

# Update PATH (append these to ~/.bashrc)
export PYENV_ROOT="$HOME/.pyenv"
command -v pyenv >/dev/null || export PATH="$PYENV_ROOT/bin:$PATH"
eval "$(pyenv init -)"

# If you used a previous version of Python, you might need to update setuptools
pip install --upgrade setuptools

# Install pipenv
pip install --user pipenv

# Update PATH (append these to ~/.bashrc)
export PIPENV_BIN="$HOME/.local/bin"
command -v pipenv >/dev/null || export PATH="$PIPENV_BIN:$PATH"
```

If you have already installed `pyenv` and/or `pipenv`, please check that you are running up-to-date versions:

* [Upgrading `pip`](https://pip.pypa.io/en/stable/installation/#upgrading-pip);
* [Upgrading `pyenv`](https://github.com/pyenv/pyenv?tab=readme-ov-file#upgrading);
* [Upgrading `pipenv`](https://pipenv.pypa.io/en/latest/installation.html#installing-pipenv).

#### Setup HeROsim's virtual environment

We assume that your current working directory is pointed at the root of the repository. The following instructions will install the necessary versions of Python 3.12 and the project's dependencies in a virtual environment using `pyenv` and `pipenv`:

```shell
# Install required Python version and project dependencies
pipenv install

# Install development dependencies if you wish to contribute to the codebase
pipenv install --dev

# Run virtual environment
pipenv shell

# Generate workload characteristics and traces
# e.g. 83 Requests per Second during 600 seconds for the CCGrid workloads
# This step is not necessary for Artifacts Evaluation, as the execution trace used in the paper ships with the repository
# python -m src.generator -d data/ids -t -r 83 -s 600

# Run the simulation scenario as shown in the paper
# e.g. compare performances of HRC, HRO, Knative, BPFF and RP policies
./scenario-ids.sh
```

### Method 2: Docker

This repository comes with a `Dockerfile` to run the simulator in a sandboxed environment.

```shell
# Build the image
docker build . -t ${USER}/herosim

# Run the image
# Output data will be written to anonymous volumes
docker run -it ${USER}/herosim

# Run the image
# Output data will be written to host directories
docker run -it -v ./chart:/home/app/chart -v ./log:/home/app/log -v ./result:/home/app/result ${USER}/herosim
```

A `docker-compose.yml` file is also distributed with the simulator for convenience.

```shell
# Run the image
# Output data will be written to named volumes specified in docker-compose.yml
docker compose up -d
```

## Developer usage

The simulator ships three base classes -- `Orchestrator`, `Autoscaler` and `Scheduler` -- that should be subclassed by users to implement their own policies.

* **`Orchestrator`**. Provides abstract initialization methods that are to be overridden to manage different structures of system state. For example, a Round Robin scheduler will need to know how many times each function replica has been selected for task placement, while a Least Connected scheduler will need to know the average concurrency in each replica to balance the load. This class is the point of entry for users to define their own data structures that will best represent the system state that will be passed around the `Autoscaler` and `Scheduler` to manage;
* **`Autoscaler`**. Provides the base behavior of the autoscaling platform, with creation and removal of function replicas. A number of abstract methods have to be overridden in each policy: resources selection for replica creation, replica initialization process, replica selection for removal, etc. These abstract methods operate at the granularity of a single function, all take the system state and the list of available hardware resources as input. The users are free to use whichever algorithms they wish to evaluate for resources management;
* **`Scheduler`**. Provides the base behavior of tasks placement, with task selection in the queue. One abstract method has to be overridden in each policy: the selection of replica among the pool to place each user request in queue. This method operates at the granularity of one user request, *i.e.* an application invocation, and takes the system state and the list of available function replicas as input.

The implementation overhead is minimal: the simplest couple of autoscaler and scheduler, namely the Random Placement policy, are implemented in less than 20 lines of code. This policy is a good starting point to create your own orchestrator: copy and rename the `src/policy/random` directory to start implementing your policy.

## License

HeROsim is released under the Apache License, Version 2.0. Feel free to modify, distribute, and use the software in accordance with the terms of the license. Contributions to the project are also welcome.
