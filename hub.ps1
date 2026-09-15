<#
Task runner for the PheedLoop Print Hub.

    .\hub.ps1              list the tasks
    .\hub.ps1 <task>       run one

Windows PowerShell 5.1. Never activates the venv: it calls the interpreter by
absolute path, because the execution policy blocks Activate.ps1 on this box.

Three rules this script exists to enforce, all of them learned the hard way
and written up in CLAUDE.MD:

  * The service reads its environment once at start, so a settings change
    needs `restart`, not a new request.
  * A service running without HUB_DEVMODE prints silently wrong-sized cards
    (Verified 18). `status` puts scale_pinned first for that reason.
  * A printer reports faults only while a job is in flight (Verified 29), so
    `status` shows the last known queue state and never claims "ready".
#>

[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [string]$Task = "help",

    [switch]$Dry,          # demo: render and measure, spool nothing
    [switch]$Follow,       # logs: keep tailing
    [string]$Queue,        # capture: which queue
    [string]$Name,         # capture: blob filename
    [string]$Pdf,          # print: file to send
    [int]$Tail = 40
)

$ErrorActionPreference = "Stop"

# --- where everything lives ----------------------------------------------
$ROOT      = $PSScriptRoot
$VENV      = Join-Path $ROOT ".venv"
$PY        = Join-Path $VENV "Scripts\python.exe"
$PIP       = Join-Path $VENV "Scripts\pip.exe"
$WAITRESS  = Join-Path $VENV "Scripts\waitress-serve.exe"
$NSSM      = Join-Path $ROOT "nssm.exe"
$SERVICE   = "PheedLoopHub"
$PORT      = 8080
$BASE      = "http://127.0.0.1:$PORT"
$LOG       = Join-Path $ROOT "service.log"
$FWRULE    = "PheedLoop Hub 8080"
$CONSOLE   = Join-Path $ROOT "console"
$STATIC    = Join-Path $ROOT "printhub\static"

# Spooler status bits. Only truthful while a job is in flight (Verified 29).
$STATUS_BITS = @{
    2       = "ERROR (generic - this driver does not attribute its faults)"
    8       = "PAPER_JAM"
    16      = "PAPER_OUT / out of cards"
    262144  = "NO_TONER / ribbon out"
    4194304 = "DOOR_OPEN / cover open"
}

# --- helpers --------------------------------------------------------------
function Write-Head($text) { Write-Host ""; Write-Host $text -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "  $text" -ForegroundColor Green }
function Write-Warn($text) { Write-Host "  $text" -ForegroundColor Yellow }
function Write-Bad($text)  { Write-Host "  $text" -ForegroundColor Red }
function Write-Item($k, $v) { Write-Host ("  {0,-16} {1}" -f $k, $v) }

function Test-Admin {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    $principal = New-Object Security.Principal.WindowsPrincipal $id
    return $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Assert-Admin($what) {
    if (-not (Test-Admin)) {
        Write-Bad "$what needs an elevated shell."
        Write-Host "  Re-run from an admin PowerShell:  .\hub.ps1 $Task"
        exit 1
    }
}

function Get-Service-State {
    $svc = Get-CimInstance Win32_Service -Filter "Name='$SERVICE'" -ErrorAction SilentlyContinue
    return $svc
}

function Get-Hub-Pid {
    # The pid of the process actually serving, which is nssm's child. Used to
    # prove a restart recycled it: nssm reporting success is not evidence.
    $svc = Get-Service-State
    if (-not $svc -or $svc.ProcessId -eq 0) { return $null }
    $child = Get-CimInstance Win32_Process -Filter "ParentProcessId=$($svc.ProcessId)" `
                -ErrorAction SilentlyContinue |
             Where-Object { $_.Name -eq "waitress-serve.exe" } | Select-Object -First 1
    if ($child) { return $child.ProcessId }
    return $svc.ProcessId
}

function Invoke-Nssm($action) {
    # nssm writes failures to stderr and they are easy to swallow. Never
    # pipe this to Out-Null: a silently failed restart leaves the OLD code
    # serving, answering /health correctly the whole time.
    # nssm writes UTF-16, which arrives here as text interleaved with NULs.
    $out = ((& $NSSM $action $SERVICE 2>&1 | Out-String) -replace "`0", "").Trim()
    $ok = ($LASTEXITCODE -eq 0)
    if (-not $ok) {
        Write-Bad "nssm $action failed (exit $LASTEXITCODE)"
        if ($out) { Write-Host "  $out" }
        if (-not (Test-Admin)) {
            Write-Warn "This shell is not elevated. Service control needs admin."
        }
    }
    return $ok
}

function Invoke-Hub($path, $method = "GET") {
    # Returns $null when the hub is not answering, rather than throwing.
    try {
        return Invoke-RestMethod -Uri "$BASE$path" -Method $method -TimeoutSec 8
    } catch {
        return $null
    }
}

function Assert-Venv {
    if (-not (Test-Path $PY)) {
        Write-Bad "No venv at $VENV"
        Write-Host "  Run:  .\hub.ps1 install"
        exit 1
    }
}

function Get-Console-Staleness {
    # A built bundle can disagree with its source, and nothing at runtime
    # would say so - the same shape of failure as a stale service process
    # answering /health perfectly. Two sources that can disagree, so compare
    # them (Verified 57).
    if (-not (Test-Path $STATIC)) { return "unbuilt" }
    $src = @(Get-ChildItem (Join-Path $CONSOLE "src") -Recurse -File -ErrorAction SilentlyContinue) +
           @(Get-Item (Join-Path $CONSOLE "index.html") -ErrorAction SilentlyContinue)
    if ($src.Count -eq 0) { return "nosource" }
    $newestSrc = ($src | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
    $built = @(Get-ChildItem $STATIC -Recurse -File -ErrorAction SilentlyContinue)
    if ($built.Count -eq 0) { return "unbuilt" }
    $newestBuilt = ($built | Sort-Object LastWriteTime -Descending | Select-Object -First 1).LastWriteTime
    if ($newestSrc -gt $newestBuilt) { return "stale" }
    return "current"
}

function Assert-Node {
    try { & node --version | Out-Null } catch {
        Write-Bad "node is not on PATH. The console needs it (dev machine only)."
        Write-Host "  winget install --id OpenJS.NodeJS.LTS --source winget"
        exit 1
    }
}

function Show-StatusBits($code) {
    if ($null -eq $code) { return }
    if ($code -eq 0) {
        Write-Item "queue status" "0  (no fault reported - NOT a readiness signal)"
        return
    }
    $named = @()
    foreach ($bit in $STATUS_BITS.Keys) {
        if ($code -band $bit) { $named += $STATUS_BITS[$bit] }
    }
    if ($named.Count -eq 0) { $named = @("unrecognised bitfield") }
    Write-Item "queue status" "$code  $($named -join ', ')"
}

# --- tasks ----------------------------------------------------------------

function Task-Help {
    Write-Host ""
    Write-Host "PheedLoop Print Hub" -ForegroundColor Cyan
    Write-Host "  .\hub.ps1 <task>"
    Write-Host ""
    Write-Host "  Setup" -ForegroundColor Cyan
    Write-Host "    init               install, create dirs, report what is still missing"
    Write-Host "    install            create the venv and install requirements.txt"
    Write-Host "    install-service    register PheedLoopHub, env vars, firewall   [admin]"
    Write-Host "    uninstall-service  stop and remove it, drop the firewall rule  [admin]"
    Write-Host ""
    Write-Host "  Run" -ForegroundColor Cyan
    Write-Host "    start / stop / restart    the service. restart after ANY code change"
    Write-Host "    dev                foreground on port $PORT, Ctrl-C to quit"
    Write-Host "    status             service, environment, health, queue"
    Write-Host "    logs [-Tail N] [-Follow]"
    Write-Host ""
    Write-Host "  Console" -ForegroundColor Cyan
    Write-Host "    console            Vite dev server on :5173, /api proxied. No rebuilds"
    Write-Host "    build              build into printhub/static, which the hub serves"
    Write-Host ""
    Write-Host "  Print" -ForegroundColor Cyan
    Write-Host "    demo [-Dry]        every printer in printers.json at once"
    Write-Host "    print -Pdf <file>  send one PDF to HUB_QUEUE"
    Write-Host "    printers           queues this box can see"
    Write-Host ""
    Write-Host "  Bench" -ForegroundColor Cyan
    Write-Host "    bench              one objective row per queue"
    Write-Host "    cards              regenerate the fleet's calibration cards"
    Write-Host "    capture -Queue <q> -Name <file>    save a DEVMODE blob"
    Write-Host "    blobs              list captured blobs"
    Write-Host "    clean              spool, out.pdf, __pycache__. Keeps blobs"
    Write-Host ""
}

function Task-Install {
    Write-Head "Installing"
    if (-not (Test-Path $PY)) {
        Write-Host "  creating venv at $VENV"
        & py -3.12 -m venv $VENV
        if ($LASTEXITCODE -ne 0) {
            Write-Bad "venv creation failed. Is Python 3.12 installed machine-wide?"
            exit 1
        }
    } else {
        Write-Ok "venv already present"
    }

    Write-Host "  installing requirements.txt"
    & $PY -m pip install --disable-pip-version-check -q -r (Join-Path $ROOT "requirements.txt")
    if ($LASTEXITCODE -ne 0) { Write-Bad "pip install failed"; exit 1 }
    Write-Ok "dependencies installed"

    # pywin32 needs a post-install step pip does not run. Without it
    # `import win32print` fails and nothing else here works.
    & $PY -c "import win32print" 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Ok "win32print imports"
    } else {
        Write-Warn "win32print does not import - running pywin32_postinstall"
        Assert-Admin "pywin32_postinstall"
        & $PY (Join-Path $VENV "Scripts\pywin32_postinstall.py") -install
        & $PY -c "import win32print" 2>$null
        if ($LASTEXITCODE -eq 0) { Write-Ok "win32print imports now" }
        else { Write-Bad "still failing. See CLAUDE.MD." ; exit 1 }
    }
}

function Task-Init {
    Task-Install

    Write-Head "Directories"
    foreach ($d in @("spool", "devmode", "cards")) {
        $p = Join-Path $ROOT $d
        if (-not (Test-Path $p)) { New-Item -ItemType Directory $p | Out-Null; Write-Ok "created $d\" }
        else { Write-Ok "$d\ present" }
    }

    Write-Head "What this box still needs"
    $missing = 0

    $q = [Environment]::GetEnvironmentVariable("HUB_QUEUE", "Machine")
    if ($q) { Write-Ok "HUB_QUEUE = $q" }
    else { Write-Warn "HUB_QUEUE not set (machine scope). install-service sets it"; $missing++ }

    $d = [Environment]::GetEnvironmentVariable("HUB_DEVMODE", "Machine")
    if ($d -and (Test-Path $d)) { Write-Ok "HUB_DEVMODE = $d" }
    elseif ($d) { Write-Bad "HUB_DEVMODE points at a missing file: $d"; $missing++ }
    else { Write-Warn "HUB_DEVMODE not set - jobs would print unpinned (Verified 18)"; $missing++ }

    $blobs = @(Get-ChildItem (Join-Path $ROOT "devmode") -Filter *.devmode -ErrorAction SilentlyContinue)
    if ($blobs.Count -gt 0) { Write-Ok "$($blobs.Count) captured blob(s)" }
    else {
        Write-Warn "no DEVMODE blobs. They are machine- and queue-specific, so a"
        Write-Host "                   fresh box must capture its own after configuring each"
        Write-Host "                   driver by hand:  .\hub.ps1 capture -Queue <q> -Name <f>"
        $missing++
    }

    $svc = Get-Service-State
    if ($svc) { Write-Ok "service $SERVICE is $($svc.State)" }
    else { Write-Warn "service not registered. Run: .\hub.ps1 install-service  [admin]"; $missing++ }

    Write-Host ""
    if ($missing -eq 0) { Write-Ok "Ready. .\hub.ps1 status" }
    else { Write-Warn "$missing item(s) above still need attention." }
}

function Task-InstallService {
    Assert-Admin "Registering the service"
    Assert-Venv
    if (-not (Test-Path $NSSM)) { Write-Bad "nssm.exe not found at $NSSM"; exit 1 }

    # Order matters: the service reads its environment once at start, and one
    # that starts without HUB_DEVMODE prints silently wrong-sized cards.
    Write-Head "Environment (machine scope)"
    $q = [Environment]::GetEnvironmentVariable("HUB_QUEUE", "Machine")
    if (-not $q) {
        Write-Bad "HUB_QUEUE is not set, and the hub refuses to print without it."
        Write-Host '  Set it first, then re-run:'
        Write-Host '    [Environment]::SetEnvironmentVariable("HUB_QUEUE", "HUB-CARD", "Machine")'
        exit 1
    }
    Write-Ok "HUB_QUEUE = $q"

    $d = [Environment]::GetEnvironmentVariable("HUB_DEVMODE", "Machine")
    if (-not $d) {
        Write-Warn "HUB_DEVMODE is not set. The service will inherit the queue default,"
        Write-Host "                   which has silently produced a 5% oversized card, an uncut"
        Write-Host "                   badge, and a page cropped to 306 of 696 rows. Set it:"
        Write-Host '    [Environment]::SetEnvironmentVariable("HUB_DEVMODE", "C:\hub\devmode\<blob>", "Machine")'
    } else { Write-Ok "HUB_DEVMODE = $d" }

    [Environment]::SetEnvironmentVariable("HUB_DIR", $ROOT, "Machine")
    Write-Ok "HUB_DIR = $ROOT"

    Write-Head "Firewall"
    $existing = Get-NetFirewallRule -DisplayName $FWRULE -ErrorAction SilentlyContinue
    if ($existing) { Write-Ok "rule already present" }
    else {
        New-NetFirewallRule -DisplayName $FWRULE -Direction Inbound -Protocol TCP `
            -LocalPort $PORT -Action Allow -Profile Any | Out-Null
        Write-Ok "inbound TCP $PORT allowed"
    }

    Write-Head "Service"
    $svc = Get-Service-State
    if ($svc) {
        Write-Ok "$SERVICE already registered, reconfiguring"
    } else {
        & $NSSM install $SERVICE $WAITRESS "--listen=0.0.0.0:$PORT" "hub:app" | Out-Null
        Write-Ok "registered"
    }
    & $NSSM set $SERVICE AppDirectory $ROOT | Out-Null
    # nssm prints "Reset parameter ObjectName to its default" here, which looks
    # like a failure and is not: LocalSystem IS its default. Confirmed below.
    & $NSSM set $SERVICE ObjectName LocalSystem | Out-Null
    & $NSSM set $SERVICE Start SERVICE_AUTO_START | Out-Null
    # Session 0 has no console. Without these a startup crash is invisible.
    & $NSSM set $SERVICE AppStdout $LOG | Out-Null
    & $NSSM set $SERVICE AppStderr $LOG | Out-Null
    & $NSSM set $SERVICE AppRotateFiles 1 | Out-Null
    & $NSSM start $SERVICE | Out-Null

    Start-Sleep -Seconds 3
    $svc = Get-Service-State
    if ($svc) {
        Write-Ok "state $($svc.State), runs as $($svc.StartName), start $($svc.StartMode)"
    }
    Task-Status
}

function Task-UninstallService {
    Assert-Admin "Removing the service"
    $svc = Get-Service-State
    if ($svc) {
        & $NSSM stop $SERVICE | Out-Null
        & $NSSM remove $SERVICE confirm | Out-Null
        Write-Ok "service removed"
    } else { Write-Warn "service was not registered" }

    $existing = Get-NetFirewallRule -DisplayName $FWRULE -ErrorAction SilentlyContinue
    if ($existing) {
        Remove-NetFirewallRule -DisplayName $FWRULE
        Write-Ok "firewall rule removed"
    }
    Write-Warn "Machine env vars HUB_* left in place. Remove by hand if you mean to."
}

function Task-Start {
    $svc = Get-Service-State
    if (-not $svc) { Write-Bad "$SERVICE is not registered. .\hub.ps1 install-service"; exit 1 }
    if (-not (Invoke-Nssm "start")) { exit 1 }
    Start-Sleep -Seconds 2
    Task-Status
}

function Task-Stop {
    $svc = Get-Service-State
    if (-not $svc) { Write-Warn "$SERVICE is not registered"; return }
    if (-not (Invoke-Nssm "stop")) { exit 1 }
    Start-Sleep -Seconds 1
    $svc = Get-Service-State
    Write-Ok "$SERVICE is $($svc.State)"
}

function Task-Restart {
    $svc = Get-Service-State
    if (-not $svc) { Write-Bad "$SERVICE is not registered. .\hub.ps1 install-service"; exit 1 }

    $before = Get-Hub-Pid

    # Deliberately not `nssm restart`. Its stop has a short fixed timeout, and
    # when waitress takes longer than that it reports SERVICE_STOP_PENDING and
    # gives up - having already stopped the service and never started it
    # again. Stop, wait for Stopped ourselves, then start.
    if (-not (Invoke-Nssm "stop")) {
        Write-Warn "stop reported a problem; checking whether it stopped anyway"
    }
    $waited = 0
    while ($waited -lt 30) {
        $svc = Get-Service-State
        if ($svc.State -eq "Stopped") { break }
        Start-Sleep -Milliseconds 500
        $waited += 0.5
    }
    $svc = Get-Service-State
    if ($svc.State -ne "Stopped") {
        Write-Bad "still $($svc.State) after 30 s. Not starting on top of it."
        exit 1
    }
    if (-not (Invoke-Nssm "start")) { exit 1 }
    Start-Sleep -Seconds 3
    $after = Get-Hub-Pid

    # Two independent sources: nssm's exit code, and whether the serving
    # process actually changed. A check is only worth having if the two can
    # disagree (Verified 57) - and here they do, because a stale process
    # keeps answering /health correctly with the old code.
    if ($before -and $after -and $before -eq $after) {
        Write-Bad "nssm reported success but the serving process did not recycle."
        Write-Host "  pid $after is still the old one. It is STILL RUNNING THE OLD CODE."
        Write-Host "  /health will answer correctly and tell you nothing. Try:"
        Write-Host "    .\hub.ps1 stop     (elevated), then .\hub.ps1 start"
        exit 1
    }
    if ($before -and $after) { Write-Ok "recycled: pid $before -> $after" }
    elseif ($after) { Write-Ok "serving as pid $after" }
    Task-Status
}

function Task-Status {
    Write-Head "Service"
    $svc = Get-Service-State
    if ($svc) {
        Write-Item "state" $svc.State
        Write-Item "runs as" $svc.StartName
        Write-Item "start mode" $svc.StartMode
        # Serving-process age, because a stale instance answers /health
        # perfectly while running whatever code it loaded at start. This is
        # the only field here that can tell you the code on disk is not the
        # code that is running.
        $hubPid = Get-Hub-Pid
        if ($hubPid) {
            $proc = Get-Process -Id $hubPid -ErrorAction SilentlyContinue
            if ($proc) {
                $age = (Get-Date) - $proc.StartTime
                $when = $proc.StartTime.ToString("yyyy-MM-dd HH:mm")
                Write-Item "serving pid" "$hubPid  since $when"
                if ($age.TotalHours -ge 1) {
                    Write-Warn ("up {0:N1} h - restart if you have changed code since" -f $age.TotalHours)
                } else {
                    Write-Item "uptime" ("{0:N1} min" -f $age.TotalMinutes)
                }
            }
        }
    } else { Write-Warn "not registered" }

    Write-Head "Environment (machine scope, read once at service start)"
    foreach ($v in @("HUB_QUEUE", "HUB_DEVMODE", "HUB_DIR")) {
        $val = [Environment]::GetEnvironmentVariable($v, "Machine")
        if ($val) { Write-Item $v $val } else { Write-Item $v "(not set)" }
    }

    Write-Head "Hub $BASE"
    $h = Invoke-Hub "/health"
    if ($null -eq $h) {
        Write-Bad "not answering. Is it running?  .\hub.ps1 start"
        return
    }
    # scale_pinned first: an unpinned hub prints silently wrong-sized cards
    # and every other number it reports still looks correct (Verified 18).
    if ($h.scale_pinned) { Write-Ok "scale_pinned  TRUE  ($($h.devmode_bytes) bytes, sha $($h.devmode_sha256))" }
    else { Write-Bad "scale_pinned  FALSE - jobs inherit the queue default. See Verified 18." }
    Write-Item "queue" $h.queue
    Write-Item "renderer" $h.renderer
    Write-Item "jobs seen" $h.jobs_seen
    if ($h.fleet) { Write-Item "fleet" ($h.fleet -join ", ") }
    if ($h.devmode_error) { Write-Bad "devmode_error: $($h.devmode_error)" }
    if ($h.fleet_error) { Write-Warn "fleet_error: $($h.fleet_error)" }

    Write-Head "Console"
    switch (Get-Console-Staleness) {
        "current"  { Write-Ok "built and current, served at $BASE/" }
        "stale"    { Write-Bad "SOURCE IS NEWER THAN THE BUILD - run .\hub.ps1 build"
                     Write-Host "  The hub is serving an older console than console/src." }
        "unbuilt"  { Write-Warn "not built. Run .\hub.ps1 build" }
        "nosource" { Write-Warn "no console source found at console/src" }
    }

    $q = Invoke-Hub "/queue"
    if ($null -ne $q) {
        Write-Head "Queue"
        Write-Item "name" $q.name
        Write-Item "driver" $q.driver
        Write-Item "port" $q.port
        Write-Item "jobs queued" $q.jobs_queued
        Show-StatusBits $q.status
        Write-Host "  Faults appear only while a job is in flight (Verified 29)." -ForegroundColor DarkGray
        Write-Host "  There is no truthful pre-flight 'ready' signal." -ForegroundColor DarkGray
    }
}

function Task-Console {
    Assert-Node
    $svc = Get-Service-State
    if (-not $svc -or $svc.State -ne "Running") {
        Write-Warn "The hub is not running, so /api will not answer. .\hub.ps1 start"
    }
    Write-Head "Vite dev server on :5173, proxying /api to :8080"
    Write-Host "  Edits appear immediately. Nothing is rebuilt by hand."
    Write-Host "  From a phone, use this machine's address, not localhost."
    Push-Location $CONSOLE
    try { & npm run dev } finally { Pop-Location }
}

function Task-Build {
    Assert-Node
    Write-Head "Building the console into printhub/static"
    Push-Location $CONSOLE
    try {
        if (-not (Test-Path (Join-Path $CONSOLE "node_modules"))) {
            Write-Host "  node_modules missing, installing first"
            & npm install
            if ($LASTEXITCODE -ne 0) { Write-Bad "npm install failed"; exit 1 }
        }
        & npm run build
        if ($LASTEXITCODE -ne 0) { Write-Bad "build failed"; exit 1 }
    } finally { Pop-Location }
    Write-Ok "built. The hub serves it at / with no restart needed."
}

function Task-Dev {
    Assert-Venv
    $svc = Get-Service-State
    if ($svc -and $svc.State -eq "Running") {
        Write-Bad "$SERVICE is running and already holds port $PORT."
        Write-Host "  A stale instance answers for the one you just started, with the old code."
        Write-Host "  Run:  .\hub.ps1 stop"
        exit 1
    }
    Write-Head "Foreground on port $PORT. Ctrl-C to quit."
    Push-Location $ROOT
    try { & $PY (Join-Path $ROOT "hub.py") } finally { Pop-Location }
}

function Task-Logs {
    if (-not (Test-Path $LOG)) { Write-Warn "no log at $LOG"; return }
    if ($Follow) { Get-Content $LOG -Tail $Tail -Wait }
    else { Get-Content $LOG -Tail $Tail }
}

function Task-Demo {
    $h = Invoke-Hub "/health"
    if ($null -eq $h) { Write-Bad "hub is not answering. .\hub.ps1 start"; exit 1 }

    if ($Dry) { $url = "/demo?dry_run=1" } else { $url = "/demo" }
    if (-not $Dry) { Write-Warn "This spends real media on every printer. -Dry rehearses for free." }

    Write-Head "Fan-out"
    $r = Invoke-Hub $url "POST"
    if ($null -eq $r) { Write-Bad "the demo request failed"; exit 1 }

    Write-Item "state" $r.state
    Write-Item "sent" "$($r.sent) of $($r.of)"
    Write-Item "wall" "$($r.wall_ms) ms   (serial would be $($r.serial_ms) ms)"
    Write-Host ""
    foreach ($p in $r.printers) {
        $mark = "ok "
        if ($p.state -ne "sent") { $mark = "FAIL" }
        Write-Host ("  {0} {1,-9} {2,-30} {3,7} ms  clipped={4}" -f `
            $mark, $p.name, $p.queue, $p.took_ms, $p.clipped)
        if ($p.error) { Write-Bad "       $($p.error)" }
        # clipped is the one check in this spike that ever caught a silent
        # failure, because it compares two independent sources (Verified 57).
        if ($p.clipped) { Write-Bad "       CLIPPED - the page does not fit the imageable area" }
    }
}

function Task-Print {
    if (-not $Pdf) { Write-Bad "usage: .\hub.ps1 print -Pdf <file.pdf>"; exit 1 }
    if (-not (Test-Path $Pdf)) { Write-Bad "no such file: $Pdf"; exit 1 }
    $h = Invoke-Hub "/health"
    if ($null -eq $h) { Write-Bad "hub is not answering. .\hub.ps1 start"; exit 1 }
    if (-not $h.scale_pinned) { Write-Warn "scale_pinned is FALSE - this may print the wrong size." }

    # curl.exe, not curl: in PowerShell bare curl is Invoke-WebRequest and
    # rejects -F.
    Write-Head "POST $BASE/print  ->  $($h.queue)"
    & curl.exe -s -F "pdf=@$Pdf" "$BASE/print"
    Write-Host ""
    Write-Host '  "sent" means it left the spooler, never that a card exists.' -ForegroundColor DarkGray
}

function Task-Printers {
    $r = Invoke-Hub "/printers"
    if ($null -eq $r) { Write-Bad "hub is not answering. .\hub.ps1 start"; exit 1 }
    Write-Head "Queues this process can see"
    foreach ($p in $r.printers) {
        if ($p -eq $r.queue) { Write-Ok "$p   <- HUB_QUEUE" } else { Write-Host "  $p" }
    }
    if (-not $r.queue_visible -and $r.queue) {
        Write-Bad "HUB_QUEUE '$($r.queue)' is NOT visible to this process."
    }
    Write-Host "  An enumerated queue is not necessarily a usable one." -ForegroundColor DarkGray
}

function Task-Bench {
    Assert-Venv
    Push-Location $ROOT
    try { & $PY (Join-Path $ROOT "tools\benchmark.py") } finally { Pop-Location }
}

function Task-Cards {
    Assert-Venv
    Write-Head "Regenerating the fleet's calibration cards"
    # Page size comes from the filename; the caliper targets do NOT, so they
    # are recorded in printers.json. Letting the generator default them once
    # silently re-authored the Epson card with a 50 mm vertical target in
    # place of its 250 mm one, and nothing about the card looks wrong
    # afterwards. Refuse rather than guess.
    $cfg = Get-Content (Join-Path $ROOT "printers.json") -Raw | ConvertFrom-Json
    Push-Location $ROOT
    try {
        foreach ($p in $cfg.printers) {
            $leaf = Split-Path $p.card -Leaf
            if ($leaf -notmatch 'test-card-([0-9.]+)x([0-9.]+)\.pdf') {
                Write-Bad "cannot parse a page size out of $leaf - skipped"
                continue
            }
            $w = $matches[1]; $h = $matches[2]
            if ($null -eq $p.targets -or $p.targets.Count -ne 2) {
                Write-Bad "$($p.name): no 'targets' in printers.json - skipped"
                Write-Host "         Add \"targets\": [horizontal, vertical] in mm."
                continue
            }
            & $PY (Join-Path $ROOT "tools\make_test_card.py") `
                $w $h $p.targets[0] $p.targets[1] | Select-Object -Last 1
        }
    } finally { Pop-Location }
}

function Task-Capture {
    Assert-Venv
    if (-not $Queue -or -not $Name) {
        Write-Bad 'usage: .\hub.ps1 capture -Queue "HUB-CARD" -Name HUB-CARD.restore.devmode'
        exit 1
    }
    $dest = Join-Path (Join-Path $ROOT "devmode") $Name
    Write-Head "Capturing $Queue"
    Write-Warn "Configure the driver by hand FIRST. A blob captured before the media"
    Write-Host "                   and cut settings are right pins the wrong ones forever,"
    Write-Host "                   and nothing reports a problem (Verified 43, 46, 47)."
    Push-Location $ROOT
    try { & $PY -m printhub.devmode capture $Queue $dest } finally { Pop-Location }
}

function Task-Blobs {
    Write-Head "Captured blobs"
    $blobs = @(Get-ChildItem (Join-Path $ROOT "devmode") -Filter *.devmode -ErrorAction SilentlyContinue)
    if ($blobs.Count -eq 0) { Write-Warn "none. .\hub.ps1 capture -Queue <q> -Name <f>"; return }
    $pinned = [Environment]::GetEnvironmentVariable("HUB_DEVMODE", "Machine")
    foreach ($b in $blobs) {
        $mark = " "
        if ($pinned -and $b.FullName -eq $pinned) { $mark = "*" }
        Write-Host ("  {0} {1,-40} {2,7} bytes  {3}" -f $mark, $b.Name, $b.Length, $b.LastWriteTime)
    }
    Write-Host "  * = currently pinned by HUB_DEVMODE" -ForegroundColor DarkGray
    Write-Host "  Blobs are machine- and queue-specific. A fresh box needs its own." -ForegroundColor DarkGray
}

function Task-Clean {
    Write-Head "Cleaning"
    $spool = @(Get-ChildItem (Join-Path $ROOT "spool") -Filter *.pdf -ErrorAction SilentlyContinue)
    if ($spool.Count -gt 0) { $spool | Remove-Item -Force; Write-Ok "removed $($spool.Count) spool PDF(s)" }
    else { Write-Ok "spool already empty" }

    $out = Join-Path $ROOT "out.pdf"
    if (Test-Path $out) { Remove-Item $out -Force; Write-Ok "removed out.pdf" }

    $caches = @(Get-ChildItem $ROOT -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
                Where-Object { $_.FullName -notlike "*\.venv\*" })
    foreach ($c in $caches) { Remove-Item $c.FullName -Recurse -Force -ErrorAction SilentlyContinue }
    if ($caches.Count -gt 0) { Write-Ok "removed $($caches.Count) __pycache__ dir(s)" }

    Write-Host "  Captured blobs in devmode\ were NOT touched." -ForegroundColor DarkGray
}

# --- dispatch -------------------------------------------------------------
switch ($Task.ToLower()) {
    "help"              { Task-Help }
    "init"              { Task-Init }
    "install"           { Task-Install }
    "install-service"   { Task-InstallService }
    "uninstall-service" { Task-UninstallService }
    "start"             { Task-Start }
    "stop"              { Task-Stop }
    "restart"           { Task-Restart }
    "status"            { Task-Status }
    "health"            { Task-Status }
    "dev"               { Task-Dev }
    "console"           { Task-Console }
    "build"             { Task-Build }
    "logs"              { Task-Logs }
    "demo"              { Task-Demo }
    "print"             { Task-Print }
    "printers"          { Task-Printers }
    "bench"             { Task-Bench }
    "cards"             { Task-Cards }
    "capture"           { Task-Capture }
    "blobs"             { Task-Blobs }
    "clean"             { Task-Clean }
    default {
        Write-Bad "unknown task '$Task'"
        Task-Help
        exit 1
    }
}
