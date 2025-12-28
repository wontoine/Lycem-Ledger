<#
PowerShell examples for calling the Lycem-Ledger API.

Run PowerShell as needed and execute the commands below after starting the Django server:
  py manage.py runserver

If you see errors like "The term '-Body' is not recognized...", ensure you are using
Invoke-RestMethod (or Invoke-WebRequest) and that -Body / -ContentType are parameters to that cmdlet.
#>

$BaseUrl = "http://127.0.0.1:8000"

Write-Host "Forgot password examples"
$uri = "$BaseUrl/api/auth/forgot-password/"
# Using an email identifier
$body = @{ identifier = "toriaube2020@gmail.com" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $uri -Body $body -ContentType "application/json"
# Using a username identifier
$body = @{ identifier = "john.doe" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $uri -Body $body -ContentType "application/json"

Write-Host "Reset password example (replace token)"
$uri = "$BaseUrl/api/auth/reset-password/"
$body = @{ token = "<insert token here>"; new_password = "hash_customer1" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $uri -Body $body -ContentType "application/json"



Write-Host "Login examples"
$uri = "$BaseUrl/api/auth/login/"
# Preferred: provide username and password
$body = @{ username = "your_username"; password = "YourPassword" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $uri -Body $body -ContentType "application/json"
# Alternate: if you don't know the username, you may also supply an email (the API will first try username, then email)
$body = @{ email = "customer@example.com"; password = "YourPassword" } | ConvertTo-Json
Invoke-RestMethod -Method Post -Uri $uri -Body $body -ContentType "application/json"

Write-Host "PowerShell curl (curl.exe) examples"
# In PowerShell, prefer single quotes around JSON so quotes are not eaten by the shell.
# Forgot password with username using curl.exe
cmd /c "curl.exe -i -X POST 'http://127.0.0.1:8000/api/auth/forgot-password/' -H 'Content-Type: application/json' -d '{"identifier":"john.doe"}'"
# Forgot password with email using curl.exe
cmd /c "curl.exe -i -X POST 'http://127.0.0.1:8000/api/auth/forgot-password/' -H 'Content-Type: application/json' -d '{"identifier":"toriaube2020@gmail.com"}'"
# Or read JSON from a file to avoid quoting issues
# New-Item -Path . -Name body.json -ItemType File -Value '{"identifier":"john.doe"}' | Out-Null
# cmd /c "curl.exe -i -X POST 'http://127.0.0.1:8000/api/auth/forgot-password/' -H 'Content-Type: application/json' --data-binary '@body.json'"

Write-Host "Create account example from file (expects .\\body.json)"
$uri = "$BaseUrl/api/auth/create-account/"
if (Test-Path .\body.json) {
  $json = Get-Content -Path .\body.json -Raw
  Invoke-RestMethod -Method Post -Uri $uri -Body $json -ContentType "application/json"
} else {
  Write-Warning "body.json not found at repo root. Create it first."
}
