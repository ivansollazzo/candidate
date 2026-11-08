/** Import rules for src/, checked with `npm run check:imports`. Layers: shared < features < app (main.tsx). */
module.exports = {
  forbidden: [
    { name: "no-circular", severity: "error", from: {}, to: { circular: true } },
    { name: "no-unresolvable", severity: "error", from: {}, to: { couldNotResolve: true } },
    { name: "no-orphans", severity: "error", from: { orphan: true, pathNot: "\\.d\\.ts$|^src/main\\.tsx$" }, to: {} },
    {
      name: "shared-without-features",
      comment: "shared/ holds what every feature uses and knows no feature or app page",
      severity: "error",
      from: { path: "^src/shared/" },
      to: { path: "^src/(features|app)/|^src/main\\.tsx$" },
    },
    {
      name: "features-without-app",
      comment: "app/ and main.tsx put the features together; features never import them",
      severity: "error",
      from: { path: "^src/features/" },
      to: { path: "^src/app/|^src/main\\.tsx$" },
    },
    {
      name: "ui-primitives-stay-generic",
      comment: "shared/ui/ only uses itself and shared/lib/utils",
      severity: "error",
      from: { path: "^src/shared/ui/" },
      to: { path: "^src/", pathNot: "^src/shared/ui/|^src/shared/lib/utils\\.ts$" },
    },
  ],
  options: {
    doNotFollow: { path: "node_modules" },
    tsConfig: { fileName: "tsconfig.json" },
    tsPreCompilationDeps: true,
    enhancedResolveOptions: { exportsFields: ["exports"], conditionNames: ["import", "require", "node", "default"] },
  },
}
