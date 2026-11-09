// Types must stay in sync with the commit parsers in .github/changelog.toml so
// every accepted commit can be grouped by the generated changelogs.
const types = [
  "build",
  "chore",
  "ci",
  "docs",
  "feat",
  "fix",
  "perf",
  "refactor",
  "revert",
  "test",
];

const scopes = [
  "audiobookshelf",
  "authelia",
  "ci",
  "deps",
  "docs",
  "error-pages",
  "images",
  "lldap",
  "release",
  "tests",
];

export default {
  extends: ["@commitlint/config-conventional"],
  rules: {
    "type-enum": [2, "always", types],
    "type-case": [2, "always", "lower-case"],
    "type-empty": [2, "never"],
    "scope-enum": [2, "always", scopes],
    "scope-empty": [2, "never"],
    "scope-case": [2, "always", "lower-case"],
    "subject-empty": [2, "never"],
    "subject-case": [2, "always", "lower-case"],
    "subject-full-stop": [2, "never", "."],
    "subject-exclamation-mark": [2, "never"],
    "subject-min-length": [2, "always", 3],
    "header-max-length": [2, "always", 100],
    "header-trim": [2, "always"],
    "body-leading-blank": [2, "always"],
    "body-max-line-length": [2, "always", 100],
    "footer-leading-blank": [2, "always"],
    "footer-max-line-length": [2, "always", 100],
  },
};
