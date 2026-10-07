# Example plugins

These ship with r2a2-science but are ordinary clients of the public API
(`r2a2.api`) — none of them is imported by `r2a2` core.

- `toy_theory/` — minimal plugin, pure Python. Run:
  `PYTHONPATH=examples/toy_theory r2a2 audit toy_theory`
- `pendulum_theory/` — conventional physics: exact energy identity control,
  small-angle comparator, hostile control against a bogus linear period law.
- `grut_adapter/` — **the adversarial test**. Loads GRUT's own
  `provenance/auditor.py` and `claims.json` as a client (set `GRUT_ROOT` if
  the GRUT repo is elsewhere), runs the original auditor unmodified, and
  adapts a claim fragment into an R2A2 Theory through the public SDK only.
  If supporting this ever requires a GRUT-specific conditional inside
  `r2a2` core, the abstraction has failed.
