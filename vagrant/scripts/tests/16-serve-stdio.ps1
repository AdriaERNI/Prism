# `prism serve --transport stdio` -- verify the server speaks MCP over stdin/stdout.
#
# Unlike the HTTP transport, stdio has no port to probe.  We pipe a JSON-RPC
# `initialize` request into the process stdin and check that a valid JSON-RPC
# response comes back on stdout.  We also verify that `tools/list` returns a
# non-empty tool array, proving the full tool-discovery path works under stdio.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "serve-stdio"

# Send a JSON-RPC request to prism serve --transport stdio via stdin.
# Returns a [pscustomobject] with .Stdout .Stderr .ExitCode .
function Invoke-PrismStdio {
    param([string[]] $Lines)

    $exe = Get-PrismExe

    # stdio on the frozen Windows exe:
    # ---------------------------------
    # The .NET Process pipe approach (RedirectStandardInput, WriteLine,
    # StandardInput.Close()) does NOT deliver a usable EOF to the frozen
    # PyInstaller exe on Windows: the server reads the requests and replies,
    # but never sees end-of-stream, so the process stays alive until the
    # harness kills it after the 30 s timeout.  (It is purely a Windows
    # console/pipe EOF quirk -- identical runs on Linux exit cleanly.)
    #
    # Verified fix: pass the requests as a real file handle via
    # Start-Process -RedirectStandardInput.  A redirected file reaches a
    # genuine EOF, the stdio loop terminates, and the process exits promptly
    # with the full response on stdout (`exited=True`, 4097 bytes).
    # This is what FastMCP's stdio_server() treats as "client closed stdin".
    $stamp = [DateTime]::UtcNow.ToString("yyyyMMdd_HHmmss_fff")
    $dir = Join-Path $env:TEMP "prism-stdio-$stamp"
    $null = New-Item -ItemType Directory -Path $dir -Force
    $stdinFile  = Join-Path $dir "stdin.jsonl"
    $stdoutFile = Join-Path $dir "stdout.txt"
    $stderrFile = Join-Path $dir "stderr.txt"

    try {
        # One JSON-RPC message per line, no trailing newline surprises.
        Set-Content -Path $stdinFile -Encoding Ascii -Value ($Lines -join "`r`n")

        $proc = Start-Process -FilePath $exe `
            -ArgumentList @('serve', '--transport', 'stdio') `
            -RedirectStandardInput  $stdinFile `
            -RedirectStandardOutput $stdoutFile `
            -RedirectStandardError  $stderrFile `
            -PassThru -WindowStyle Hidden

        # The server should process the requests and exit on stdin EOF; give
        # it 30 s, then kill to avoid wedging the suite behind WinRM.
        if (-not $proc.WaitForExit(30000)) {
            try { $proc.Kill() } catch {}
            $proc.WaitForExit(5000) | Out-Null
        }

        $stdout = if (Test-Path $stdoutFile) { [IO.File]::ReadAllText($stdoutFile) } else { "" }
        $stderr = if (Test-Path $stderrFile) { [IO.File]::ReadAllText($stderrFile) } else { "" }

        return [pscustomobject]@{
            Stdout   = $stdout
            Stderr   = $stderr
            ExitCode = $proc.ExitCode
        }
    } finally {
        Remove-Item -Recurse -Force $dir -ErrorAction SilentlyContinue
    }
}

Test-Case "prism serve --transport stdio responds to initialize" {
    $init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"prism-stdio-test","version":"1.0"}}}'
    $initialized = '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'

    $r = Invoke-PrismStdio -Lines @($init, $initialized)

    # stdout should contain a JSON-RPC response with id=1
    Assert-True ($r.Stdout.Trim().Length -gt 0) "no output on stdout (stderr: $($r.Stderr.Trim()))"

    # Each JSON-RPC message is on its own line; find the response with id:1
    $lines = $r.Stdout -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 }
    $initResp = $null
    foreach ($l in $lines) {
        try {
            $obj = $l | ConvertFrom-Json
            if ($obj.id -eq 1 -and $obj.result) { $initResp = $obj; break }
        } catch { continue }
    }

    Assert-True ($null -ne $initResp) "no JSON-RPC response with id=1 in stdout"
    Assert-HasProperty $initResp.result "protocolVersion" "initialize response missing protocolVersion"
    Assert-HasProperty $initResp.result "capabilities" "initialize response missing capabilities"
    Assert-HasProperty $initResp.result "serverInfo" "initialize response missing serverInfo"
}

Test-Case "prism serve --transport stdio lists tools" {
    $init = '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"prism-stdio-test","version":"1.0"}}}'
    $initialized = '{"jsonrpc":"2.0","method":"notifications/initialized","params":{}}'
    $listTools = '{"jsonrpc":"2.0","id":2,"method":"tools/list","params":{}}'

    $r = Invoke-PrismStdio -Lines @($init, $initialized, $listTools)

    Assert-True ($r.Stdout.Trim().Length -gt 0) "no output on stdout (stderr: $($r.Stderr.Trim()))"

    $lines = $r.Stdout -split "`r?`n" | Where-Object { $_.Trim().Length -gt 0 }
    $toolsResp = $null
    foreach ($l in $lines) {
        try {
            $obj = $l | ConvertFrom-Json
            if ($obj.id -eq 2 -and $obj.result) { $toolsResp = $obj; break }
        } catch { continue }
    }

    Assert-True ($null -ne $toolsResp) "no JSON-RPC response with id=2 in stdout"
    Assert-HasProperty $toolsResp.result "tools" "tools/list response missing tools array"
    Assert-True ($toolsResp.result.tools.Count -gt 0) "tools/list returned empty tools array"
}

Test-Case "prism serve --help advertises --transport stdio" {
    $r = Invoke-Prism serve --help
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "--transport"
    Assert-Contains $r.Stdout "stdio"
}