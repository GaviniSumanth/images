#!/usr/bin/env bash
set -euo pipefail

jq -e '
  (if type == "array" then {repositories: .} else . end) as $root |

  ($root.repositories | type == "array") and
  ($root.repositories | length > 0) and
  ([$root.repositories[].repository] | length == (unique | length)) and
  ([$root.repositories[].image] | length == ([$root.repositories[].image] | unique | length)) and
  all(
    $root.repositories[];
    (.repository | test("^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")) and
    (.version | test("^[A-Za-z0-9_][A-Za-z0-9_.-]{0,127}$")) and
    (.containerfile | test("^[A-Za-z0-9_-]+(/[A-Za-z0-9_-]+)*/Containerfile$")) and
    (.image | test("^[a-z0-9][a-z0-9._-]*$"))
  )
' releases.json