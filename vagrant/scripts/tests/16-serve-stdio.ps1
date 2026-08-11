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
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName               = $exe
    $psi.Arguments              = 'serve --transport stdio'
    $psi.UseShellExecute        = $false
    $psi.RedirectStandardInput  = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError  = $true
    $psi.CreateNoWindow         = $true

    $proc = New-Object System.Diagnostics.Process
    $proc.StartInfo = $psi

    try {
        [void]$proc.Start()

        # Write each line to stdin, then close the stream so the server
        # sees EOF and exits cleanly.
        foreach ($line in $Lines) {
            $proc.StandardInput.WriteLine($line)
        }
        $proc.StandardInput.Close()

        # The server should process the requests and exit; give it 30s.
        if (-not $proc.WaitForExit(30000)) {
            try { $proc.Kill() } catch {}
            $proc.WaitForExit(5000) | Out-Null
        }

        $stdout = $proc.StandardOutput.ReadToEnd()
        $stderr = $proc.StandardError.ReadToEnd()
        return [pscustomobject]@{
            Stdout   = $stdout
            Stderr   = $stderr
            ExitCode = $proc.ExitCode
        }
    } finally {
        $proc.Close()
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