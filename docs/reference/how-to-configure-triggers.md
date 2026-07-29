# How to Configure Triggers

This guide walks you through setting up file watch triggers in AgentPool.

## Step 1: Define a Watch Trigger

Add a `watch` section to your YAML config:

```yaml
watch:
  - path: "src/**/*.py"
    action: run
    agent: formatter
```

## Step 2: Test the Trigger

Run `agentpool watch --config agents.yml` and modify a file matching the pattern.

## Step 3: Verify Execution

Check the agent's output in the console or storage backend.
