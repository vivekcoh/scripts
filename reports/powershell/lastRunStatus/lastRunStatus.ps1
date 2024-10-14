# process commandline arguments
[CmdletBinding()]
param (
    [Parameter()][array]$vip,
    [Parameter()][string]$username = 'helios',
    [Parameter()][string]$domain = 'local',
    [Parameter()][string]$tenant = $null,
    [Parameter()][switch]$useApiKey,
    [Parameter()][string]$password = $null,
    [Parameter()][switch]$noPrompt,
    [Parameter()][switch]$mcm,
    [Parameter()][string]$mfaCode = $null,
    [Parameter()][array]$clusterName = $null
)

# source the cohesity-api helper code
. $(Join-Path -Path $PSScriptRoot -ChildPath cohesity-api.ps1)

# # authentication =============================================
# # demand clusterName for Helios/MCM
# if(($vip -eq 'helios.cohesity.com' -or $mcm) -and ! $clusterName){
#     Write-Host "-clusterName required when connecting to Helios/MCM" -ForegroundColor Yellow
#     exit 1
# }

# # authenticate
# apiauth -vip $vip -username $username -domain $domain -passwd $password -apiKeyAuthentication $useApiKey -mfaCode $mfaCode -heliosAuthentication $mcm -tenant $tenant -noPromptForPassword $noPrompt

# # exit on failed authentication
# if(!$cohesity_api.authorized){
#     Write-Host "Not authenticated" -ForegroundColor Yellow
#     exit 1
# }

# # select helios/mcm managed cluster
# if($USING_HELIOS){
#     $thisCluster = heliosCluster $clusterName
#     if(! $thisCluster){
#         exit 1
#     }
# }
# # end authentication =========================================

# outfile
$dateString = (get-date).ToString('yyyy-MM-dd')
$outfileName = "lastRunStatus-$dateString.csv"
$yesterday = timeAgo 1 Days

# headings
"Cluster Name,Job Name,Tenant,Policy,Last Run,Last Status,Paused,Backed Up Last 24 Hours" | Out-File -FilePath $outfileName -Encoding utf8

function reportJobs(){
    $cluster = api get cluster
    "`n$($cluster.name)"
    $jobs = api get -v2 "data-protect/protection-groups?useCachedData=false&pruneSourceIds=true&pruneExcludedSourceIds=true&isDeleted=false&isActive=true&includeTenants=true&includeLastRunInfo=true"
    $policies = api get -v2 "data-protect/policies?excludeLinkedPolicies=false"
    foreach($job in $jobs.protectionGroups | Sort-Object -Property name){
        $tenant = $job.permissions.name
        if($tenant){
            "    {0} ({1})" -f $job.name, $tenant
        }else{
            "    {0}" -f $job.name
            $tenant = ''
        }
        $policy = $policies.policies | Where-Object {$_.id -eq $job.policyId}
        $lastRunUsecs = 0
        $lastStatus = '-'
        if($job.PSObject.Properties['lastRun']){
            if($job.lastRun.PSObject.Properties['localBackupInfo']){
                $runInfo = $job.lastRun.localBackupInfo
            }elseif($job.lastRun.PSObject.Properties['originalBackupInfo']){
                $runInfo = $job.lastRun.originalBackupInfo
            }else{
                $runInfo = $job.lastRun.archivalInfo.archivalTargetResults[0]
            }
            $lastRunUsecs = $runInfo.startTimeUsecs
            $lastStatus = $runInfo.status
        }
        $backedUpLast24 = $False
        if($lastRunUsecs -gt $yesterday){
            $backedUpLast24 = $True
        }
        "$($cluster.name),$($job.name),$tenant,$($policy.name),$(usecsToDate $lastRunUsecs),$lastStatus,$($job.isPaused),$backedUpLast24" | Out-File -FilePath $outfileName -Append
    }    
}

# authentication =============================================
if(! $vip){
    $vip = @('helios.cohesity.com')
}

foreach($v in $vip){
    # authenticate
    apiauth -vip $v -username $username -domain $domain -passwd $password -apiKeyAuthentication $useApiKey -mfaCode $mfaCode -heliosAuthentication $mcm -regionid $region -tenant $tenant -noPromptForPassword $noPrompt -quiet
    if(!$cohesity_api.authorized){
        output "`n$($v): authentication failed" -ForegroundColor Yellow
        continue
    }
    if($USING_HELIOS){
        if(! $clusterName){
            $clusterName = @((heliosClusters).name)
        }
        foreach($c in $clusterName){
            $null = heliosCluster $c
            reportJobs
        }
    }else{
        reportJobs
    }
}

"`nOutput saved to $outfilename`n"
