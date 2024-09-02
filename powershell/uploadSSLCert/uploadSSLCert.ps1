[CmdletBinding()]
param (
    [Parameter()][string]$vip='helios.cohesity.com',
    [Parameter()][string]$username = 'helios',
    [Parameter()][string]$domain = 'local',
    [Parameter()][string]$tenant,
    [Parameter()][switch]$useApiKey,
    [Parameter()][string]$password,
    [Parameter()][switch]$noPrompt,
    [Parameter()][switch]$mcm,
    [Parameter()][string]$mfaCode,
    [Parameter()][switch]$emailMfaCode,
    [Parameter()][string]$clusterName,
    [Parameter(Mandatory = $True)][string]$certFile,
    [Parameter(Mandatory = $True)][string]$keyFile
)

if(Test-Path -Path $certFile -PathType Leaf){
    $certData = Get-Content $certFile -Raw
}else{
    write-host "Cert File not found!" -ForegroundColor Yellow
    exit 1
}

if(Test-Path -Path $keyFile -PathType Leaf){
    $keyData = Get-Content $keyFile -Raw
}else{
    write-host "Key File not found!" -ForegroundColor Yellow
    exit 1
}

# source the cohesity-api helper code
. $(Join-Path -Path $PSScriptRoot -ChildPath cohesity-api.ps1)

# authentication =============================================
# demand clusterName for Helios/MCM
if(($vip -eq 'helios.cohesity.com' -or $mcm) -and ! $clusterName){
    Write-Host "-clusterName required when connecting to Helios/MCM" -ForegroundColor Yellow
    exit 1
}

# authenticate
apiauth -vip $vip -username $username -domain $domain -passwd $password -apiKeyAuthentication $useApiKey -mfaCode $mfaCode -sendMfaCode $emailMfaCode -heliosAuthentication $mcm -regionid $region -tenant $tenant -noPromptForPassword $noPrompt

# exit on failed authentication
if(!$cohesity_api.authorized){
    Write-Host "Not authenticated" -ForegroundColor Yellow
    exit 1
}

# select helios/mcm managed cluster
if($USING_HELIOS){
    $thisCluster = heliosCluster $clusterName
    if(! $thisCluster){
        exit 1
    }
}
# end authentication =========================================

$cluster = api get cluster

$sslparams = @{
    "certificate" = [string]$certData;
    "lastUpdateTimeMsecs" = 0;
    "privateKey" = [string]$keyData
}

Write-Host "Updating SSL certificate on $($cluster.name)..."
$null = api put certificates/webServer $sslparams

$restartParams = @{
    "clusterId" = $cluster.id;
    "services" = @("iris")
}

Write-Host "Restarting IRIS service..."
$null = api post /nexus/cluster/restart $restartParams
