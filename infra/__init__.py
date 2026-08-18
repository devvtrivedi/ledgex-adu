"""Cross-cutting plumbing with zero business logic and zero layer.

Not core/: core/* may import core/model, infra/ and stdlib/third-party
only (§2) -- a rule about keeping domain logic free of jurisdiction
content (I1), not about being free of infra/ itself. infra/ has no
domain content to be free of in the first place -- env var reads and a
bare DB connection aren't L0-L8 logic, they're what every layer (and
things outside core/ entirely -- api/, pipelines/,
jurisdictions/*/adapter.py) needs before any of that logic can run.
§2 self-contradicted on this point (README finding #29) until 1.38,
where the older, infra/-predating wording of the core/* rule was
corrected to match the diagram, this docstring's own second half, and
the actual import graph -- all three already agreed.

Not ops/: "ops" conventionally means deployment/operational tooling that
depends on the app, not a runtime dependency the app imports. Reusing
that slot for shared library code the app imports at runtime would read
backwards to the next person who opens it.

Import contract: infra/* may import stdlib/third-party only -- not even
core/model, so nothing downstream can ever come to depend on infra/ for
a domain type. Anything (core/, commerce/, jurisdictions/, pipelines/,
api/) may import infra/.

See docs/LEDGEX_SPEC.md §2 for the full repository layout.
"""
