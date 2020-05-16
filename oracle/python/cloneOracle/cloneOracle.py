#!/usr/bin/env python
"""Clone an Oracle DB Using python"""

### usage: ./cloneOracle.py -v mycluster \
#                           -u myuser \
#                           -d mydomain.net \
#                           -ss oracleprod.mydomain.net \
#                           -ts oracledev.mydomain.net \
#                           -sd proddb \
#                           -td devdb \
#                           -oh /home/oracle/app/oracle/product/11.2.0/dbhome_1 \
#                           -ob /home/oracle/app/oracle \
#                           -w

### import pyhesity wrapper module
from pyhesity import *
from time import sleep

### command line arguments
import argparse
parser = argparse.ArgumentParser()
parser.add_argument('-v', '--vip', type=str, required=True)  # Cohesity cluster name or IP
parser.add_argument('-u', '--username', type=str, required=True)  # Cohesity Username
parser.add_argument('-d', '--domain', type=str, default='local')  # Cohesity User Domain
parser.add_argument('-ss', '--sourceserver', type=str, required=True)  # name of source oracle server
parser.add_argument('-sd', '--sourcedb', type=str, required=True)  # name of source oracle DB
parser.add_argument('-ts', '--targetserver', type=str, default=None)  # name of target oracle server
parser.add_argument('-td', '--targetdb', type=str, default=None)  # name of target oracle DB
parser.add_argument('-oh', '--oraclehome', type=str, required=True)  # oracle home path on target
parser.add_argument('-ob', '--oraclebase', type=str, required=True)  # oracle base path on target
parser.add_argument('-lt', '--logtime', type=str, default=None)  # oracle base path on target
parser.add_argument('-l', '--latest', action='store_true')
parser.add_argument('-w', '--wait', action='store_true')  # wait for completion

args = parser.parse_args()

vip = args.vip
username = args.username
domain = args.domain
sourceserver = args.sourceserver
sourcedb = args.sourcedb

if args.targetserver is None:
    targetserver = sourceserver
else:
    targetserver = args.targetserver

if args.targetdb is None:
    targetdb = sourcedb
else:
    targetdb = args.targetdb

oraclehome = args.oraclehome
oraclebase = args.oraclebase
logtime = args.logtime
latest = args.latest
wait = args.wait

### authenticate
apiauth(vip, username, domain)

### search for view to clone
searchResults = api('get', '/searchvms?entityTypes=kOracle&vmName=%s' % sourcedb)
if len(searchResults) == 0:
    print("SourceDB %s not found" % sourcedb)
    exit()

### narrow search results to the correct server
searchResults = [searchResult for searchResult in searchResults['vms'] if sourceserver.lower() in [x.lower() for x in searchResult['vmDocument']['objectAliases']]]
if len(searchResults) == 0:
    print("SourceDB %s on Server %s not found" % (sourcedb, sourceserver))
    exit()

### find latest snapshot

latestdb = sorted(searchResults, key=lambda result: result['vmDocument']['versions'][0]['snapshotTimestampUsecs'], reverse=True)[0]
version = latestdb['vmDocument']['versions'][0]
ownerId = latestdb['vmDocument']['objectId']['entity']['oracleEntity']['ownerId']

### find target host
entities = api('get', '/appEntities?appEnvType=19')
for entity in entities:
    if entity['appEntity']['entity']['displayName'].lower() == targetserver.lower():
        targetEntity = entity
if targetEntity is None:
    print "target server not found"
    exit()

# handle log replay
versionNum = 0
validLogTime = False

if logtime is not None or latest is True:
    if logtime is not None:
        logusecs = dateToUsecs(logtime)
    dbversions = latestdb['vmDocument']['versions']

    for version in dbversions:
        # find db date before log time
        GetRestoreAppTimeRangesArg = {
            "type": 19,
            "restoreAppObjectVec": [
                {
                    "appEntity": latestdb['vmDocument']['objectId']['entity'],
                    "restoreParams": {
                        "sqlRestoreParams": {
                            "captureTailLogs": True
                        },
                        "oracleRestoreParams": {
                            "alternateLocationParams": {
                                "oracleDBConfig": {
                                    "controlFilePathVec": [],
                                    "enableArchiveLogMode": True,
                                    "redoLogConf": {
                                        "groupMemberVec": [],
                                        "memberPrefix": "redo",
                                        "sizeMb": 20
                                    },
                                    "fraSizeMb": 2048
                                }
                            },
                            "captureTailLogs": False,
                            "secondaryDataFileDestinationVec": [
                                {}
                            ]
                        }
                    }
                }
            ],
            "ownerObjectVec": [
                {
                    "jobUid": latestdb['vmDocument']['objectId']['jobUid'],
                    "jobId": latestdb['vmDocument']['objectId']['jobId'],
                    "jobInstanceId": version['instanceId']['jobInstanceId'],
                    "startTimeUsecs": version['instanceId']['jobStartTimeUsecs'],
                    "entity": {
                        "id": ownerId
                    },
                    "attemptNum": 1
                }
            ]
        }
        logTimeRange = api('post', '/restoreApp/timeRanges', GetRestoreAppTimeRangesArg)

        if latest is True:
            if 'timeRangeVec' not in logTimeRange['ownerObjectTimeRangeInfoVec'][0]:
                logTime = None
                latest = None
                break

        if 'timeRangeVec' in logTimeRange['ownerObjectTimeRangeInfoVec'][0]:
            logStart = logTimeRange['ownerObjectTimeRangeInfoVec'][0]['timeRangeVec'][0]['startTimeUsecs']
            logEnd = logTimeRange['ownerObjectTimeRangeInfoVec'][0]['timeRangeVec'][0]['endTimeUsecs']

            if latest is True:
                logusecs = logEnd - 1000000
                validLogTime = True
                break

            if logStart <= logusecs and logusecs <= logEnd:
                validLogTime = True
                break

        versionNum += 1

cloneParams = {
    "name": "Clone-Oracle",
    "action": "kCloneApp",
    "restoreAppParams": {
        "type": 19,
        "ownerRestoreInfo": {
            "ownerObject": {
                "jobUid": latestdb['vmDocument']['objectId']['jobUid'],
                "jobId": latestdb['vmDocument']['objectId']['jobId'],
                "jobInstanceId": version['instanceId']['jobInstanceId'],
                "startTimeUsecs": version['instanceId']['jobStartTimeUsecs'],
                "entity": {
                    "id": latestdb['vmDocument']['objectId']['entity']['parentId'],
                }
            },
            "ownerRestoreParams": {
                "action": "kCloneVMs",
                "powerStateConfig": {}
            },
            "performRestore": False
        },
        "restoreAppObjectVec": [
            {
                "appEntity": latestdb['vmDocument']['objectId']['entity'],
                "restoreParams": {
                    "oracleRestoreParams": {
                        "alternateLocationParams": {
                            "newDatabaseName": targetdb,
                            "homeDir": oraclehome,
                            "baseDir": oraclebase
                        },
                        "captureTailLogs": False,
                        "secondaryDataFileDestinationVec": [
                            {}
                        ]
                    },
                    "targetHost": targetEntity['appEntity']['entity'],
                    "targetHostParentSource": {
                        "id": targetEntity['appEntity']['entity']['id']
                    }
                }
            }
        ]
    }
}

# apply log replay time
if validLogTime is True:
    cloneParams['restoreAppParams']['restoreAppObjectVec'][0]['restoreParams']['oracleRestoreParams']['restoreTimeSecs'] = int(logusecs / 1000000)
else:
    if logtime is not None:
        print('LogTime of %s is out of range' % logtime)
        print('Available range is %s to %s' % (usecsToDate(logStart), usecsToDate(logEnd)))
        exit(1)

### execute the clone task
response = api('post', '/cloneApplication', cloneParams)

if 'errorCode' in response:
    exit(1)

print("Cloning DB %s as %s..." % (sourcedb, targetdb))
taskId = response['restoreTask']['performRestoreTaskState']['base']['taskId']
status = api('get', '/restoretasks/%s' % taskId)

if wait is True:
    finishedStates = ['kCanceled', 'kSuccess', 'kFailure']
    while(status[0]['restoreTask']['performRestoreTaskState']['base']['publicStatus'] not in finishedStates):
        sleep(1)
        status = api('get', '/restoretasks/%s' % taskId)
    if(status[0]['restoreTask']['performRestoreTaskState']['base']['publicStatus'] == 'kSuccess'):
        print('Clone Completed Successfully')
        exit(0)
    else:
        print('Clone ended with state: %s' % status[0]['restoreTask']['performRestoreTaskState']['base']['publicStatus'])
        exit(1)
