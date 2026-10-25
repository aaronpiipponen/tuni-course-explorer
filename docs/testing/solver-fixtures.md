# Solver fixtures

This page lists the seven generated solver JSON files of the TypeScript solver and the commands that write them.

## The files and their exporters

| File | Python owner |
|---|---|
| `web/src/solver/fixtures/satisfaction.json` | `tests.prerequisite.export_solver_fixtures.main()` |
| `web/src/solver/fixtures/route-activity.json` | `tests.prerequisite.export_route_fixtures.main()` |
| `web/src/solver/fixtures/route-approximation.json` | `tests.prerequisite.export_route_fixtures.main()` |
| `web/src/solver/fixtures/route-contracts.json` | `tests.prerequisite.export_route_fixtures.main()` |
| `web/src/solver/fixtures/route-minimum.json` | `tests.prerequisite.export_route_fixtures.main()` |
| `web/src/solver/fixtures/route-module-failures.json` | `tests.prerequisite.export_route_fixtures.main()` |
| `web/src/solver/fixtures/route-module-shortfall.json` | `tests.prerequisite.export_route_fixtures.main()` |

The exporters import the real prerequisite builders and the real solver structures, so a fixture shows what the server writes for the named scenario.

The satisfaction fixture holds the structures and node-state cases of the satisfaction tests. The route fixtures hold complete solver structures for the activity, approximation, contract, minimum, module-failure and module-shortfall scenarios, together with the drawing display where a scenario needs one. Several entries repeat one scenario under a different basis, mark set or module selection, and each entry is a complete structure. The files are serialized as indented JSON so a reader can compare two structures in a diff.

## Regeneration

```bash
uv run python -m tests.prerequisite.export_solver_fixtures
uv run python -m tests.prerequisite.export_route_fixtures
```

Run the exporter that owns the changed scenario. Each command writes every file in its own group with a trailing newline. Regeneration is an explicit step after a change to a structure builder or to an exported DTO, and the regenerated file is reviewed with that change.

## Test import and the app bundle

The TypeScript tests import the fixture JSON directly, so the fixture data reaches the tests alone. The browser bundle is built from the application entry point.

The `npm --prefix web run solver:build` command builds the Node machine route bundle. It writes `web/src/solver/cli.ts` to `web/.solver-cli/cli.js`, and that directory is ignored by Git. The fixtures are separate from that bundle.
