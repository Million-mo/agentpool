# Same-type URI scheme registration is idempotent

`UriSchemeRegistry.register()` now treats a scheme already claimed by another
instance of the **same provider type** as an idempotent no-op instead of
raising `UriSchemeConflictError`. Only a genuinely different provider type
claiming an already-owned scheme still raises.

Why: manifests commonly configure one capability per agent with per-role
variant settings (e.g. three `type: viking` capabilities — knowledge-base,
vision, and research agents — each with different `support_vision`,
`enable_memory`, and tool-filter options). These are separate instances of
the same provider type sharing one URI scheme namespace (`viking://`); the
first instance claims ownership and the others reuse it. Before this fix,
pool init crashed on the second registration with:

```
UriSchemeConflictError: URI scheme 'viking' is already claimed by
'VikingCapability'; cannot register 'VikingCapability'
RuntimeError: Failed to initialize agent pool
```

Per-agent behavior is unaffected: each capability instance stays registered
at AGENT scope in the `ExtensionRegistry`, so its own tools, memory, and
URI-guard settings continue to apply. The scheme registry only routes
`scheme://` resource URI lookups and keeps the first same-type claimant.