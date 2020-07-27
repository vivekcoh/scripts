# usage:
# ./intervalPolicy.ps1 -vip mycluster `
#                           -username myuser `
#                           -domain mydomain.net `
#                           -policyName 'my policy' `
#                           -intervalMinutes 20

### process commandline arguments
[CmdletBinding()]
param (
    [Parameter(Mandatory = $True)][string]$vip,
    [Parameter(Mandatory = $True)][string]$username,
    [Parameter()][string]$domain = 'local',
    [Parameter()][string]$policyName,
    [Parameter()][Int64]$intervalMinutes = 60,
    [Parameter()][Int64]$daysToKeep = $null,
    [Parameter()][Int64]$retries = $null,
    [Parameter()][Int64]$retryInterval = $null
)

if($intervalMinutes -lt 3 -or $intervalMinutes -gt 1440){
    Write-Host "intervalMinutes should be between 3 and 1440" -ForegroundColor Yellow
    exit 1
}

if($null -ne $daysToKeep -and $daysToKeep -lt 1){
    $daysToKeep = 1
}

# source the cohesity-api helper code
. $(Join-Path -Path $PSScriptRoot -ChildPath cohesity-api.ps1)

# authenticate
apiauth -vip $vip -username $username -domain $domain

# find existing policy
$policies = api get protectionPolicies
$policy = $policies | Where-Object name -eq $policyName

# create blackout windows
$days = @('kMonday', 'kTuesday', 'kWednesday', 'kThursday', 'kFriday', 'kSaturday', 'kSunday')
$midnight = [datetime]'2020-01-01 0:00:00'
$endOfDay = $midnight.AddHours(24).AddMinutes(-1)
$startTime = $midnight
$endTime = $midnight
$blackoutPeriods = @()
while($startTime -ne $endOfDay){
    $startTime = $endTime.AddMinutes(1)
    $endTime = $startTime.AddMinutes($intervalMinutes - 2)
    if($endTime -gt $endOfDay){
        $endTime = $endOfDay
    }
    foreach($day in $days){
        $blackoutPeriods += @{
            "day"       = $day;
            "startTime" = @{
                "hour"   = $startTime.Hour;
                "minute" = $startTime.Minute
            };
            "endTime"   = @{
                "hour"   = $endTime.Hour;
                "minute" = $endTime.Minute
            }
        }
    }
    $startTime = $endTime
    $endTime = $endTime.AddMinutes(1)
}

if($policy){
    # update existing policy
    $policy.incrementalSchedulingPolicy = @{
        "periodicity" = "kContinuous";
        "continuousSchedule" = @{
            "backupIntervalMins" = $intervalMinutes
        }
    }
    if($daysToKeep){
        $policy.daysToKeep = $daysToKeep
    }
    if(! $policy.PSObject.Properties['blackoutPeriods']){
        setApiProperty -name 'blackoutPeriods' -value $blackoutPeriods -object $policy
    }else{
        $policy.blackoutPeriods = $blackoutPeriods
    }
    if($null -ne $retries){
        $policy.retries = $retries
    }
    if($null -ne $retryInterval){
        $policy.retryIntervalMins = $retryInterval
    }
    "Updating policy $policyName..."
    $null = api put "protectionPolicies/$($policy.id)" $policy
}else{
    # create new policy
    if(! $daysToKeep){
        $daysToKeep = 14
    }
    if(! $retries){
        $retries = 3
    }
    if(! $retryInterval){
        $retryInterval = 30
    }
    $policy = @{
        "name"                        = $policyName;
        "incrementalSchedulingPolicy" = @{
            "periodicity"        = "kContinuous";
            "continuousSchedule" = @{
                "backupIntervalMins" = $intervalMinutes
            }
        };
        "blackoutPeriods"             = $blackoutPeriods;
        "retries"                     = $retries;
        "retryIntervalMins"           = $retryInterval;
        "daysToKeep"                  = $daysToKeep
    }
    "Creating policy $policyName..."
    $null = api post protectionPolicies $policy
}
