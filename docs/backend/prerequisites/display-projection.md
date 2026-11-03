# Prerequisite display projection

The native projector turns one compiled solver structure into the display pieces, their identities, their support bindings and the projection contexts a route calculation lights.

## The projection

`native/projector.cpp` owns the one projection. `PrerequisiteGraphCompiler.compile` asks the native compiler for the structure and its drawing in one call, and `src/course_explorer/prerequisite/projection.py` keeps only the frozen drawing DTOs and the request-local element allowance. The native projector builds one normalized display recipe per `(owner, use, member set, module-body flag, structural module flag, parent operator, path flags)` context, then collects the reachable `(recipe, parent display piece, nearest display piece)` context DAG and emits display pieces, connections, bindings, diagnostics and projection contexts into the same record view.

Elided recipes are flattened during that walk, and the walk emits only reachable attachments. Every recipe caches its set of drawn targets: a visible recipe holds its own fingerprint, and a hidden recipe holds the union of its children's and decorations' cached sets. Logical elision, internal-requirement eligibility and module or connector identity all read that one set, so unique displayed targets decide elision while the recipe holds every direct child reference and source binding.

The native projector keys each occurrence by its recipe's stable context key, its parent display piece and its nearest display piece, and gives it the identity `c:` plus a content digest of that flat tuple. Each `PrerequisiteProjectionContext` stores the native owner and piece, the native child slots as `(slot, context_id)` pairs and the member IDs that occurrence selects. A repeated flat key resolves to one row, so both native paths to a shared occurrence reference the same child context without enumerating reaching paths. The outermost emission returns the root context ID.

A visible occurrence emits its display piece and its incoming endpoint and fact attachment, binds its supports to its own display piece and associates that attachment with its own context. A transparent occurrence emits no edge: it binds to `binding_key` when it has one and otherwise to the inherited nearest display piece, and its children keep the inherited parent and nearest display pieces. An expanded occurrence places its descendants at `descendant_anchor`, so a visible head anchors its closure while a hidden head inherits the containing display piece. A display-only internal-requirement summary sits at its enclosing connector's drawn anchor, and its attachment is associated with the native child context of the slot that selects it, so a summary lights with its own child rather than with every sibling under one support. The materializer reads the emitted display-piece and edge tables without reordering or deriving them.

`PrerequisiteDisplayNode` carries a content-addressed identity, its display kind, owner, course or module identity, numeric bounds, reason or detail, member and diagnostic IDs, the path flags, provenance flags, the inferred-card marker and `markable`. For unresolved display pieces `reason` is the unresolved reason. For ignored display pieces it is the ignored kind. `markable` is true exactly for module, cardinality, credits, course-count and opaque-credit display pieces. `PrerequisiteDisplayEdge` groups every relationship between one endpoint pair, lists its member IDs and is `inferred_only` when every member fact is inferred. `PrerequisiteDrawingGraph` holds the sorted display pieces and edges. `PrerequisiteDrawingAllowance` carries the configured limit and the unique reachable counts.

The projector preserves canonical course display pieces, unique-child logical elision, same-operator folding, module member cards, internal-requirement options and genuine numeric boundaries.

## Module cards and nested modules

One module display piece holds the flattened course cards of the module rules it contains. A structurally nested module contributes its cards and external obligations to that enclosing display piece and emits no display piece of its own. The member list already reaches through a structural nested module and stops at an expanded course head. A whole-module prerequisite met inside a member's own closure draws that module's display piece, because an expanded-course boundary resets the structural context.

## Hidden heads and origin flags

A hidden module-member head contributes no global course display piece. Its source use and fact bind to its containing display piece, while its real external obligations attach to the containing module as a conditional subtree. The subtree attachments belong to the member and expanded child contexts, so a basis-covered member never lights its unselected closure. Only a visible course occurrence contributes its origin flags, so a hidden official member never suppresses an independently visible inferred-only card.

A structural nested module's directly attached diagnostics are classified as contained while it is built, so the disappeared-module synthesis creates no nested display piece. The ignored annotation sits at its ordinary binding anchor, and every emitted display piece is root-reachable.

## Marks and the allowance

A saved mark never changes a recipe identity or a fold decision. The allowance counts the unique reachable display-piece IDs and endpoint records before any display DTO is materialized, so a refused or route-only projection receives its bindings, projection contexts and members. The configured `WebSettings.prerequisite_graph_max_elements` limit never applies to solving.

## Shared drawing identity

A display identity is `(course owner, content fingerprint)`: the displayed kind, its displayed values and the sorted unique fingerprints of its drawn children. A logical group whose children reach exactly one unique drawn target collapses to that target even when it lists several source occurrences. Each occurrence holds its own recipe reference, binding and native context row.

Courses are global terminals. Provenance, official kind, inferred category, inference metadata, mark state, child order, multiplicity, work keys and localized names never separate equal drawings. A mark is fixed input: a saved key for a display piece that a normalized drawing does not emit has no effect and applies again if the same identity returns. A structurally nested module emits no display piece, so a saved key for one has no effect.

The compact bindings map every scoped calculation support to the display pieces and markable boxes it represents. A hidden head, an elided wrapper, a structural nested module and a module-body support bind to their nearest emitted containing display piece, so no binding points to an un-emitted display piece. A mark on one display piece therefore applies to every calculation piece behind it, including opposite child orders and repeated numeric slots, while the calculation keeps each slot. A support may bind several display pieces when a shared course is reached from several owners.

A connection's members group by endpoint pair and complete fact, and one member is attributed to the union of its attachments' context IDs. Its identity is `m:` plus a digest of the endpoint pair and the fact, so alternative occurrences of one endpoint pair and fact share one member. Each selecting context stores the member IDs its occurrences own, and a purely synthetic diagnostic attachment has no context and never lights.

The drawing carries no computed node or member state. The browser's `projectRoute` in `web/src/solver/route-projection.ts` pairs each projected context with the selected drawing node for it, collects the members that context owns and follows only the child slots the node carries, and it derives the route's drawn nodes from the root plus the source and target endpoints of those lit members. A support that binds several drawn locations therefore contributes only the locations a chosen occurrence meets. [Satisfaction evaluation](/docs/backend/prerequisites/satisfaction-evaluation.md#the-browsers-box-states) states the box states the browser computes from this projection.

## Tests

`tests/prerequisite/test_graph_projection.py` covers canonical course display pieces shared globally, identical logical and numeric subtrees shared across provenance, visible connections grouped with their relationship evidence, module cards that hide a member closure without relabeling an independent occurrence, single-child collapsing, the composed AND role, provenance flags, activity retention, external module dependencies, a member whole-module prerequisite, module-membership scoping of shared external connections, and a member prerequisite choice that keeps its conditional OR. `tests/prerequisite/conftest.py` supplies the native fixture library these tests compile through.
