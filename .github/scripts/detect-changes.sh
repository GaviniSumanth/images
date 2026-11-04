#!/usr/bin/env bash
set -euo pipefail

BEFORE="${1:-}"
CURRENT="${2:-}"

old='{"repositories":[]}'

if [[ "$BEFORE" =~ ^[0-9a-f]{40}$ ]] && [[ "$BEFORE" != "0000000000000000000000000000000000000000" ]]; then
  old=$(git show "$BEFORE:releases.json" 2>/dev/null || echo '{"repositories":[]}')
fi

changed='[]'

if [[ "$BEFORE" =~ ^[0-9a-f]{40}$ ]] && [[ "$BEFORE" != "0000000000000000000000000000000000000000" ]]; then
  changed=$(git diff --name-only "$BEFORE" "$CURRENT" | jq -Rsc 'split("\n") | map(select(length > 0))')
else
  changed='[".github/workflows/build-container.yml"]'
fi

matrix=$(jq -cn \
  --argjson old "$old" \
  --argjson new "$(cat releases.json)" \
  --argjson changed "$changed" \
  '
  ($new | if type == "array" then {repositories: .} else . end) as $root |
  ($old | if type == "array" then {repositories: .} else . end) as $previous |

  $root.repositories |
  map(
    . as $r |

    ([
      $previous.repositories[]? |
      select(.repository == $r.repository)
    ][0] // null) as $o |

    ($r.containerfile | split("/") | .[0:-1] + ["tests"]) |
    join("/") as $test_dir |

    select(
      $o == null or
      $o.version != $r.version or
      $o.containerfile != $r.containerfile or
      $o.image != $r.image or
      ($changed | index($r.containerfile)) != null or
      ($changed | index($o.containerfile // "")) != null or
      any($changed[]; startswith("_shared/")) or
      ($changed | index(".github/workflows/build-container.yml")) != null or
      any($changed[]; startswith($test_dir + "/"))
    ) |

    {
      repo: $r.repository,
      tag: $r.version,
      containerfile: $r.containerfile,
      image: $r.image,
      test_context: $test_dir
    }
  )
  ')

echo "matrix=$matrix"