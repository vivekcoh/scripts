#!/usr/bin/env python
"""base V2 example"""

# import pyhesity wrapper module
from pyhesity import *
from datetime import datetime
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
parser.add_argument('-e', '--emailmfacode', action='store_true')
parser.add_argument('-n', '--numruns', type=int, default=100)
parser.add_argument('-y', '--days', type=int, default=1)
parser.add_argument('-o', '--lastrunonly', action='store_true')
parser.add_argument('-l', '--onlylogs', action='store_true')
parser.add_argument('-x', '--units', type=str, choices=['MiB', 'GiB', 'mib', 'gib'], default='MiB')  # units
parser.add_argument('-j', '--jobname', type=str, default='')

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
emailmfacode = args.emailmfacode
numruns = args.numruns
days = args.days
lastrunonly = args.lastrunonly
onlylogs = args.onlylogs
units = args.units
jobname=args.jobname

multiplier = 1024 * 1024 * 1024
if units.lower() == 'mib':
    multiplier = 1024 * 1024

if units == 'mib':
    units = 'MiB'
if units == 'gib':
    units = 'GiB'

# authenticate
apiauth(vip=vip, username=username, domain=domain, password=password, useApiKey=useApiKey, helios=mcm, prompt=(not noprompt), emailMfaCode=emailmfacode, mfaCode=mfacode)

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

now = datetime.now()
nowUsecs = dateToUsecs(now.strftime("%Y-%m-%d %H:%M:%S"))

# outfile
cluster = api('get', 'cluster')
dateString = now.strftime("%Y-%m-%d")
outfile = 'oracleBackupReport-%s-%s.csv' % (cluster['name'], dateString)
f = codecs.open(outfile, 'w')

# headings
f.write('Job id,Job Name,RunId,StartTime(PST)\n')

jobs = api('get', 'data-protect/protection-groups?isDeleted=false&isActive=true&includeTenants=true&environments=kOracle', v=2)

daysAgo = timeAgo(days, 'days')


def IsMultiAttemptPendingReplication(run):
  if len(run['objects']) < 0:
    print('Not able to get attempt details.');
    return;

  if 'replicationInfo' in run:
    for replicaInfo in run['replicationInfo']['replicationTargetResults']:
        if replicaInfo['status'] == "Succeeded":
            print('Run %s ignored as replication done' % run['id'])
            return
       if replicaInfo['status'] == "Canceled":
            print('Run %s ignored as replication already cancelled' % run['id'])
            return
  for object in run['objects']:
    if not 'localSnapshotInfo' in object:
        print('Not able to get attempt details as no snap info.');
        return;
    if 'localBackupInfo' not in run:
        print('Not able to get attempt details as no snap info.');
        return;
    localBackupInfo = run['localBackupInfo']
    runStartTime = localBackupInfo['startTimeUsecs']
    localSnapshotInfo = object['localSnapshotInfo']
    if object['localSnapshotInfo']['failedAttempts'] is not None:
        #print(localSnapshotInfo)
        if localSnapshotInfo['snapshotInfo']['status'] != 'kSuccessful':
            continue
        failedAttempts=object['localSnapshotInfo']['failedAttempts']
        print('Run %s is multiattempt for source %s' % (run['id'], object['object']['name']))
        url="/protection/group/run/replication/" + run['protectionGroupId'] + "/" + run['id']
        f.write('%s,%s,%s,%s(%s)\n' % (run['protectionGroupId'], run['protectionGroupName'], run['id'], runStartTime, usecsToDate(runStartTime)))
        return

for job in sorted(jobs['protectionGroups'], key=lambda job: job['name'].lower()):
    if jobname != '' and job['name'] != jobname:
        continue

    print(job['name'])
    endUsecs = nowUsecs
    while 1:
        runs = api('get', 'data-protect/protection-groups/%s/runs?numRuns=%s&startTimeUsecs=%s&endTimeUsecs=%s&includeTenants=true&includeObjectDetails=true' % (job['id'], numruns, daysAgo, endUsecs), v=2)
        if len(runs['runs']) > 0:
            endUsecs = runs['runs'][-1]['localBackupInfo']['startTimeUsecs'] - 1
        else:
            break
        for run in runs['runs']:
            runtype = run['localBackupInfo']['runType'][1:]
            if runtype != 'Log' or includelogs:
                IsMultiAttemptPendingReplication(run)
                    if lastrunonly:
                        break
f.close()
print('\nOutput saved to %s\n' % outfile)
