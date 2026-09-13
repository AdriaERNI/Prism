# prism-installer/tests/fixtures/deliberately-broken.ps1
# Always fails. Its only job is to prove the gate can go RED: a gate that
# accepts a known-bad input is not gating. Never invoked by the suite pass,
# only by test-runner-report.ps1.
. (Join-Path (Join-Path (Join-Path (Join-Path $PSScriptRoot '..') '..') 'shared') 'installer-common.ps1')
Assert-ExitCode -Expected @(0) -Actual 101 -Because 'this fixture is designed to fail'
