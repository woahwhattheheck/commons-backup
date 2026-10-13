# Start the shared swarm cloud setup

Use this as the saved cloud environment's Start skill. Run it in the task's
selected existing cloud workspace. Each task has its own working files.

1. Read `/workspace/commons/RULES.md` in full. Live owner instructions win.
2. Source `/workspace/activate-swarm.sh` in each worker shell.
3. Run `swarm-env up`, then `swarm-env status` and
   `swarm-capacity --path /workspace --path /dev/shm`. These observe actual
   service and capacity state; they do not establish every provider binding.
4. Use the current harness's actual connected GitHub and Slack tools. Discover
   their current schemas at work boundaries. Do not infer access from a tool
   count or from another task's credentials.
5. For source changes, open distinct cloud worktrees through `swarm-current`.
   Select private writable build directories with
   `eval "$(swarm-worker NAME --java 21 --node 24)"`. JDK17 and Node18 can be
   selected when required by the current project. Reuse existing source-bound
   builds and generated artifacts; do not run test batteries.
6. Keep coordination in the existing canonical `state/claims` road. Keep
   private runtime state under `/workspace/shared/swarm`; preserve other
   workers' changes and use stable operation IDs for uncertain effects.

Read `commons/host/SWARM_CLOUD_ENVIRONMENT.md` for runtime and service details.
Do not create paid compute, recurring tasks, model jobs or owner-PC clones merely
by starting the setup. Missing model/device/provider bindings stay explicit.

For Dot's first attached task, record its own `environment_status` result. Confirm
the saved `source_config_id` and version, then run `swarm-env status` successfully
inside that task. The old thread's runtime ID is not proof of this attachment.
