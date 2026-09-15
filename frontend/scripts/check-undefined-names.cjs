#!/usr/bin/env node
// Fails when a component or function is used but never imported or declared.
//
// The production build does not catch this. On Sep 4 `<Settings2>` lost its
// import and blanked the whole Settings page (including account deletion) on
// web, iOS and Android for ten days.
//
// Usage: node scripts/check-undefined-names.cjs [srcDir]   (default: ./src)
const path = require("path");
const { ESLint } = require("eslint");

const RULES = ["react/jsx-no-undef", "no-undef"];

const GLOBALS = [
  "window", "document", "navigator", "console", "process", "setTimeout", "clearTimeout",
  "setInterval", "clearInterval", "fetch", "URL", "URLSearchParams", "FileReader", "Blob",
  "FormData", "localStorage", "sessionStorage", "Intl", "Promise", "Image", "requestAnimationFrame",
  "cancelAnimationFrame", "AbortController", "MediaRecorder", "atob", "btoa", "location", "history",
  "alert", "confirm", "crypto", "performance", "CustomEvent", "Event", "HTMLElement",
  "IntersectionObserver", "ResizeObserver", "MutationObserver", "Notification", "self", "globalThis",
  "require", "module", "Buffer", "TextEncoder", "TextDecoder", "structuredClone", "queueMicrotask",
  "Audio", "File", "getComputedStyle", "matchMedia", "screen", "open", "print",
];

const main = async () => {
  const srcDir = path.resolve(process.argv[2] || path.join(__dirname, "..", "src"));
  const eslint = new ESLint({
    cwd: srcDir,
    overrideConfigFile: true,
    overrideConfig: [
      // Top-level ignores: inside a `files` block it would only skip that block,
      // and tests would still be parsed without JSX support.
      { ignores: ["**/*.test.js"] },
      {
        files: ["**/*.{js,jsx}"],
        linterOptions: { reportUnusedDisableDirectives: "off" },
        languageOptions: {
          ecmaVersion: "latest",
          sourceType: "module",
          parserOptions: { ecmaFeatures: { jsx: true } },
          globals: Object.fromEntries(GLOBALS.map((name) => [name, "readonly"])),
        },
        plugins: { react: require("eslint-plugin-react") },
        rules: Object.fromEntries(RULES.map((rule) => [rule, "error"])),
      },
    ],
  });

  const results = await eslint.lintFiles(["**/*.{js,jsx}"]);
  const problems = results.flatMap((result) =>
    result.messages
      .filter((message) => RULES.includes(message.ruleId) || message.fatal)
      .map((message) => `${path.relative(srcDir, result.filePath)}:${message.line} ${message.message}`),
  );

  if (problems.length) {
    console.error(`Undefined names found:\n${problems.join("\n")}`);
    process.exit(1);
  }
  console.log(`No undefined names in ${results.length} files.`);
};

main().catch((error) => {
  console.error(error);
  process.exit(2);
});
