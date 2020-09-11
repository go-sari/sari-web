#!/bin/bash

# Generates the contents of a requirements.txt from the Pipfile, ignoring the
# packages already provided by AMS Python3.8 Lambda environemtn.

set -euo pipefail

jq --argjson pkgs "$(awk -f filter-pkgs.awk Pipfile)" \
    -r '.default
        | to_entries[]
        | select(.key | in($pkgs))
        | .key + .value.version' Pipfile.lock
