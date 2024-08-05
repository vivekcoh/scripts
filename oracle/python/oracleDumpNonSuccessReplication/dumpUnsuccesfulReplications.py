#!/usr/bin/env python
"""base V2 example"""

# import pyhesity wrapper module
from pyhesity import *
from datetime import datetime
import codecs

def ValidateOpType(opname):
  validOpname = ['dumppending', 'cancelpending', 'dumpunsuccessful']
  if opname not in validOpname:
    print('Opname should be one of %s' % validOpname)
    exit(1)

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
parser.add_argument('-n', '--numruns', type=int, default=1000)
parser.add_argument('-y', '--days', type=int, default=1)
parser.add_argument('-o', '--lastrunonly', action='store_true')
parser.add_argument('-l', '--onlylogs', action='store_true')
parser.add_argument('-j', '--jobname', type=str, default=None)
parser.add_argument('-L', '--joblist', type=str, required=False)   # text file
parser.add_argument('-I', '--jobidlist', type=str, required=False)   # text file of job ids
parser.add_argument("-O", '--opname', type=str, required=True)

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
jobname=args.jobname
joblist = args.joblist
jobidlist = args.jobidlist
opname=args.opname
ValidateOpType(opname)

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
outfile = 'oracleUnsuccessful-replications-%s-%s.csv' % (cluster['name'], dateString)
f = codecs.open(outfile, 'a')

# headings
f.write('Job id,Job Name,RunId,StartTime(PST)\n')

jobs = api('get', 'data-protect/protection-groups?isDeleted=false&isActive=true&includeTenants=true&environments=kOracle', v=2)

daysAgo = timeAgo(days, 'days')

def IsCancelledReplication(run):
  if 'localBackupInfo' not in run:
        print('Not able to get attempt details as no snap info.');
        return;
  if 'isLocalSnapshotsDeleted' in run and run['isLocalSnapshotsDeleted']:
    return
  localBackupInfo = run['localBackupInfo']
  runStartTime = localBackupInfo['startTimeUsecs']
  if 'replicationInfo' in run:
    for replicaInfo in run['replicationInfo']['replicationTargetResults']:
        if replicaInfo['status'] == "Succeeded":
            #print('Run %s ignored as replication done' % run['id'])
            return
        if replicaInfo['status'] == "Running":
            #print('Run %s ignored as replication running' % run['id'])
            return
        if replicaInfo['status'] == "Canceled":
            print('Adding Cancelled replication %s to list' % run['id'])
            #print(run)
            f.write('%s,%s,%s,%s(%s)\n' % (run['protectionGroupId'], run['protectionGroupName'], run['id'], runStartTime, usecsToDate(runStartTime)))
            return

def IsFailedReplication(run):
  #print(run)
  if 'localBackupInfo' not in run:
        print('Not able to get attempt details as no snap info.');
        return;
  if 'isLocalSnapshotsDeleted' in run and run['isLocalSnapshotsDeleted']:
    return
  localBackupInfo = run['localBackupInfo']
  runStartTime = localBackupInfo['startTimeUsecs']
  if 'replicationInfo' in run:
    for replicaInfo in run['replicationInfo']['replicationTargetResults']:
        if replicaInfo['status'] == "Succeeded":
            #print('Run %s ignored as replication done' % run['id'])
            return
        if replicaInfo['status'] == "Running":
            #print('Run %s ignored as replication running' % run['id'])
            return
        if replicaInfo['status'] == "Failed":
            print('Adding Failed replication %s to list' % run['id'])
            #print(run)
            f.write('%s,%s,%s,%s(%s)\n' % (run['protectionGroupId'], run['protectionGroupName'], run['id'], runStartTime, usecsToDate(runStartTime)))
            return

def IsPendingReplication(run):
  #print(run)
  if 'localBackupInfo' not in run:
        print('Not able to get attempt details as no snap info.');
        return;
  if 'isLocalSnapshotsDeleted' in run and run['isLocalSnapshotsDeleted']:
    return
  localBackupInfo = run['localBackupInfo']
  runStartTime = localBackupInfo['startTimeUsecs']
  if 'replicationInfo' in run:
    for replicaInfo in run['replicationInfo']['replicationTargetResults']:
        if replicaInfo['status'] == "Succeeded":
            #print('Run %s ignored as replication done' % run['id'])
            return
        if replicaInfo['status'] == "Running":
            print('Adding Running replication %s to list' % run['id'])
            f.write('%s,%s,%s,%s(%s)\n' % (run['protectionGroupId'], run['protectionGroupName'], run['id'], runStartTime, usecsToDate(runStartTime)))
            return
        if replicaInfo['status'] == "Failed":
            #print('Skipping Failed replication %s to list' % run['id'])
            return

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

jobnames = gatherList(jobname, joblist, name='jobs', required=False)
jobids = gatherList(None, jobidlist, name='jobids', required=False)
for job in sorted(jobs['protectionGroups'], key=lambda job: job['name'].lower()):
    if len(jobnames) != 0 and job['name'].lower() not in [j.lower() for j in jobnames]:
        print(job['name'])
        print(1)
        continue

    if len(jobids) != 0 and job['id'].split(':')[-1] not in jobids:
        print(job['name'])
        print(2)
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
            if runtype != 'Log' and onlylogs:
                continue
            if opname == 'dumppending':
              IsPendingReplication(run)
            elif opname == 'dumpunsuccessful':
              IsFailedReplication(run)
              IsCancelledReplication(run)
            if lastrunonly:
                break
f.close()
print('\nOutput saved to %s\n' % outfile)
