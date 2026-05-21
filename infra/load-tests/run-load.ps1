# run-load.ps1 — Vidya sustained load baseline (10 VU, 60 s)
# Prerequisites: k6 installed (https://k6.io/docs/getting-started/installation/)
# Usage:
#   .\run-load.ps1
#   .\run-load.ps1 -OutFile results\load-$(Get-Date -f yyyyMMdd-HHmm).json

param(
  [string]$BaseUrl       = 'http://vidya.127.0.0.1.nip.io:9080/api',
  [string]$Tenant        = 'dev',
  [string]$FacultyEmail  = 'faculty@dev.vidya.local',
  [string]$FacultyPass   = 'Faculty@123',
  [string]$OutFile       = ''
)

$script = Join-Path $PSScriptRoot 'load.js'

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

Write-Host "Running load test against $BaseUrl ..." -ForegroundColor Cyan
k6 @args
