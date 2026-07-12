# `prism serve` -- start the MCP HTTP server in the background, probe it, stop.
#
# The server runs streamable-http; a plain GET on /mcp returns a 4xx/200
# but proves the listener is up. We don't try to speak MCP from PowerShell.

. "$PSScriptRoot\..\_common.ps1"

Begin-Suite "serve"

function Start-PrismServe {
    param([int] $Port = 13000)
    $exe = Get-PrismExe
    $logOut = "C:\prism-tests\serve.out.log"
    $logErr = "C:\prism-tests\serve.err.log"
    Remove-Item $logOut, $logErr -ErrorAction SilentlyContinue
    $proc = Start-Process -FilePath $exe `
                          -ArgumentList @("serve", "--port", "$Port", "--skip-preflight") `
                          -PassThru -WindowStyle Hidden `
                          -RedirectStandardOutput $logOut `
                          -RedirectStandardError  $logErr
    return $proc
}

function Wait-PortListening {
    param([int] $Port, [int] $TimeoutSec = 30)
    $deadline = (Get-Date).AddSeconds($TimeoutSec)
    while ((Get-Date) -lt $deadline) {
        $tcp = Test-NetConnection -ComputerName 127.0.0.1 -Port $Port -InformationLevel Quiet -WarningAction SilentlyContinue
        if ($tcp) { return $true }
        Start-Sleep -Milliseconds 500
    }
    return $false
}

Test-Case "prism serve binds the configured port" {
    $port = 13000
    $proc = Start-PrismServe -Port $port
    try {
        $up = Wait-PortListening -Port $port -TimeoutSec 30
        Assert-True $up "server did not open port $port within 30s"
    } finally {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

Test-Case "prism serve responds to HTTP on /mcp" {
    $port = 13001
    $proc = Start-PrismServe -Port $port
    try {
        Assert-True (Wait-PortListening -Port $port -TimeoutSec 30) "port $port never opened"
        # MCP streamable-http requires a POST with init payload; a GET
        # returns 4xx/405 but proves the HTTP listener is wired up.
        try {
            $resp = Invoke-WebRequest -Uri "http://127.0.0.1:$port/mcp" -UseBasicParsing -TimeoutSec 5
            $code = $resp.StatusCode
        } catch {
            $code = $_.Exception.Response.StatusCode.value__
        }
        Assert-True ($code -is [int] -and $code -ge 200 -and $code -lt 600) "no HTTP response on /mcp (got: $code)"
    } finally {
        if ($proc -and -not $proc.HasExited) {
            Stop-Process -Id $proc.Id -Force -ErrorAction SilentlyContinue
        }
    }
}

Test-Case "prism serve --help advertises --port and --skip-preflight" {
    $r = Invoke-Prism serve --help
    Assert-ExitCode 0 $r.ExitCode
    Assert-Contains $r.Stdout "--port"
    Assert-Contains $r.Stdout "skip-preflight"
}