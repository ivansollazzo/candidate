/** Import rules for src/, checked with `npm run check:imports`. They describe the current layout; each migration phase tightens them. */
module.exports = {
  forbidden: [
    {
      name: "no-circular",
      comment: "warning until phase 5: lib/i18n ↔ lib/auth and lib/api → lib/status → lib/i18n → lib/auth → lib/api",
      severity: "warn",
      from: {},
      to: { circular: true },
    },
    { name: "no-unresolvable", severity: "error", from: {}, to: { couldNotResolve: true } },
    { name: "no-orphans", severity: "error", from: { orphan: true, pathNot: "\\.d\\.ts$|^src/main\\.tsx$" }, to: {} },
    {
      name: "lib-without-ui",
      comment: "lib/ holds logic and data access, never components or pages",
      severity: "error",
      from: { path: "^src/lib/" },
      to: { path: "^src/(components|pages)/" },
    },
    {
      name: "components-without-pages",
      severity: "error",
      from: { path: "^src/components/" },
      to: { path: "^src/pages/" },
    },
    {
      name: "ui-primitives-stay-generic",
      comment: "components/ui/ only uses itself and lib/utils",
      severity: "error",
      from: { path: "^src/components/ui/" },
      to: { path: "^src/", pathNot: "^src/components/ui/|^src/lib/utils\\.ts$" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: { exportsFields: ["exports"], conditionNames: ["import", "require", "node", "default"] },
  },
}
