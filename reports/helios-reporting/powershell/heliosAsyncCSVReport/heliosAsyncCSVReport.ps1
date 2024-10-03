[CmdletBinding()]
param (
    [Parameter()][string]$vip='helios.cohesity.com',
    [Parameter()][string]$username='helios',
    [Parameter()][switch]$EntraId,
    [Parameter()][string]$startDate = '',
    [Parameter()][string]$endDate = '',
    [Parameter()][switch]$thisCalendarMonth,
    [Parameter()][switch]$lastCalendarMonth,
    [Parameter()][int]$days = 7,
    [Parameter()][array]$clusterNames,
    [Parameter()][string]$reportName = 'Protection Runs',
    [Parameter()][string]$timeZone = 'America/New_York',
    [Parameter()][string]$outputPath = '.',
    [Parameter()][switch]$includeCCS,
    [Parameter()][switch]$excludeLogs,
    [Parameter()][array]$environment,
    [Parameter()][array]$excludeEnvironment,
    [Parameter()][switch]$replicationOnly,
    [Parameter()][int]$timeoutSeconds = 300,
    [Parameter()][int]$sleepTimeSeconds = 15,
    [Parameter()][switch]$dbg
)

# gather list from command line params and file
function gatherList($Param=$null, $FilePath=$null, $Required=$True, $Name='items'){
    $items = @()
    if($Param){
        $Param | ForEach-Object {$items += $_}
    }
    if($FilePath){
        if(Test-Path -Path $FilePath -PathType Leaf){
            Get-Content $FilePath | ForEach-Object {$items += [string]$_}
        }else{
            Write-Host "Text file $FilePath not found!" -ForegroundColor Yellow
            exit
        }
    }
    if($Required -eq $True -and $items.Count -eq 0){
        Write-Host "No $Name specified" -ForegroundColor Yellow
        exit
    }
    return ($items | Sort-Object -Unique)
}

# source the cohesity-api helper code
. $(Join-Path -Path $PSScriptRoot -ChildPath cohesity-api.ps1)

# authenticate
apiauth -vip $vip -username $username -domain 'local' -helios -entraIdAuthentication $EntraId

$allClusters = heliosClusters
$regions = api get -mcmv2 dms/regions
if($includeCCS){
    foreach($region in $regions.regions){
        $allClusters = @($allClusters + $region)
    }
}

# select clusters to include
$selectedClusters = $allClusters
if($clusterNames.length -gt 0){
    $selectedClusters = $allClusters | Where-Object {$_.name -in $clusterNames -or $_.id -in $clusterNames}
    $unknownClusters = $clusterNames | Where-Object {$_ -notin @($allClusters.name) -and $_ -notin @($allClusters.id)}
    if($unknownClusters){
        Write-Host "Clusters not found:`n $($unknownClusters -join ', ')" -ForegroundColor Yellow
        exit 1
    }
}

# date range
$today = Get-Date

if($startDate -ne '' -and $endDate -ne ''){
    $uStart = dateToUsecs $startDate
    $uEnd = dateToUsecs $endDate
}elseif ($thisCalendarMonth) {
    $uStart = dateToUsecs ($today.Date.AddDays(-($today.day-1)))
    $uEnd = dateToUsecs ($today)
}elseif ($lastCalendarMonth) {
    $uStart = dateToUsecs ($today.Date.AddDays(-($today.day-1)).AddMonths(-1))
    $uEnd = dateToUsecs ($today.Date.AddDays(-($today.day-1)).AddSeconds(-1))
}else{
    $uStart = timeAgo $days 'days'
    $uEnd = dateToUsecs ($today)
}

$start = (usecsToDate $uStart).ToString('yyyy-MM-dd')
$end = (usecsToDate $uEnd).ToString('yyyy-MM-dd')

$excludeLogsFilter = @{
    "attribute" = "backupType";
    "filterType" = "In";
    "inFilterParams" = @{
        "attributeDataType" = "String";
        "stringFilterValues" = @(
            "kRegular",
            "kFull",
            "kSystem"
        );
        "attributeLabels" = @(
            "Incremental",
            "Full",
            "System"
        )
    }
}

$environmentFilter = @{
    "attribute" = "environment";
    "filterType" = "In";
    "inFilterParams" = @{
        "attributeDataType" = "String";
        "stringFilterValues" = @(
            $environment
        );
        "attributeLabels" = @(
            $environment
        )
    }
}

$replicationFilter = @{
    "attribute" = "activityType";
    "filterType" = "In";
    "inFilterParams" = @{
        "attributeDataType" = "String";
        "stringFilterValues" = @(
            "Replication"
        );
        "attributeLabels" = @(
            "Replication"
        )
    }
}

# get list of available reports
$reports = api get -reportingV2 reports
$report = $reports.reports | Where-Object {$_.title -eq $reportName}
if(! $report){
    Write-Host "Invalid report name: $reportName" -ForegroundColor Yellow
    Write-Host "`nAvailable report names are:`n"
    Write-Host (($reports.reports.title | Sort-Object) -join "`n")
    exit
}

$title = $report.title

# output files
$csvFileName = $(Join-Path -Path $outputPath -ChildPath "$($title.replace('/','-').replace('\','-'))_$($start)_$($end).csv")

$systemIds = @()
$systemNames = @()

foreach($cluster in ($selectedClusters)){
    if($cluster.name -in @($regions.regions.name)){
        $systemIds = @($systemIds + $cluster.id)
    }else{
        $systemIds = @($systemIds + "$($cluster.clusterId):$($cluster.clusterIncarnationId)")
    }
    $systemNames = @($systemNames + $cluster.name)
}

$reportParams = @{
    "reportId" = $report.id;
    "name" = $report.title;
    "reportFormats" = @(
        "CSV"
    );
    "filters" = @(
        @{
            "attribute"             = "date";
            "filterType"            = "TimeRange";
            "timeRangeFilterParams" = @{
                "lowerBound" = [int64]$uStart;
                "upperBound" = [int64]$uEnd
            }
        }
        @{
            "attribute" = "systemId";
            "filterType" = "Systems";
            "systemsFilterParams" = @{
                "systemIds" = @($systemIds);
                "systemNames" = @($systemNames)
            }
        }
    );
    "timezone" = $timeZone;
    "notificationParams" = $null
}

if($excludeLogs){
    $reportParams.filters = @($reportParams.filters + $excludeLogsFilter)
}
if($environment){
    $reportParams.filters = @($reportParams.filters + $environmentFilter)
}
if($replicationOnly){
    $reportParams.filters = @($reportParams.filters + $replicationFilter)
}
if($dbg){
    $reportParams | toJson
}

$request = api post -reportingV2 "reports/requests" $reportParams
if(! $request.PSObject.Properties['id']){
    exit 1
}

$finishedStates = @('Succeeded', 'Canceled', 'Failed', 'Warning', 'SucceededWithWarning')

# Wait for report to generate
Write-Host "Waiting to report to generate..."
while($True){   
    Start-Sleep $sleepTimeSeconds
    $thisRequest = (api get -reportingV2 "reports/requests").requests | Where-Object id -eq $request.id
    if($thisRequest.status -in $finishedStates){
        break
    }
}

# Download CSV
Write-Host "Report generation status: $($thisRequest.status)"
if($thisRequest.status -ne 'Succeeded'){
    exit 1
}
fileDownload -fileName "report-tmp.zip" -uri "https://helios.cohesity.com/heliosreporting/api/v1/public/reports/requests/$($thisRequest.id)/artifacts/CSV"
Expand-Archive -Path "report-tmp.zip"
Remove-Item -Path "report-tmp.zip"

$csv = Import-CSV -Path "report-tmp/$($report.id)_$(usecsToDate $thisRequest.submittedAtTimestampUsecs -format "yyyy-MM-d_Hm").csv"
$columns = $csv[0].PSObject.properties.name 

# exclude environments
if($excludeEnvironment){
    $csv = $csv | Where-Object environment -notin $excludeEnvironment
}

# Convert timestamps to dates
$epochColumns = @('lastRunTime', 'lastSuccessfulBackup', 'endTimeUsecs', 'runStartTimeUsecs')
foreach($epochColumn in $epochColumns){
    $csv | Where-Object {$_.PSObject.Properties[$epochColumn] -and $_.$epochColumn -ne $null -and $_.$epochColumn -ne 0} | ForEach-Object{
        $_.$epochColumn = usecsToDate $($_.$epochColumn)
    }
}

# convert usecs to seconds
$usecColumns = @('durationUsecs')
$usecColumnRenames = @{'durationUsecs' = 'durationSeconds'}
foreach($usecColumn in $usecColumns){
    $csv | Where-Object {$_.PSObject.Properties[$usecColumn]} | ForEach-Object{
        $_.$usecColumn = [int]($_.$usecColumn / 1000000)
    }
}

$csv | Export-CSV -Path $csvFileName
Write-Host "`nCSV output saved to $csvFileName`n"
Remove-Item -Path "report-tmp" -Recurse
