# run-spike.ps1 — Vidya rate-limit spike validation (8 → 30 VU)
# Prerequisites: k6 installed (https://k6.io/docs/getting-started/installation/)
# Usage:
#   .\run-spike.ps1
#   .\run-spike.ps1 -OutFile results\spike-$(Get-Date -f yyyyMMdd-HHmm).json

param(
  [string]$BaseUrl       = 'http://vidya.127.0.0.1.nip.io:9080/api',
  [string]$Tenant        = 'dev',
  [string]$FacultyEmail  = 'faculty@dev.vidya.local',
  [string]$FacultyPass   = 'Faculty@123',
  [string]$OutFile       = ''
)

$script = Join-Path $PSScriptRoot 'spike.js'

$args = @(
  'run',
  '-e', "BASE_URL=$BaseUrl",
  '-e', "TENANT=$Tenant",
  '-e', "FACULTY_EMAIL=$FacultyEmail",
  '-e', "FACULTY_PASS=$FacultyPass"
)

if ($OutFile) {
  $args += '--out', "json=$OutFile"
}

$args += $script

Write-Host "Running spike test against $BaseUrl ..." -ForegroundColor Cyan
k6 @args
