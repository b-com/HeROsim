#!/usr/bin/env bash

# Boilerplate ################################

set -Eeuo pipefail
trap cleanup SIGINT SIGTERM ERR EXIT

# script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" &>/dev/null && pwd -P)

cleanup() {
  trap - SIGINT SIGTERM ERR EXIT
  # script cleanup here
}

msg() {
  echo >&2 -e "${1-}"
}

die() {
  local msg=$1
  local code=${2-1} # default exit status 1
  msg "$msg"
  exit "$code"
}

# Check pipenv environment
virtual_environment=${PIPENV_ACTIVE:-}
if [[ "$virtual_environment" -ne 1 ]]; then
  msg "The script must be run from within a pipenv virtual environment."
  msg "Please run pipenv shell from the script's directory."
  die "Virtual environment not found."
fi

# Input data #################################

data_directory="data/ids"
infrastructure_file="data/ids/infrastructure.json"
workload_trace="data/ids/traces/workload-83-600.json"

# Platform configuration #####################

keep_alive=30
queue_length=100

# Start scenario #############################

# Evaluation against baselines ###############

scheduling_strategy="hrc_hrc"
task_priority="least_penalty"
cache_policy="fifo"

python -m src.placement \
  --clear \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

scheduling_strategy="hro_hro"
task_priority="least_penalty"
cache_policy="fifo"

python -m src.placement \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

scheduling_strategy="kn_kn"
task_priority="fifo"
cache_policy="fifo"

python -m src.placement \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

scheduling_strategy="kn_bpff"
task_priority="fifo"
cache_policy="fifo"

python -m src.placement \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

scheduling_strategy="kn_rp"
task_priority="fifo"
cache_policy="fifo"

python -m src.placement \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

# Generate charts
chart_files=$(
  python -m src.charts -p -i "${infrastructure_file}" -d "${data_directory}" -w "${workload_trace}"
)

# Save logs
cp -r "log" "log_baselines"
# Save results
cp -r "result" "result_baselines"

# Evaluation of individual components ########

scheduling_strategy="hrc_hrc"
task_priority="least_penalty"
cache_policy="fifo"

python -m src.placement \
  --clear \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

scheduling_strategy="hrc_hro"
task_priority="least_penalty"
cache_policy="fifo"

python -m src.placement \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

scheduling_strategy="hro_hro"
task_priority="least_penalty"
cache_policy="fifo"

python -m src.placement \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

scheduling_strategy="hro_hrc"
task_priority="least_penalty"
cache_policy="fifo"

python -m src.placement \
  -i "${infrastructure_file}" \
  -d "${data_directory}" \
  -w "${workload_trace}" \
  -s "${scheduling_strategy}" \
  -c "${cache_policy}" \
  -t "${task_priority}" \
  -k "${keep_alive}" \
  -q "${queue_length}"

# Save logs
cp -r "log" "log_components"
# Save results
cp -r "result" "result_components"

# Generate charts
chart_files=$(
  python -m src.charts -p -i "${infrastructure_file}" -d "${data_directory}" -w "${workload_trace}"
)

: '
# Preview main chart file in VS Code
echo "${chart_files}" | while read -r chart_file; do
  if [[ -f ${chart_file} ]]; then
    if command -v code &> /dev/null; then
      code "${chart_file}"
    else
      echo "${chart_file}"
    fi
  fi
done
# '
