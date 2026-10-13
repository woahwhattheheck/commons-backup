# Host-neutral always-on image for the grok.com Slack connector.
# Build from the repository root:
#   docker build -f integrations/grok_slack/Dockerfile -t commons-grok-slack .
# GitHub Actions is not an always-on Socket Mode host.
# Copy named files only so a local gitignored env file cannot bake into the image.
FROM python:3.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/opt/commons \
    COMMONS_GROK_SLACK_STATE_DB=/var/lib/commons/grok_slack.sqlite3 \
    COMMONS_GROK_SLACK_HEALTH_BIND=127.0.0.1:8788

RUN useradd --system --uid 10001 --create-home --home-dir /var/lib/commons commons

WORKDIR /opt/commons
COPY commons_publication_policy.py /opt/commons/commons_publication_policy.py
COPY integrations/grok_slack/requirements.txt /opt/commons/requirements.txt
RUN pip install --no-cache-dir -r /opt/commons/requirements.txt
RUN mkdir -p /opt/commons/integrations/grok_slack /opt/commons/integrations/grokcom_revenue
COPY integrations/grok_slack/__init__.py \
     integrations/grok_slack/app_manifest.yaml \
     integrations/grok_slack/bridge.py \
     integrations/grok_slack/handoff.py \
     integrations/grok_slack/canary.py \
     integrations/grok_slack/env.example \
     integrations/grok_slack/run.sh \
     integrations/grok_slack/run-handoff.sh \
     integrations/grok_slack/run-handoff.ps1 \
     integrations/grok_slack/Dockerfile \
     integrations/grok_slack/compose.yml \
     integrations/grok_slack/commons-grok-slack.service \
     integrations/grok_slack/commons-grok-slack-handoff.service \
     integrations/grok_slack/README.md \
     /opt/commons/integrations/grok_slack/
COPY integrations/grokcom_revenue/__init__.py \
     integrations/grokcom_revenue/orchestrator.py \
     /opt/commons/integrations/grokcom_revenue/

USER commons
VOLUME ["/var/lib/commons"]
EXPOSE 8788

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python /opt/commons/integrations/grok_slack/bridge.py health --json --probe http://127.0.0.1:8788/health

CMD ["python", "/opt/commons/integrations/grok_slack/bridge.py", "serve"]
