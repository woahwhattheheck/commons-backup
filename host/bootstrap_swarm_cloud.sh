#!/usr/bin/env bash
# Prepare the real Commons/Deathstar environment in an existing cloud workspace.
set -euo pipefail

swarm_workspace=/workspace
swarm_commons="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)"
swarm_prepare=0
while (($#)); do
  case "$1" in
    --workspace) swarm_workspace="$2"; shift 2 ;;
    --commons) swarm_commons="$2"; shift 2 ;;
    --prepare) swarm_prepare=1; shift ;;
    *) echo "Usage: bash bootstrap_swarm_cloud.sh [--prepare] [--workspace PATH] [--commons PATH]" >&2; exit 2 ;;
  esac
done
swarm_state="$swarm_workspace/shared/swarm"
swarm_deathstar="$swarm_workspace/deathstar"

# Reuse a selected repository. A missing checkout is created only in this cloud
# workspace, using the inherited GitHub session; credentials are never printed.
if [[ ! -d "$swarm_deathstar/deathstar" ]]; then
  if [[ -e "$swarm_deathstar" ]]; then
    echo "Existing Deathstar path is not its checkout: $swarm_deathstar" >&2
    exit 1
  fi
  git clone --depth 1 --filter=blob:none \
    https://github.com/woahwhattheheck/deathstar.git "$swarm_deathstar"
fi
python3 -B "$swarm_commons/host/swarm_cloud_environment.py" \
  --workspace "$swarm_workspace" --state "$swarm_state" \
  --deathstar "$swarm_deathstar" --commons "$swarm_commons" init
python3 -B "$swarm_commons/host/swarm_cloud_toolchains.py" install \
  --root "$swarm_state/toolchains"
python3 -B "$swarm_commons/host/swarm_cloud_languages.py" install \
  --root "$swarm_state/toolchains"
source "$swarm_workspace/activate-swarm.sh"
if ((swarm_prepare)); then
  echo "Prepared source, reusable toolchains and activation. Services start in each new task."
else
  swarm-env up
fi
