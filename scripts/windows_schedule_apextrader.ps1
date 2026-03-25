# Windows Scheduled Task Install for ApexTrader
# Run in PowerShell as Administrator.

$taskName = 'ApexTraderAutoRun'
$taskDescription = 'Run ApexTrader trading bot every 5 minutes in local environment'

$action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '-NoProfile -WindowStyle Hidden -Command "cd C:\Users\user\Desktop\wsapex\apextrader; .\\run_local_ps.ps1 | Tee-Object -FilePath .\\apextrader.log"'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1)
$trigger.RepetitionInterval = [TimeSpan]::FromMinutes(5)
$trigger.RepetitionDuration = [TimeSpan]::MaxValue

$principal = New-ScheduledTaskPrincipal -UserId "$env:UserName" -LogonType Interactive -RunLevel Highest

$task = New-ScheduledTask -Action $action -Trigger $trigger -Principal $principal -Settings @{AllowStartIfOnBatteries=$true; RunOnlyIfIdle=$false; WakeToRun=$true; StartWhenAvailable=$true}

Register-ScheduledTask -TaskName $taskName -InputObject $task -Description $taskDescription -Force
Write-Host "Scheduled task '$taskName' installed successfully. Use 'schtasks /query /tn $taskName' to inspect."