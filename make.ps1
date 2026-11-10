# Windows / PowerShell equivalent of the Makefile.
# Usage:  .\make.ps1 reconcile   (or: pwsh .\make.ps1 test)
param([Parameter(Position = 0)][string]$Target = "help")

$ErrorActionPreference = "Stop"

switch ($Target.ToLower()) {
    "setup" {
        python -m pip install -e ".[dev]"
    }
    "test" {
        python -m pytest
    }
    "reconcile" {
        python -m payment_reconciliation reconcile --orders data/orders.csv --events data/events.jsonl --out outputs
    }
    "digest" {
        python -m payment_reconciliation digest --summary outputs/summary.json
    }
    "findings" {
        python scripts/generate_findings.py --summary outputs/summary.json --states outputs/order_states.csv --out docs/findings.md
    }
    "clean" {
        Remove-Item -Force -ErrorAction SilentlyContinue outputs/order_states.csv, outputs/summary.json, outputs/orphan_events.csv, outputs/mismatches.csv, outputs/.reconcile_work.sqlite
        Remove-Item -Recurse -Force -ErrorAction SilentlyContinue .pytest_cache, build, dist
        Get-ChildItem -Recurse -Directory -Filter "*.egg-info" | Remove-Item -Recurse -Force -ErrorAction SilentlyContinue
    }
    default {
        Write-Host "Payment Reconciliation Service - available targets:"
        Write-Host "  .\make.ps1 setup       install with dev extras"
        Write-Host "  .\make.ps1 test        run the 96-test suite"
        Write-Host "  .\make.ps1 reconcile   reconcile data/orders.csv x data/events.jsonl -> outputs/"
        Write-Host "  .\make.ps1 digest      print headline figures from outputs/summary.json"
        Write-Host "  .\make.ps1 findings    generate docs/findings.md from your outputs"
        Write-Host "  .\make.ps1 clean       remove generated artifacts"
    }
}
