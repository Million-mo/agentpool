# OpenCode Bot Testing Guide

This file is for testing the OpenCode GitHub bot integration.

## Overview

The `opencode.yml` workflow integrates [OpenCode](https://opencode.ai) with our
GitHub workflow. It uses the Kimi Code Plan (`kimi-for-coding` provider) as the
LLM backend.

## Triggers

| Event | Trigger | Use Case |
|-------|---------|----------|
| `pull_request` | Auto on PR open/sync/reopen | Automated code review |
| `issue_comment` | `/oc` or `/opencode` in comment | Manual task on issue/PR |
| `pull_request_review_comment` | `/oc` on PR diff line | Targeted code feedback |

## Model

- **Provider**: `kimi-for-coding`
- **Model**: `kimi-for-coding` (maps to Kimi K2.7 Code)
- **Context**: 256K (Andante tier)

## Usage Examples

### Auto Review

Open a PR targeting `develop/agentic`. The bot reviews automatically.

### Manual Fix

Comment on any issue or PR:

```
/oc fix the typo in the README
```

### Inline Code Review

In the PR "Files changed" tab, comment on a specific line:

```
/oc add error handling here
```

## Notes

This file is a test artifact. Remove or keep as documentation.
