<#
Set up Roshan Mustaqbil on this Windows PC. Double-click setup.bat (in the
app's folder) rather than running this directly.

It installs Python 3.12 if no suitable Python is found, installs the app's packages, creates the
settings file and database, creates the administrator, optionally loads the
demo data, and puts a "Roshan Mustaqbil" shortcut on the desktop. Running it
again is safe: finished steps are skipped or repeated harmlessly.

Unattended use (for example on a test machine):
  setup.bat -Quiet -AdminPassword "choose-one" -Demo yes -NoShortcut
#>
param(
    [switch]$Quiet,
    [string]$AdminPassword = $env:RM_ADMIN_PASSWORD,
    [ValidateSet("ask", "yes", "no")][string]$Demo = "ask",
    [switch]$NoShortcut,
    [switch]$Start
)

$ErrorActionPreference = "Stop"
$ProgressPreference = "SilentlyContinue"
$App = Split-Path $PSScriptRoot -Parent
Set-Location $App
$Venv = Join-Path $App ".venv\Scripts\python.exe"

function Step($text) { Write-Host ""; Write-Host "== $text" -ForegroundColor Cyan }
function Done($text) { Write-Host "   $text" -ForegroundColor Green }
function Stop-Setup($text) {
    Write-Host ""
    Write-Host "Setup stopped: $text" -ForegroundColor Red
    if (-not $Quiet) { Read-Host "Press Enter to close" | Out-Null }
    exit 2  # setup.bat pauses on any other failure
}
# Anything unexpected also stops with a message, instead of closing the window.
trap { Stop-Setup "$_" }
function Ask-YesNo($question, $default) {
    if ($Quiet) { return $default }
    $hint = if ($default) { "Y/n" } else { "y/N" }
    $answer = Read-Host "$question [$hint]"
    if ([string]::IsNullOrWhiteSpace($answer)) { return $default }
    return $answer.Trim().ToLower().StartsWith("y")
}
function Run-Python([string[]]$arguments, $failure) {
    & $Venv @arguments
    if ($LASTEXITCODE -ne 0) { Stop-Setup $failure }
}
function Get-PythonOutput([string[]]$arguments) {
    # Only the last line printed; Django's start-up messages go to stderr.
    $previous = $ErrorActionPreference
    $ErrorActionPreference = "Continue"
    try { $lines = & $Venv @arguments 2>$null } finally { $ErrorActionPreference = $previous }
    return "$($lines | Select-Object -Last 1)".Trim()
}

Write-Host ""
Write-Host "Roshan Mustaqbil setup" -ForegroundColor White
Write-Host "Folder: $App"

# 1. Python ---------------------------------------------------------------
Step "1/7 Python"
function Find-Python {
    # The app's packages support Python 3.12 to 3.14.
    $tries = @("-3.12", "-3.13", "-3.14" | ForEach-Object { @{ Exe = "py"; Args = @($_) } }) + @(@{ Exe = "python"; Args = @() })
    foreach ($try in $tries) {
        if (Get-Command $try.Exe -ErrorAction SilentlyContinue) {
            try {
                $found = & $try.Exe @($try.Args + @("-c", "import sys; print(sys.executable if (3, 12) <= sys.version_info[:2] <= (3, 14) else '')")) 2>$null
                if ($LASTEXITCODE -eq 0 -and $found) { return ($found | Select-Object -Last 1).Trim() }
            } catch { }
        }
    }
    $local = Join-Path $env:LOCALAPPDATA "Programs\Python\Python312\python.exe"
    if (Test-Path $local) { return $local }
    return $null
}
$Python = Find-Python
if (-not $Python -and -not (Test-Path $Venv)) {
    if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
        Stop-Setup "Python isn't installed. Install it from https://www.python.org/downloads/ (tick 'Add python.exe to PATH'), then run setup again."
    }
    Write-Host "   Installing Python 3.12 (a few minutes)..."
    winget install --exact --id Python.Python.3.12 --scope user --silent --accept-package-agreements --accept-source-agreements | Out-Host
    $Python = Find-Python
    if (-not $Python) { Stop-Setup "Python 3.12 didn't install. Install it from https://www.python.org/downloads/, then run setup again." }
}
if ($Python) { Done "Using $Python" } else { Done "Using the app's existing Python environment" }

# 2. The app's packages ------------------------------------------------------------
Step "2/7 The app's packages (the first time takes 5-15 minutes)"
if (-not (Test-Path $Venv)) {
    & $Python -m venv .venv
    if ($LASTEXITCODE -ne 0) { Stop-Setup "Couldn't create the Python environment (.venv)." }
}
Run-Python @("-m", "pip", "install", "--upgrade", "--quiet", "pip") "Couldn't update pip. Check the internet connection and run setup again."
& $Venv -m pip install --quiet --disable-pip-version-check -r requirements.txt
if ($LASTEXITCODE -ne 0) {
    Write-Host "   Retrying once..."
    Run-Python @("-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt") "Couldn't install the app's packages. Check the internet connection and run setup again."
}
Done "Packages installed"

# 3. Settings -------------------------------------------------------------------
Step "3/7 Settings"
$EnvFile = Join-Path $App ".env"
if (Test-Path $EnvFile) {
    Done "Keeping the existing settings file (.env)"
} else {
    # Letters, digits, - and _ only: a "$" would be read as a reference to another setting.
    $secret = (& $Venv -c "import secrets; print(secrets.token_urlsafe(50))").Trim()
    $initPassword = (& $Venv -c "import secrets; print(secrets.token_urlsafe(24))").Trim()
    # Other devices can use this PC's name (which doesn't change) or its current addresses.
    $addresses = @("localhost", "127.0.0.1", $env:COMPUTERNAME.ToLower())
    try {
        $addresses += Get-NetIPAddress -AddressFamily IPv4 -ErrorAction Stop |
            Where-Object { $_.IPAddress -notlike "127.*" -and $_.IPAddress -notlike "169.254.*" } |
            ForEach-Object { $_.IPAddress }
    } catch { }
    $tunnels = @(".devtunnels.ms", ".trycloudflare.com", ".ngrok-free.app", ".ngrok-free.dev", ".app.github.dev")
    $database = (Join-Path $App "roshan_mustaqbil.sqlite3") -replace "\\", "/"
    $lines = @(
        "# Roshan Mustaqbil settings for this PC, written by setup. Keep this file private.",
        "DEBUG=False",
        "# Plain http inside the building (a tunnel adds https), and static files served from the app's folders.",
        "SESSION_COOKIE_SECURE=False",
        "CSRF_COOKIE_SECURE=False",
        "WHITENOISE_USE_FINDERS=True",
        "SECRET_KEY=$secret",
        "ALLOWED_HOSTS=$((($addresses + $tunnels) | Select-Object -Unique) -join ',')",
        "CSRF_TRUSTED_ORIGINS=http://localhost:8001,http://127.0.0.1:8001,https://*.devtunnels.ms,https://*.trycloudflare.com,https://*.ngrok-free.app,https://*.ngrok-free.dev,https://*.app.github.dev",
        "TIME_ZONE=Asia/Kolkata",
        "DB_ENGINE=django.db.backends.sqlite3",
        "DB_NAME=$database",
        "DB_INIT_PASSWORD=$initPassword"
    )
    [System.IO.File]::WriteAllLines($EnvFile, [string[]]$lines, (New-Object System.Text.UTF8Encoding $false))
    Done "Created .env (database: roshan_mustaqbil.sqlite3)"
}

# 4. Database -------------------------------------------------------------------
Step "4/7 Database (the first time takes a few minutes)"
Run-Python @("manage.py", "migrate", "--noinput", "-v", "0") "Couldn't set up the database."
Done "Database ready"

# 5. The administrator ---------------------------------------------------------------
Step "5/7 The administrator (the only sign-in)"
$adminExists = (Get-PythonOutput @("manage.py", "shell", "-c", "from horilla_auth.models import HorillaUser; print('yes' if HorillaUser.objects.filter(username='admin').exists() else 'no')")) -eq "yes"
if ($adminExists) {
    # Nothing to ask: setup never changes an existing password. This still
    # checks the centre's records; the throwaway password is not used.
    $AdminPassword = (& $Venv -c "import secrets; print(secrets.token_urlsafe(24))").Trim()
} elseif (-not $AdminPassword) {
    if ($Quiet) { Stop-Setup "Give -AdminPassword (or set RM_ADMIN_PASSWORD) for an unattended setup." }
    while ($true) {
        $first = Read-Host "Choose the administrator's password (8+ characters)" -AsSecureString
        $second = Read-Host "Type it again" -AsSecureString
        $plainFirst = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($first))
        $plainSecond = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($second))
        if ($plainFirst.Length -lt 8) { Write-Host "   Use at least 8 characters." -ForegroundColor Yellow; continue }
        if ($plainFirst -ne $plainSecond) { Write-Host "   The two passwords don't match." -ForegroundColor Yellow; continue }
        $AdminPassword = $plainFirst
        break
    }
}
Run-Python @("manage.py", "bootstrap_roshan_mustaqbil_demo", "--password", $AdminPassword) "Couldn't create the administrator."
if ($adminExists) {
    Done "Keeping the existing administrator, admin, and their password. To change it: .venv\Scripts\python manage.py changepassword admin"
} else {
    Done "Sign in as: admin, with the password you chose"
}

# 6. Demo data -------------------------------------------------------------------
Step "6/7 Demo data"
$loadDemo = switch ($Demo) { "yes" { $true } "no" { $false } default { Ask-YesNo "Load the demo data (960 example students)? Choose No for real use." $false } }
if ($loadDemo) {
    Run-Python @("manage.py", "seed_youth_centre_demo") "Couldn't load the demo data."
    Done "Demo data loaded. Remove it before real use: .venv\Scripts\python manage.py seed_youth_centre_demo --remove"
} else {
    Done "No demo data. Add students at the desk, or import your register (Students > Import from a spreadsheet)."
}

# 7. Desktop shortcut ------------------------------------------------------------
Step "7/7 Desktop shortcut"
if ($NoShortcut) {
    Done "Skipped"
} else {
    $desktop = [Environment]::GetFolderPath("Desktop")
    $shell = New-Object -ComObject WScript.Shell
    $link = $shell.CreateShortcut((Join-Path $desktop "Roshan Mustaqbil.lnk"))
    $link.TargetPath = Join-Path $App "scripts\start.bat"
    $link.WorkingDirectory = $App
    $link.IconLocation = Join-Path $App "static\images\brand\rm.ico"
    $link.Description = "Start Roshan Mustaqbil"
    $link.Save()
    Done "Created 'Roshan Mustaqbil' on the desktop"
}

Write-Host ""
Write-Host "Setup finished." -ForegroundColor Green
Write-Host "Start the app with the 'Roshan Mustaqbil' desktop shortcut (or scripts\start.bat),"
Write-Host "then open http://127.0.0.1:8001 and sign in as admin."
if ($Start -or (Ask-YesNo "Start the app now?" $false)) {
    Start-Process -FilePath (Join-Path $App "scripts\start.bat") -WorkingDirectory $App
}
