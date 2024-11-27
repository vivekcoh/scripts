#!/usr/bin/env python

# import Cohesity python module
from pyhesity import *
from datetime import datetime
from datetime import timedelta
import codecs

# command line arguments
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('-v', '--vip', type=str, default='helios.cohesity.com')
parser.add_argument('-u', '--username', type=str, default='helios')
parser.add_argument('-d', '--domain', type=str, default='local')
parser.add_argument('-c', '--clustername', type=str, default=None)
parser.add_argument('-mcm', '--mcm', action='store_true')
parser.add_argument('-i', '--useApiKey', action='store_true')
parser.add_argument('-pwd', '--password', type=str, default=None)
parser.add_argument('-np', '--noprompt', action='store_true')
parser.add_argument('-m', '--mfacode', type=str, default=None)
parser.add_argument('-j', '--jobname', action='append', type=str)
parser.add_argument('-l', '--joblist', type=str)
parser.add_argument('-r', '--remotecluster', type=str, default=None)
parser.add_argument('-a', '--cancelall', action='store_true')
parser.add_argument('-o', '--canceloutdated', action='store_true')
parser.add_argument('-t', '--olderthan', type=int, default=0)
parser.add_argument('-y', '--youngerthan', type=int, default=0)
parser.add_argument('-k', '--daystokeep', type=int, default=0)
parser.add_argument('-n', '--numruns', type=int, default=9999)
parser.add_argument('-f', '--showfinished', action='store_true')
parser.add_argument('-x', '--units', type=str, choices=['MiB', 'GiB'], default='MiB')
parser.add_argument('-e', '--environment', type=str, default='')
parser.add_argument("-L", "--onlylog", action='store_true')
args = parser.parse_args()

vip = args.vip
username = args.username
domain = args.domain
clustername = args.clustername
mcm = args.mcm
useApiKey = args.useApiKey
password = args.password
noprompt = args.noprompt
mfacode = args.mfacode
jobnames = args.jobname
joblist = args.joblist
remotecluster = args.remotecluster
cancelall = args.cancelall
canceloutdated = args.canceloutdated
numruns = args.numruns
olderthan = args.olderthan
youngerthan = args.youngerthan
daysToKeep = args.daystokeep
showfinished = args.showfinished
units = args.units
environment=args.environment
onlylog=args.onlylog

if olderthan > 0:
    olderthanusecs = timeAgo(olderthan, 'days')
if youngerthan > 0:
    youngerthanusecs = timeAgo(youngerthan, 'days')

# authenticate
apiauth(vip=vip, username=username, domain=domain, password=password, useApiKey=useApiKey, helios=mcm, prompt=(not noprompt), mfaCode=mfacode)

# if connected to helios or mcm, select access cluster
if mcm or vip.lower() == 'helios.cohesity.com':
    if clustername is not None:
        heliosCluster(clustername)
    else:
        print('-clustername is required when connecting to Helios or MCM')
        exit()

# exit if not authenticated
if apiconnected() is False:
    print('authentication failed')
    exit(1)


# gather server list
def gatherList(param=None, filename=None, name='items', required=True):
    items = []
    if param is not None:
        for item in param:
            items.append(item)
    if filename is not None:
        f = open(filename, 'r')
        items += [s.strip() for s in f.readlines() if s.strip() != '']
        f.close()
    if required is True and len(items) == 0:
        print('no %s specified' % name)
        exit()
    return items


jobnames = gatherList(jobnames, joblist, name='jobs', required=False)

finishedStates = ['kCanceled', 'kSuccess', 'kFailure', 'kWarning']

multiplier = 1024 * 1024
if units.lower() == 'gib':
    multiplier = 1024 * 1024 * 1024

now = datetime.now()
nowUsecs = dateToUsecs(now.strftime("%Y-%m-%d %H:%M:%S"))

# outfile
cluster = api('get', 'cluster')
dateString = now.strftime("%Y-%m-%d")
outfile = 'replication-tasks-%s-%s.csv' % (cluster['name'], dateString)
f = codecs.open(outfile, 'a')

runningTasks = {}

# for each active job
jobs = api('get', 'protectionJobs')
for job in sorted(jobs, key=lambda job: job['name'].lower()):
    if 'isDeleted' not in job:  # and ('isActive' not in job or job['isActive'] is not False):
        jobId = job['id']
        if len(jobnames) == 0 or job['name'].lower() in [j.lower() for j in jobnames]:
        # if jobname is None or job['name'].lower() == jobname.lower():
            jobName = job['name']
            if environment != '' and job['environment'] != environment:
              continue
            print("Getting tasks for %s" % jobName)
            # find runs with unfinished replication tasks
            url='protectionRuns?jobId=%s&numRuns=%s&excludeTasks=true&excludeNonRestoreableRuns=true&endTimeUsecs=%s' % (jobId, numruns, nowUsecs)
            if youngerthan > 0:
              url='%s&startTimeUsecs=%s' % (url, youngerthanusecs)
            runs = api('get', url)
            if olderthan > 0:
                runs = [r for r in runs if r['backupRun']['stats']['startTimeUsecs'] < olderthanusecs]
            if youngerthan > 0:
                runs = [r for r in runs if r['backupRun']['stats']['startTimeUsecs'] > youngerthanusecs]
            for run in runs:
                runStartTimeUsecs = run['backupRun']['stats']['startTimeUsecs']
                if onlylog and run['backupRun']['runType'][1:] != 'Log':
                  continue
                if 'copyRun' in run:
                    for copyRun in run['copyRun']:
                        # store run details in dictionary
                        if copyRun['target']['type'] == 'kRemote':
                            if copyRun['status'] not in finishedStates or showfinished:
                                if remotecluster is None or copyRun['target']['replicationTarget']['clusterName'].lower() == remotecluster.lower():
                                    runningTask = {
                                        "jobname": jobName,
                                        "jobId": jobId,
                                        "startTimeUsecs": runStartTimeUsecs,
                                        "copyType": copyRun['target']['type'],
                                        "remoteCluster": copyRun['target']['replicationTarget'],
                                        "status": copyRun['status'],
                                        "numSnaps": 0,
                                        "transferred": 0,
                                        "timeTaken": '',
                                        "throughput": 0
                                    }
                                    if copyRun['status'] in finishedStates and 'stats' in copyRun:
                                      if 'stats' in copyRun and copyRun['stats'] is not None:
                                        if 'physicalBytesTransferred' in copyRun['stats']:
                                          runningTask['transferred'] = round(float(copyRun['stats']['physicalBytesTransferred']) / multiplier, 2)
                                        if 'startTimeUsecs' in copyRun['stats'] and 'endTimeUsecs' in copyRun['stats']:
                                          durationTime = timedelta(microseconds=copyRun['stats']['endTimeUsecs'] - copyRun['stats']['startTimeUsecs'])
                                          runningTask['timeTaken'] = str(durationTime)
                                          if durationTime.total_seconds() > 0:
                                            runningTask['throughput'] = round(runningTask['transferred']/durationTime.total_seconds())
                                    if 'copySnapshotTasks' in copyRun and copyRun['copySnapshotTasks'] is not None and len(copyRun['copySnapshotTasks']) > 0:
                                        runningTask['numSnaps'] = len(copyRun['copySnapshotTasks'])
                                    runningTasks[runStartTimeUsecs] = runningTask

if len(runningTasks.keys()) > 0:
    print("\n\nJobName,JobUID,StartTime,Status,Details")
    print("----------           --------")
    # for each replicating run - sorted from oldest to newest
    for startTimeUsecs in sorted(runningTasks.keys()):
        t = runningTasks[startTimeUsecs]
        jobUid='%s:%s:%s' % (cluster['id'], cluster['incarnationId'], t['jobId'])
        # get detailed run info
        run = api('get', '/backupjobruns?allUnderHierarchy=true&exactMatchStartTimeUsecs=%s&id=%s' % (t['startTimeUsecs'], t['jobId']))
        runStartTimeUsecs = run[0]['backupJobRuns']['protectionRuns'][0]['backupRun']['base']['startTimeUsecs']
        numSnapString = ''
        if t['numSnaps'] > 0:
          numSnapString = ' (objects: %s)' % t['numSnaps']
        transferredString = ''
        if t['transferred'] > 0 or numSnapString != '':
          transferredString = '   %s %s transferred' % (t['transferred'], units.upper())
        if t['timeTaken'] != '':
          transferredString += ',TimeTaken:%s Throughput:%sMBps' % (t['timeTaken'], t['throughput'])
        # get replication task(s)
        if 'activeTasks' in run[0]['backupJobRuns']['protectionRuns'][0]['copyRun']:
            printStr = "%s,%s,%s(%s),%s%s" % (t['jobname'], jobUid, usecsToDate(t['startTimeUsecs']),t['startTimeUsecs'], numSnapString, transferredString)
            for task in run[0]['backupJobRuns']['protectionRuns'][0]['copyRun']['activeTasks']:
                if task['snapshotTarget']['type'] == 2:
                    if remotecluster is None or task['snapshotTarget']['replicationTarget']['clusterName'].lower() == remotecluster.lower():
                        # determine if run is now older than the desired retention
                        noLongerNeeded = ''
                        usecsToKeep = daysToKeep * 1000000 * 86400
                        timePassed = nowUsecs - runStartTimeUsecs
                        if daysToKeep > 0 and timePassed > usecsToKeep:
                            noLongerNeeded = "NO LONGER NEEDED"
                        if cancelall or (canceloutdated and noLongerNeeded == "NO LONGER NEEDED"):
                            printStr += ", %s  %s (canceling)" % (task['taskUid']['objectId'], noLongerNeeded)
                            cancelTaskParams = {
                                "jobId": t['jobId'],
                                "copyTaskUid": {
                                    "id": task['taskUid']['objectId'],
                                    "clusterId": task['taskUid']['clusterId'],
                                    "clusterIncarnationId": task['taskUid']['clusterIncarnationId']
                                }
                            }
                            try:
                                #print('Blocked cancellation for %s' % cancelTaskParams)
                                result = api('post', 'protectionRuns/cancel/%s' % t['jobId'], cancelTaskParams)
                            except Exception:
                                pass
                        else:
                            printStr += ", Replication Task ID %s  %s" % (task['taskUid']['objectId'], noLongerNeeded)
            print(printStr)
            f.write(printStr + "\n")
        elif showfinished:
            printStr = "%s,%s,%s(%s),%s, %s%s" % (t['jobname'], jobUid, usecsToDate(t['startTimeUsecs']), t['startTimeUsecs'], t['status'][1:], numSnapString, transferredString)
            print(printStr)
            f.write(printStr + "\n")
else:
    print('\nNo active replication tasks found')
