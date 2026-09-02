$Server=$env:DRS_URL.TrimEnd('/')
$Key=$env:DRS_API_KEY
$Source=if($env:DRS_SOURCE){$env:DRS_SOURCE}else{$env:COMPUTERNAME}
$Interval=if($env:DRS_INTERVAL){[int]$env:DRS_INTERVAL}else{30}
while($true){
  try {
    $cpu=(Get-CimInstance Win32_Processor | Measure-Object -Property LoadPercentage -Average).Average
    $os=Get-CimInstance Win32_OperatingSystem
    $mem=[math]::Round((($os.TotalVisibleMemorySize-$os.FreePhysicalMemory)/$os.TotalVisibleMemorySize)*100,2)
    $disk=Get-CimInstance Win32_LogicalDisk -Filter "DriveType=3" | Select-Object -First 1
    $diskPct=if($disk.Size -gt 0){[math]::Round((($disk.Size-$disk.FreeSpace)/$disk.Size)*100,2)}else{0}
    $body=@{category='system_metric';source=$Source;severity='info';action='sample';resource='host';payload=@{cpu_percent=$cpu;memory_percent=$mem;disk_percent=$diskPct;platform='windows'}} | ConvertTo-Json -Depth 5
    if($Server -and $Key){Invoke-RestMethod -Method Post -Uri "$Server/events" -Headers @{'X-API-Key'=$Key} -ContentType 'application/json' -Body $body -TimeoutSec 3 | Out-Null}
  } catch {}
  Start-Sleep -Seconds $Interval
}
