# Publish a selectable swarm environment for Dot

The running task instance and a saved environment configuration are different
objects. `environment_status` currently reports a running instance with no
`source_config_id`. Giving Dot that instance ID does not attach its task.

Prepare this configuration using the supported
[cloud environment UI](https://learn.chatgpt.com/docs/environments/cloud-environments):

| Field | Prepared value |
| --- | --- |
| Name | Swarm — Commons and Deathstar |
| Repositories | `woahwhattheheck/commons` and `woahwhattheheck/deathstar` |
| Install script | `bash /workspace/commons/host/bootstrap_swarm_cloud.sh --prepare` |
| Start skill | Contents of [SWARM_CLOUD_START.md](SWARM_CLOUD_START.md) |
| Network | The current unrestricted cloud policy, preserving the managed proxy and CA |
| Provider connections | Existing owner-connected GitHub/Slack and required native service bindings |

In a new setup, choose **Work in → Cloud → Select environment → Create
environment**, select the repositories, and choose **Get started**. Set the
Install script and Start skill above, run preparation, then **Save and Publish**.
Existing configurations can be edited under **Settings → Codex Cloud →
Environments** and republished. If Dot runs in another workspace, the available
**Privacy → Who can use** setting must include that workspace; inspect the
actual sharing options before changing them.

Publish the clean setup prepared from source and official toolchain artifacts.
Do not publish this task's private Slack/GitHub captures, credentials, databases,
jobs, browser sessions or runtime journals as a general environment snapshot.
The `--prepare` command installs prerequisites and activation without capturing
the running Docker services' inherited credential environment. New tasks start
their own services with their own current provider bindings.

Have Dot select the published setup for its cloud task. Verify in Dot's own task:

```bash
source /workspace/activate-swarm.sh
swarm-env up
swarm-env status
eval "$(swarm-worker dot --java 21 --node 24)"
javac -version
go version
```

Dot's `environment_status` must name the published `source_config_id` and
version, with current observations. Record its successful actual command before
claiming it can use the setup. Publication gives each task separate working
files; it does not attach Dot to this existing VM or its databases/jobs.

This session exposes only the cloud status reader. It has no callable saved
configuration writer, publish action or cross-task attach controller, so the
remaining Save/Publish/selection step must happen in the supported UI. The cloud
runtime skill explicitly says: “Configuration changes require the environment
configuration workflow and its user review.”
