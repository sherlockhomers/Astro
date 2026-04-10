param(
    [int]$InitialMB = 65536,
    [int]$MaximumMB = 65536,
    [string]$PagefilePath = 'C:\pagefile.sys'
)

$principal = New-Object Security.Principal.WindowsPrincipal([Security.Principal.WindowsIdentity]::GetCurrent())
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {
    Write-Error "Please run this script as Administrator."
    exit 1
}

$regPath = 'HKLM:\SYSTEM\CurrentControlSet\Control\Session Manager\Memory Management'
$pagefileValue = "$PagefilePath $InitialMB $MaximumMB"
Set-ItemProperty -Path $regPath -Name PagingFiles -Value $pagefileValue
Set-ItemProperty -Path $regPath -Name ExistingPageFiles -Value "\\??\\$PagefilePath"

Write-Host "Pagefile configured:" $pagefileValue
Write-Host "A system reboot is required for changes to take effect."
