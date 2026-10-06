# Phase 1 end-to-end API verification for regtrack-backend.
# Requires: MySQL reachable (DB_URL) and the backend running (default http://localhost:8080).
param(
    [string]$Base = "http://localhost:8080",
    [string]$AdminEmail = "admin@regtrack.local",
    [string]$AdminPassword = "Admin@12345"
)

$ErrorActionPreference = "Stop"
$webhookSecret = $env:WEBHOOK_SECRET
if (-not $webhookSecret) { $webhookSecret = "dev-webhook-shared-secret-please-change" }

$script:pass = 0
$script:fail = 0

function Assert($name, $condition, $detail) {
    if ($condition) {
        $script:pass++
        Write-Host "  PASS  $name"
    } else {
        $script:fail++
        Write-Host "  FAIL  $name  ->  $detail" -ForegroundColor Red
    }
}

function Call($method, $path, $bodyObj, $token, $rawBody) {
    $headers = @{}
    if ($token) { $headers["Authorization"] = "Bearer $token" }
    $body = $rawBody
    if ($null -eq $body -and $null -ne $bodyObj) { $body = $bodyObj | ConvertTo-Json -Depth 6 }
    try {
        $resp = Invoke-WebRequest -Method $method -Uri ($Base + $path) -Headers $headers `
            -ContentType "application/json" -Body $body -UseBasicParsing -TimeoutSec 30
        return @{ status = [int]$resp.StatusCode; body = $resp.Content }
    } catch {
        $status = 0
        $content = ""
        if ($_.Exception.Response) {
            $status = [int]$_.Exception.Response.StatusCode
            try {
                $stream = $_.Exception.Response.GetResponseStream()
                $reader = New-Object System.IO.StreamReader($stream)
                $content = $reader.ReadToEnd()
            } catch { $content = "" }
        }
        return @{ status = $status; body = $content }
    }
}

function HmacHex([string]$data, [string]$key) {
    $hmac = New-Object System.Security.Cryptography.HMACSHA256
    $hmac.Key = [Text.Encoding]::UTF8.GetBytes($key)
    $hash = $hmac.ComputeHash([Text.Encoding]::UTF8.GetBytes($data))
    return -join ($hash | ForEach-Object { $_.ToString("x2") })
}

Write-Host "`n=== Phase 1 E2E: $Base ===`n"

# 1. Health
$r = Call "GET" "/actuator/health" $null $null
$healthBody = if ($r.body -is [byte[]]) { [Text.Encoding]::UTF8.GetString($r.body) } else { [string]$r.body }
Assert "health is UP" ($r.status -eq 200 -and $healthBody -match '"UP"') "status=$($r.status) body=$healthBody"

# 2. Register compliance officer with a company
$runId = [guid]::NewGuid().ToString('N').Substring(0,8)
$email = "officer+$runId@acme.test"
$companyName = "Acme Fintech $runId Ltd"
$r = Call "POST" "/api/auth/register" @{
    email = $email; password = "Passw0rd!23"; fullName = "Compliance Officer"
    companyName = $companyName; industry = "Banking & NBFC"
} $null
Assert "register officer + company" ($r.status -eq 201) "status=$($r.status) body=$($r.body)"
$officerToken = ($r.body | ConvertFrom-Json).token
$companyId = ($r.body | ConvertFrom-Json).user.companyId
Assert "officer received JWT" ([bool]$officerToken) "token missing"

# 3. Duplicate registration rejected
$r = Call "POST" "/api/auth/register" @{
    email = $email; password = "Passw0rd!23"; fullName = "Duplicate"
} $null
Assert "duplicate email rejected (409)" ($r.status -eq 409) "status=$($r.status)"

# 4. Admin login
$r = Call "POST" "/api/auth/login" @{ email = $AdminEmail; password = $AdminPassword } $null
Assert "admin login" ($r.status -eq 200) "status=$($r.status) body=$($r.body)"
$adminToken = ($r.body | ConvertFrom-Json).token

# 5. Wrong password rejected
$r = Call "POST" "/api/auth/login" @{ email = $AdminEmail; password = "wrong-password" } $null
Assert "bad password rejected (401)" ($r.status -eq 401) "status=$($r.status)"

# 6. /api/me
$r = Call "GET" "/api/me" $null $officerToken
Assert "officer /api/me" ($r.status -eq 200 -and ($r.body | ConvertFrom-Json).email -eq $email) "status=$($r.status)"

# 7. Unauthenticated access blocked
$r = Call "GET" "/api/me" $null $null
Assert "unauthenticated blocked (401)" ($r.status -eq 401) "status=$($r.status)"

# 8. Seeded sources visible
$r = Call "GET" "/api/sources" $null $officerToken
$sources = $r.body | ConvertFrom-Json
Assert "sources seeded (MCA/RBI/SEBI)" ($r.status -eq 200 -and $sources.Count -ge 3) "status=$($r.status) count=$($sources.Count)"

# 9. Officer cannot create sources (ADMIN only)
$r = Call "POST" "/api/sources" @{ code = "X"; name = "Nope" } $officerToken
Assert "officer blocked from creating source (403)" ($r.status -eq 403) "status=$($r.status)"

# 10. Officer cannot read audit log (ADMIN only)
$r = Call "GET" "/api/audit" $null $officerToken
Assert "officer blocked from audit (403)" ($r.status -eq 403) "status=$($r.status)"

# 11. Admin creates a source
# Idempotency: both the code and the company name above derive from $runId so a
# re-run can never collide with uk_sources_code / uk_companies_name (QA fix).
$sourceCode = "ED" + $runId.Substring(0, 8).ToUpper()
$r = Call "POST" "/api/sources" @{
    code = $sourceCode; name = "Example Dept of Corporate Affairs"
    agency = "MCA"; baseUrl = "https://example.gov.in"
    watchUrl = "https://example.gov.in/notices"; active = $true
} $adminToken
Assert "admin creates source" ($r.status -eq 201) "status=$($r.status) body=$($r.body)"

# 12. Webhook without signature -> 401
$regUrl = "https://www.rbi.org.in/notifications/2026/circ-$runId.html"
$payload = '{"url":"' + $regUrl + '","title":"RBI Notification on Digital Lending","source_code":"RBI","content":"<html><body>Version 1 of the circular</body></html>"}'
$r = Call "POST" "/api/webhooks/changedetection" $null $null $payload
Assert "webhook without signature rejected (401)" ($r.status -eq 401) "status=$($r.status)"

# 13. Webhook with bad signature -> 401
$headers = @{ "X-Webhook-Signature" = "sha256=" + ("0" * 64) }
try {
    Invoke-WebRequest -Method POST -Uri ($Base + "/api/webhooks/changedetection") -Headers $headers `
        -ContentType "application/json" -Body $payload -UseBasicParsing -TimeoutSec 30 | Out-Null
    $badStatus = 202
} catch { $badStatus = [int]$_.Exception.Response.StatusCode }
Assert "webhook bad signature rejected (401)" ($badStatus -eq 401) "status=$($badStatus)"

# 14. Webhook with valid HMAC -> 202, regulation + version created
$signature = HmacHex $payload $webhookSecret
$headers = @{ "X-Webhook-Signature" = "sha256=$signature" }
$resp1 = $null
try {
    $w = Invoke-WebRequest -Method POST -Uri ($Base + "/api/webhooks/changedetection") -Headers $headers `
        -ContentType "application/json" -Body $payload -UseBasicParsing -TimeoutSec 30
    $resp1 = @{ status = [int]$w.StatusCode; body = $w.Content }
} catch { $resp1 = @{ status = [int]$_.Exception.Response.StatusCode; body = "" } }
Assert "signed webhook accepted (202)" ($resp1.status -eq 202) "status=$($resp1.status)"
$ack1 = $resp1.body | ConvertFrom-Json
Assert "regulation created from webhook" ([bool]$ack1.regulationId) "ack=$($resp1.body)"
Assert "first version created" ([bool]$ack1.newVersionId) "ack=$($resp1.body)"

# 15. Same URL with changed content -> second version, old version recorded
$payload2 = '{"url":"' + $regUrl + '","title":"RBI Notification on Digital Lending (Amended)","source_code":"RBI","content":"<html><body>Version 2 - amended circular text</body></html>"}'
$signature2 = HmacHex $payload2 $webhookSecret
try {
    $w = Invoke-WebRequest -Method POST -Uri ($Base + "/api/webhooks/changedetection") `
        -Headers @{ "X-Webhook-Signature" = "sha256=$signature2" } -ContentType "application/json" `
        -Body $payload2 -UseBasicParsing -TimeoutSec 30
    $resp2 = @{ status = [int]$w.StatusCode; body = $w.Content }
} catch { $resp2 = @{ status = [int]$_.Exception.Response.StatusCode; body = "" } }
$ack2 = $resp2.body | ConvertFrom-Json
Assert "second webhook accepted (202)" ($resp2.status -eq 202) "status=$($resp2.status)"
Assert "old version linked" ($ack2.regulationId -eq $ack1.regulationId -and [bool]$ack2.newVersionId) "ack=$($resp2.body)"

# 16. Regulations + versions
$r = Call "GET" "/api/regulations?source=RBI" $null $officerToken
$regs = $r.body | ConvertFrom-Json
$reg = $regs | Where-Object { $_.id -eq $ack1.regulationId } | Select-Object -First 1
Assert "regulation listed with versionCount=2" ($r.status -eq 200 -and $reg.versionCount -eq 2) "status=$($r.status) reg=$($reg | ConvertTo-Json -Compress)"
$r = Call "GET" ("/api/regulations/" + $ack1.regulationId + "/versions") $null $officerToken
$versions = $r.body | ConvertFrom-Json
Assert "version history has 2 entries" ($r.status -eq 200 -and $versions.Count -eq 2) "status=$($r.status) count=$($versions.Count)"
$r = Call "GET" ("/api/regulations/" + $ack1.regulationId + "/versions/" + $ack2.newVersionId) $null $officerToken
$vDetail = $r.body | ConvertFrom-Json
Assert "new version content retrievable" ($r.status -eq 200 -and $vDetail.content -match "amended") "status=$($r.status)"

# 17. Change events listed
$r = Call "GET" "/api/events" $null $officerToken
$events = $r.body | ConvertFrom-Json
Assert "two change events stored" ($r.status -eq 200 -and $events.Count -ge 2) "status=$($r.status) count=$($events.Count)"

# 18. Admin creates an analysis alert for the officer's company
$r = Call "POST" "/api/alerts" @{
    companyId = $companyId; changeEventId = $ack2.eventId
    relevance = "HIGH"
    summary = "Amended RBI circular on digital lending - changes KYC obligations."
    affectedAreas = "Digital lending, KYC, Fair practices code"
    effectiveDate = "2026-11-01"
    requiredAction = "Update digital lending policy and customer disclosures by 2026-11-01."
    emailRecipients = "compliance@acme.test"
} $adminToken
Assert "alert created (201)" ($r.status -eq 201) "status=$($r.status) body=$($r.body)"
$alertId = ($r.body | ConvertFrom-Json).id

# 19. Officer sees only own-company alerts
$r = Call "GET" "/api/alerts" $null $officerToken
$alerts = $r.body | ConvertFrom-Json
$own = @($alerts | Where-Object { $_.companyId -eq $companyId })
Assert "officer sees own-company alert with regulation context" ($r.status -eq 200 -and $own.Count -ge 1 -and $own[0].regulationTitle) "status=$($r.status) count=$($own.Count)"

# 20. Officer updates alert status
$r = Call "PATCH" ("/api/alerts/" + $alertId + "/status") @{ status = "READ" } $officerToken
Assert "officer marks alert READ" ($r.status -eq 200 -and ($r.body | ConvertFrom-Json).status -eq "READ") "status=$($r.status)"

# 21. Company profile upsert
$r = Call "PUT" ("/api/companies/" + $companyId + "/profile") @{
    industrySectors = "NBFC, Digital payments, Corporate lending"
    regulatoryBodies = "RBI,MCA,SEBI"
    jurisdictions = "India"
    complianceContactEmail = $email
    notificationEnabled = $true
    notes = "Primary focus: digital lending regulations."
} $officerToken
Assert "officer updates own company profile" ($r.status -eq 200) "status=$($r.status) body=$($r.body)"

# 22. Officer cannot read another company
$r = Call "GET" "/api/companies/999999" $null $officerToken
Assert "missing company -> 404" ($r.status -eq 404) "status=$($r.status)"

# 23. Admin audit trail contains key actions
$r = Call "GET" "/api/audit" $null $adminToken
$audit = $r.body | ConvertFrom-Json
$actions = @($audit | ForEach-Object { $_.action })
Assert "audit has REGISTER" ($actions -contains "REGISTER") "actions=$($actions -join ',')"
Assert "audit has WEBHOOK_RECEIVED" ($actions -contains "WEBHOOK_RECEIVED") "actions=$($actions -join ',')"
Assert "audit has ALERT_CREATED" ($actions -contains "ALERT_CREATED") "actions=$($actions -join ',')"
Assert "audit has LOGIN" ($actions -contains "LOGIN") "actions=$($actions -join ',')"

# 24. Audit filter works
$r = Call "GET" "/api/audit?action=LOGIN_FAILED" $null $adminToken
$filtered = $r.body | ConvertFrom-Json
Assert "audit filter LOGIN_FAILED shows bad attempt" (@($filtered | Where-Object { $_.action -eq "LOGIN_FAILED" }).Count -ge 1) "count=$($filtered.Count)"

Write-Host "`n=== Result: $script:pass passed, $script:fail failed ===`n"
if ($script:fail -gt 0) { exit 1 } else { exit 0 }
