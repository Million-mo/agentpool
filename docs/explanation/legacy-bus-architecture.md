# Legacy Bus Architecture

## Overview

The EventBus in `src/agentpool/orchestrator/event_bus.py` uses a single-threaded
event loop with bounded queues. This document explains the original design.

## The Old Queue Model

Previously, the `EventBus` relied on `asyncio.Queue` with no replay buffer.
Every subscriber had to be active at the time of publication or the event
would be lost.

## Migration to Bounded Queues

In M2, the EventBus was upgraded to use bounded queues with replay buffers.
See `src/agentpool/legacy/old_event_bus.py` for the original implementation.

## Deprecated APIs

- `EventBus.subscribe_all()` — removed in M2
- `EventBus.fire_and_forget()` — replaced by `publish()`
