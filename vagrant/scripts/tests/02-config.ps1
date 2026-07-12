# `prism config` covers no-arg display, single flag updates, interactive
# walkthrough, per-key reset, and full reset. All without touching IRIS.
#
# This test deliberately runs LAST among config-touching scripts via its
# own setup/teardown to avoid clobbering the connection settings used by
# the rest of the suite.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "config"

# Snapshot the current config so we can restore it at the end.
$snapshotPath = "$env:LOCALAPPDATA\prism\config.json"
$snapshot = $null
if (Test-Path $snapshotPath) {
    $snapshot = Get-Content $snapshotPath -Raw
}

try {
    Test-Case "prism config (no args) shows all settings" {
        $r = Invoke-Prism config
        Assert-ExitCode 0 $r.ExitCode
        Assert-Contains $r.Stdout "iris_base_url"
        Assert-Contains $r.Stdout "iris_username"
        Assert-Contains $r.Stdout "iris_namespace"
        Assert-Contains $r.Stdout "Config file:"
    }

    Test-Case "config redacts the password" {
        $r = Invoke-Prism config
        Assert-ExitCode 0 $r.ExitCode
        Assert-Contains $r.Stdout "***" "password should be redacted"
        Assert-NotContains $r.Stdout "iris_password                   SYS"
    }

    Test-Case "config -U updates iris_base_url" {
        $r = Invoke-Prism config -U "http://example.test:9999"
        Assert-ExitCode 0 $r.ExitCode
        Assert-Contains $r.Stdout "Saved 1 setting"
        $r2 = Invoke-Prism config
        Assert-Contains $r2.Stdout "http://example.test:9999"
    }

    Test-Case "config -r KEY removes a single key" {
        $null = Invoke-Prism config -U "http://example.test:9999"
        $r = Invoke-Prism config -r iris_base_url
        Assert-ExitCode 0 $r.ExitCode
        Assert-Contains $r.Stdout "Reset 1 setting"
        $r2 = Invoke-Prism config
        Assert-NotContains $r2.Stdout "http://example.test:9999"
    }

    Test-Case "config -r unknown_key fails with non-zero exit" {
        $r = Invoke-Prism config -r not_a_real_setting
        Assert-True ($r.ExitCode -ne 0) "expected non-zero exit on unknown key"
        Assert-Contains $r.Stderr "Unknown setting"
    }

    Test-Case "config sets multiple flags in one call" {
        $r = Invoke-Prism config `
                -n "USER" `
                --compile-flags "ck" `
                --terminal-method "ws"
        Assert-ExitCode 0 $r.ExitCode
        Assert-Contains $r.Stdout "Saved 3 setting"
        $r2 = Invoke-Prism config
        Assert-Contains $r2.Stdout "ck"
        Assert-Contains $r2.Stdout "ws"
    }

    Test-Case "config bool flag --debug toggles" {
        $null = Invoke-Prism config --debug
        $r = Invoke-Prism config
        Assert-Match $r.Stdout "iris_debug_enabled\s+True"
        $null = Invoke-Prism config --no-debug
        $r2 = Invoke-Prism config
        Assert-Match $r2.Stdout "iris_debug_enabled\s+False"
    }

    Test-Case "config int flag --debug-max-depth coerces" {
        $r = Invoke-Prism config --debug-max-depth 7
        Assert-ExitCode 0 $r.ExitCode
        $r2 = Invoke-Prism config
        Assert-Match $r2.Stdout "iris_debug_max_depth\s+7"
    }

    Test-Case "config --reset-all wipes config.json" {
        $null = Invoke-Prism config -U "http://wipeme:1234"
        $r = Invoke-Prism config --reset-all
        Assert-ExitCode 0 $r.ExitCode
        Assert-Contains $r.Stdout "Cleared"
        $r2 = Invoke-Prism config
        Assert-NotContains $r2.Stdout "http://wipeme:1234"
    }
} finally {
    # Restore the snapshot so subsequent suites still see VM IRIS.
    if ($snapshot) {
        $dir = Split-Path $snapshotPath -Parent
        if (-not (Test-Path $dir)) { New-Item -ItemType Directory -Path $dir -Force | Out-Null }
        Set-Content -Path $snapshotPath -Value $snapshot -Encoding UTF8 -NoNewline
    }
}