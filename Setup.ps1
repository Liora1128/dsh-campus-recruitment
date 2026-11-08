param([string]$DataRoot='',[string]$Python='',[string]$Node='',[string]$Browser='')
$ErrorActionPreference='Stop'
$dshDataHome=if($env:DSH_HOME){$env:DSH_HOME}else{Join-Path ([Environment]::GetFolderPath('UserProfile')) '.dsh'}
$nodeCandidates=@($Node,(Join-Path $dshDataHome 'dsh-runtimes\dsh-primary-runtime\dependencies\node\bin\node.exe'))
$nodeCommand=Get-Command node -ErrorAction SilentlyContinue
if($nodeCommand){$nodeCandidates+=$nodeCommand.Source}
$selectedNode=$nodeCandidates | Where-Object {$_ -and (Test-Path -LiteralPath $_ -PathType Leaf)} | Select-Object -First 1
if(-not $selectedNode){throw 'Cannot find Node 22+. Pass -Node with the DSH bundled Node executable or an existing Node installation.'}
$setupArgs=@((Join-Path $PSScriptRoot 'tools\configure.mjs'))
foreach($entry in @(@('--data-root',$DataRoot),@('--python',$Python),@('--node',$Node),@('--browser',$Browser))){if($entry[1]){$setupArgs+=@($entry[0],$entry[1])}}
& $selectedNode @setupArgs
if($LASTEXITCODE -ne 0){throw 'Configuration failed'}
& $selectedNode (Join-Path $PSScriptRoot 'tools\doctor.mjs')
if($LASTEXITCODE -ne 0){throw 'Runtime checks failed'}
Write-Host 'Install this directory in DSH: Plugins -> Add plugin -> Third-party plugin.'
Write-Host $PSScriptRoot
