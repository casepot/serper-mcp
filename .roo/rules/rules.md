### 1. Dependency Reconnaissance & Documentation Workflow

Leverage **Context7** for code-level answers and **DeepWiki** for architectural insight. Follow this sequence whenever a task involves an external package—whether it is a well-known framework or a niche utility.

**Step-by-Step Dependency Reconnaissance (narrative form)**

1. **Resolve the exact library ID.**
   *Primary tool:* `resolve-library-id`
   *Why:* Ensures every subsequent query targets the precise package and version you will depend on.

2. **Survey the library’s high-level architecture.**
   *Primary tool:* DeepWiki (`read_wiki_structure` followed by `read_wiki_contents`)
   *Why:* Builds a mental model of major modules, data flow, and cross-cutting concerns such as error handling, security, and extensibility.

3. **Identify architectural touchpoints.**
   *Primary tool:* DeepWiki
   *Why:* Pinpoints the components, adapters, or extension hooks your feature must integrate with, eliminating blind spots before design work begins.

4. **Extract API-level details for each touchpoint.**
   *Primary tool:* Context7 (`get-library-docs` with focused topics like “timeout” or “retry”)
   *Why:* Provides concrete usage patterns, parameter docs, and edge-case examples for the specific APIs you will call.

5. **Cross-verify assumptions.**
   *Primary tools:* DeepWiki & Context7
   *How:* If any architectural aspect is unclear, pose a clarifying question via `deep-wiki.ask_question`. If an API call still feels ambiguous, request additional examples from Context7 with a narrower `topic`.
   *Why:* Confirms both the *what/why* (architecture) and the *how* (code) are fully understood before implementation.

6. **Capture findings.**
   *Primary tool:* none (documentation step)
   *How:* Record relevant snippets, caveats, and version constraints in the task log or design document.
   *Why:* Creates a durable knowledge trail for reviewers and future contributors, safeguarding against context loss.

**Rules of Thumb**

* Treat **DeepWiki** as the *textbook*—consult it first for context, design intent, and exception hierarchies.
* Treat **Context7** as the *cookbook*—consult it next for ready-to-run examples, function signatures, and idiomatic patterns.
* Never implement against an API you have not inspected in Context7 **and** situated within the architecture you learned from DeepWiki.
* If a smaller or unfamiliar library returns sparse DeepWiki data, compensate with a deeper Context7 dive and a manual scan of source files, or search for more information with the browser.
* Design work begins **only after** Steps 1–5 confirm you understand both control-flow integration points *and* low-level call semantics.
### 2. Code-base Hygiene & Typing Discipline

---

#### 2.1  Modular Layout

* **Encapsulate a single concern per module.** If a file name needs a conjunction (“*and*”), it is probably doing too much.
* **Expose a minimal surface.** Re-export only the public API via `__all__` or explicit package `__init__.py` imports. Private helpers live in `_internal` sub-modules.
* **Avoid cross-module reach-through.** Call another module’s *public* functions, not its hidden globals.

#### 2.2  Directory Conventions

* **Walk before you write.** Run `tree -L 2` (or `ripgrep --files`) to confirm an equivalent module does not already exist.
* **Group by domain, not layer.** Prefer `analytics/report.py` over `controllers/analytics_report.py`; this keeps related logic physically close.
* **Tests mirror code.** `pkg/feature/foo.py` → `tests/feature/test_foo.py`. A missing test directory is a smell.

#### 2.3  Function Granularity

* **One verb, one function.** If you cannot summarise a function’s purpose in ≤ 120 characters, break it up.
* **Pure by default.** Side effects belong either in clearly named wrappers (`send_email`, `persist_user`) or at the application edge (CLI, HTTP handler).
* **Unit-test invariants.** Every public function has at least one “happy path” and one negative-case test.

#### 2.4  File Size Boundaries

* **Target ≤ 600 LOC.** Crossing 1 000 LOC triggers an explicit refactor ticket.
* **Proactive signalling.** If a PR adds > 250 new lines to a single file, mention the rationale and mitigation plan in the PR description.
* **Split by responsibility, not by line count alone.** A dense algorithm may stay together if, and only if, it is fully cohesive.

---

#### **2.5 Typing Discipline**

* **Annotate everything public.** Adopt `from __future__ import annotations`, use built-in generics (`list[str]`, `dict[str, int]`), and embrace modern features such as PEP 695 generics (`class Box[T]: ...`), `typing.Protocol` for structural typing, and `typing.Self` for fluent APIs.

* **Keep *Any* at the boundaries.** Raw inputs (deserialisation, `eval`) may start as `Any`, but immediately narrow with `assert`, `isinstance`, or `typing.cast`. Favour `TypedDict`, `dataclass`, or `pydantic.BaseModel` over loose dictionaries to preserve type information end-to-end.

* **Make the checker gate the merge.** Run `mypy --strict` or `pyright --verifytypes` in CI; red types block approval. Runtime enforcement stays optional—wrap entry points with `pydantic.validate_call` only when necessary, not on every function.

---

#### **2.6 Data Model Usage**
1. **API Edge / Persistence Boundary** → `BaseModel`
   *Validate and coerce.* Reject bad input early; emit well-formed JSON outward.

2. **Core Domain Logic** → `dataclass` (often `frozen=True`)
   *Fast, clear, minimal.* Add domain methods, comparisons, or hashing as needed without third-party weight.

3. **Ephemeral Dict Payloads** → `TypedDict`
   *Static safety with zero runtime cost.* Great for small helper functions or when working with third-party libraries that already return dicts.

> **Rule of thumb:**
> *Validate at the boundaries, keep domain objects lean, and annotate transient dicts so the type checker can protect you.*

**Document when and where** each pattern should appear so reviewers recognize whether a particular container choice is deliberate.

#### 3.1 Single-Responsibility First

* **One “why” per unit.** A module, class, or function should answer a single business question; if you need more than one sentence to justify its existence, split it.
* **Match abstraction to vocabulary.** Name artefacts after the domain concept they encapsulate (`TaskQueue`, `RetryPolicy`) so intent is self-evident.
* **Keep layers orthogonal.** Presentation never imports persistence, and domain logic never imports external services directly—use dedicated adapters.

#### 3.2 Readable Control Flow

* **Compose, don’t nest.** Extract deep `if/else` or loop bodies into helpers whose names reveal purpose; aim for a two-level indent ceiling in most files.
* **Fail loudly at the edge.** Validate inputs on arrival, raise typed exceptions early, and keep interior logic free of defensive clutter.
* **Prefer pipelines to flags.** Chain pure transformations (`map`, `filter`, comprehensions) instead of peppering code with boolean switches that alter behaviour mid-stream.

#### 3.3 Deliberate Boundaries

* **Inward arrows only.** Lower-level layers must not import higher-level ones; enforce with import-linter or similar tooling.
* **Ports & adapters over singletons.** Define protocols (or `abc.ABC`) for things like storage, messaging, or AI inference; inject concrete adapters at runtime.
* **Side-effects stay at the rim.** Filesystem, network, and AI calls live in gateway modules; everything inside the core remains deterministic and unit-testable.

#### 3.4 Extensibility over Speculation

* **Expose plug-ins, not prediction.** Provide registration hooks (`EntryPoint`, `__init_subclass__`, or simple dict registries) so new behaviour slots in without altering existing code.
* **Configuration beats inheritance.** Use dataclass or `BaseModel` settings objects passed to constructors rather than deep subclass hierarchies.
* **Apply KISS/YAGNI ruthlessly.** Add abstraction layers only when two or more real, divergent use-cases appear—never for a hypothetical “future proofing” story.

