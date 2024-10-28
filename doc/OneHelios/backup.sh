#!/bin/bash

##########################################
#
# OneHelios Backup - version  2024.10.28a
# Last Updated By: Brian Seltzer
#
##########################################

## constants
LOG_FILE='backup-service-log.txt'

## parameters
BACKUP_POSTGRES=0
BACKUP_MONGODB=0
BACKUP_ELASTIC=0
EXPIRE_BACKUPS=0
DO_ALL=0
NO_MAIL=0
ELASTIC_BACKUP_REPOSITORY='elastic-backups-repo'

function usage {
    programname=$0
    cat <<HELP_USAGE
    usage: $programname [-aemnpx] [-t to_address] [-s set_name] [-k key_name] [-v key_value]"
        -a            (backup all services - the default)
        -e            (backup Elasticsearch)
        -m            (backup MongoDB)
        -n            (do not send email report)
        -p            (backup Postgres)
        -x            (expire old backups)
        -t to_address (email address to send report to)
        -s set_name   (name of backup set - auto generated by default)
        -k key_name   (arbitrary key name to store)
        -v key_value  (arbitrary value to store for key name)
HELP_USAGE
    exit 1
}

while getopts "t:s:k:v:pmexan" flag
    do
        case "${flag}" in
            t) MAIL_TO=${OPTARG};;
            s) SET_NAME=${OPTARG};;
            p) BACKUP_POSTGRES=1;;
            m) BACKUP_MONGODB=1;;
            e) BACKUP_ELASTIC=1;;
            k) KEY_NAME=${OPTARG};;
            v) KEY_VALUE=${OPTARG};;
            x) EXPIRE_BACKUPS=1;;
            a) DO_ALL=1;;
            n) NO_MAIL=1;;
            *) usage | tee $LOG_FILE; exit 1;;
        esac
    done

if [[ -z $KEY_NAME ]] && [[ $BACKUP_POSTGRES -eq 0 ]] && [[ $BACKUP_MONGODB -eq 0 ]] && [[ $BACKUP_ELASTIC -eq 0 ]] && [[ $EXPIRE_BACKUPS -eq 0 ]]; then
    DO_ALL=1
fi
if [[ $DO_ALL -eq 1 ]]; then
    BACKUP_POSTGRES=1
    BACKUP_MONGODB=1
    BACKUP_ELASTIC=1
    EXPIRE_BACKUPS=1
fi

if [[ -z $MAIL_TO ]]; then
    MAIL_TO=$SEND_TO
fi

finish () {
    if [[ $BACKUP_POSTGRES -eq 1 ]] || [[ $BACKUP_MONGODB -eq 1 ]] || [[ $BACKUP_ELASTIC -eq 1 ]] || [[ $DO_ALL -eq 1 ]]; then
        if [[ $NO_MAIL -eq 0 ]]; then
            echo "account email {" > ~/.mailrc
            echo "    set from=\"$SEND_FROM\"" >> ~/.mailrc
            echo "    set ssl-verify=ignore" >> ~/.mailrc
            echo "    set mta=smtp://$SMTP_SERVER:$SMTP_PORT" >> ~/.mailrc
            if [[ "$SMTP_STARTTLS" == "true" ]]; then
                echo "    set smtp-use-starttls" >> ~/.mailrc
            fi
            if [[ "$SMTP_USER" != "" ]]; then
                echo "    set smtp-auth=login" >> ~/.mailrc
                echo "    set smtp-auth-user=$SMTP_USER" >> ~/.mailrc
                echo "    set smtp-auth-password=$SMTP_PASSWORD" >> ~/.mailrc
            fi
            echo "}"  >> ~/.mailrc
            if [[ $1 -eq 0 ]]; then
                cat $LOG_FILE | mailx -A email -a $LOG_FILE -s "OneHelios Successful Backup Report ($APPLIANCE_NAME)" $SEND_TO 2>/dev/null
            else
                cat $LOG_FILE | mailx -A email -a $LOG_FILE -s "OneHelios ** Failed ** Backup Report ($APPLIANCE_NAME)" $SEND_TO 2>/dev/null
            fi
            # cat $LOG_FILE | mailx -a $LOG_FILE -s "OneHelios Backup Report" -S mta=smtp://${SMTP_SERVER}:${SMTP_PORT} -S from=${SEND_FROM} ${MAIL_TO} 2>/dev/null
        fi
    fi
    exit $1
}

if [ -z "${POSTGRES_SERVICE_HOST}" ]; then
    POSTGRES_SERVICE_HOST="$POSTGRES_RW_SERVICE_HOST"
fi

if [ -z "${S3_HOST}" ] || [ -z "${S3_ACCESS_KEY}" ] || [ -z "${S3_SECRET_KEY}" ] || [ -z "${S3_LOCATION}" ] || [ -z "${S3_BUCKET}" ] || [ -z "${S3_RETENTION}" ] || [ -z "${ELASTIC_BACKUP_REPOSITORY}" ]
then
    echo -e " ** Environment is not set! **" | tee $LOG_FILE
    finish 1
fi

# create elastic backup repo
REPO_RESULT=$(curl -X 'GET' "http://$ELASTICSEARCH_ES_HTTP_SERVICE_HOST:$ELASTICSEARCH_ES_HTTP_SERVICE_PORT/_snapshot" 2>dev/null)
if [[ "$REPO_RESULT" != *$ELASTIC_BACKUP_REPOSITORY* ]]; then
    echo -e "\n -- Creating Elastic Snapshot Repository\n" | tee $LOG_FILE
    curl -X PUT -k \
        --url "http://$ELASTICSEARCH_ES_HTTP_SERVICE_HOST:$ELASTICSEARCH_ES_HTTP_SERVICE_PORT/_snapshot/$ELASTIC_BACKUP_REPOSITORY" \
        -H 'Content-type: application/json' \
        -d '{
        "type": "s3",
        "settings": {
            "bucket": "'${S3_BUCKET}'",
            "access_key": "'${S3_ACCESS_KEY}'",
            "secret_key": "'${S3_SECRET_KEY}'",
            "endpoint": "'${S3_HOST}'",
            "path_style_access": "true",
            "protocol": "https"
        }
    }'
fi

echo ""

## Current Date
EPOC_DATE=$(date +"%s")
HUMAN_DATE=$(date -d @$EPOC_DATE +%Y-%m-%d_%H:%M:%S)
RETENTION_SECONDS=$(($S3_RETENTION * 86400))

if [ -z "${SET_NAME}" ]
then
    SET_NAME=$EPOC_DATE.$HUMAN_DATE
fi

echo -e " -- Backup set name: $SET_NAME\n" | tee $LOG_FILE

BACKUP_STATUS='Success'
BACKUP_EXIT_CODE=0

## MongoDB Backup
if [[ $BACKUP_MONGODB -eq 1 ]]; then
    echo -e " -- MongoDB backup started\n" | tee -a $LOG_FILE
    mongodump $MONGODB_CONNECT_STRING --username=$MONGODB_USER --password=$MONGODB_PASSWORD --archive | s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate put - s3://$S3_BUCKET/DUMPS/$SET_NAME/mongodump  | tee -a $LOG_FILE
    MONGO_STATUS=$?
    if [[ $MONGO_STATUS -ne 0 ]]; then
        BACKUP_STATUS='Failure'
        BACKUP_EXIT_CODE=1
    else
        FOUND_MONGO='false'
        for line in $(s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate ls s3://$S3_BUCKET/DUMPS/$SET_NAME/); do
            if [[ "$line" == "s3://$S3_BUCKET/DUMPS/$SET_NAME/mongodump" ]]; then
                FOUND_MONGO='true'
            fi
        done
        if [[ "$FOUND_MONGO" != 'true' ]]; then
            echo -e "\n ** Mongo backup failed! **" | tee -a $LOG_FILE
            BACKUP_STATUS='Failed'
            BACKUP_EXIT_CODE=1
        else
            echo -e "\n -- Mongo backup verified" | tee -a $LOG_FILE
        fi
    fi
fi

## Postgres Backup
if [[ $BACKUP_POSTGRES -eq 1 ]]; then
    echo -e " -- Postgres backup started\n" | tee -a $LOG_FILE
    echo "$POSTGRES_SERVICE_HOST:$POSTGRES_SERVICE_PORT:postgres:$POSTGRES_USER:$PGPASSWORD" > .pgpass
    pg_dumpall -h $POSTGRES_SERVICE_HOST -U $POSTGRES_USER -w | s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate put - s3://$S3_BUCKET/DUMPS/$SET_NAME/pgdump | tee -a $LOG_FILE
    PG_STATUS=$?
    if [[ $PG_STATUS -ne 0 ]]; then
        BACKUP_STATUS='Failed'
        BACKUP_EXIT_CODE=2
    else
        FOUND_POSTGRES='false'
        for line in $(s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate ls s3://$S3_BUCKET/DUMPS/$SET_NAME/); do
            if [[ "$line" == "s3://$S3_BUCKET/DUMPS/$SET_NAME/pgdump" ]]; then
                FOUND_POSTGRES='true'
            fi
        done
        if [[ "$FOUND_POSTGRES" != 'true' ]]; then
            echo -e "\n ** Postgres backup failed! **" | tee -a $LOG_FILE
            BACKUP_STATUS='Failed'
            BACKUP_EXIT_CODE=2
        else
            echo -e "\n -- Postgres backup verified" | tee -a $LOG_FILE
        fi
    fi
fi

## Elastic Backup
if [[ $BACKUP_ELASTIC -eq 1 ]]; then
    echo -e " -- Elastic backup started" | tee -a $LOG_FILE
    ELASTIC_RESULT=$(curl -X 'PUT' "http://$ELASTICSEARCH_ES_HTTP_SERVICE_HOST:$ELASTICSEARCH_ES_HTTP_SERVICE_PORT/_snapshot/$ELASTIC_BACKUP_REPOSITORY/$SET_NAME"  -H 'Content-Type: application/json' -d '{"include_global_state": true}' 2>/dev/null)
    ELASTIC_STATUS=$?

    if [[ $ELASTIC_STATUS -ne 0 ]]; then
        echo -e "\n$ELASTIC_RESULT\n" | tee -a $LOG_FILE
        echo -e " ** Elastic backup failed! **" | tee -a $LOG_FILE
        BACKUP_STATUS='Failed'
        BACKUP_EXIT_CODE=3
    else
        ELASTIC_SUCCESS=$(echo $ELASTIC_RESULT | jq -r '.accepted')
        if [[ $ELASTIC_SUCCESS == 'true' ]]; then
            # wait for snapshot to finish
            SNAP_FINISHED=false
            while [ "$SNAP_FINISHED" == "false" ]; do
                sleep 10
                SNAP_INFO=$(curl -X 'GET' "http://$ELASTICSEARCH_ES_HTTP_SERVICE_HOST:$ELASTICSEARCH_ES_HTTP_SERVICE_PORT/_cat/snapshots/$ELASTIC_BACKUP_REPOSITORY" 2>/dev/null | grep "$SET_NAME")
                if [[ $SNAP_INFO != *PROGRESS* ]]; then
                    SNAP_FINISHED=true
                fi
            done
            echo -e "\n$SNAP_INFO\n" | tee -a $LOG_FILE
            if [[ $SNAP_INFO == *"SUCCESS"* ]]; then
                echo -e " -- Elastic backup verified" | tee -a $LOG_FILE
            else
                echo -e " ** Elastic backup failed! **" | tee -a $LOG_FILE
                BACKUP_STATUS='Failed'
                BACKUP_EXIT_CODE=3
            fi
        else
            echo -e "\n$ELASTIC_RESULT\n" | tee -a $LOG_FILE
            echo -e " ** Elastic backup failed! **" | tee -a $LOG_FILE
            BACKUP_STATUS='Failed'
            BACKUP_EXIT_CODE=3
        fi
    fi
fi

## store key/value
if [ -z "${KEY_NAME+x}" ] || [ -z "${KEY_VALUE+x}" ]
then
    true
else
    echo -e " --- storing $KEY_NAME"
    echo "$KEY_VALUE" | s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate put - s3://$S3_BUCKET/DUMPS/$SET_NAME/$KEY_NAME 2>/dev/null
fi

## Exit if backup failed
if [[ $BACKUP_EXIT_CODE -gt 0 ]]; then
    echo -e " ** Exiting with BACKUP_EXIT_CODE: $BACKUP_EXIT_CODE ($BACKUP_STATUS) **" | tee -a $LOG_FILE
    finish $BACKUP_EXIT_CODE
fi

# save backup set
if [[ $BACKUP_POSTGRES -eq 1 ]] || [[ $BACKUP_MONGODB -eq 1 ]] || [[ $BACKUP_ELASTIC -eq 1 ]] || [[ $DO_ALL -eq 1 ]]; then
    cat $LOG_FILE | s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate put - s3://$S3_BUCKET/BACKUP_SETS/$SET_NAME 2>/dev/null
fi

## Expire Old Backups
if [[ $EXPIRE_BACKUPS -eq 1 ]]; then
    echo -e " -- Expiring old backups - retention: $S3_RETENTION days\n" | tee -a $LOG_FILE

    ## Get backup set list
    s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate ls s3://$S3_BUCKET/BACKUP_SETS/ | while read -r line; do
        lineparts=($line)
        BACKUP_DATE="${lineparts[0]} ${lineparts[1]}"
        EPOC_BACKUP_DATE="$(date -d "${BACKUP_DATE}" +%s)"
        S3_PATH=${lineparts[3]}
        arr=(${S3_PATH//\// })
        SET_NAME=${arr[3]}
        DUMP_PATH=${S3_PATH/BACKUP_SETS/"DUMPS"}
        ELAPSED_SECONDS=$(($EPOC_DATE - $EPOC_BACKUP_DATE))
        ELAPSED_DAYS=$(($ELAPSED_SECONDS / 86400))
        if (( $ELAPSED_SECONDS > $RETENTION_SECONDS )); then
            echo -e "    $SET_NAME - $BACKUP_DATE ($ELAPSED_DAYS days old) --> Expiring" | tee -a $LOG_FILE
            # delete dump folder
            s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate del -r $DUMP_PATH > /dev/null 2>&1
            # delete elastic snapshot
            DEL_SNAP=$(curl -X 'DELETE' "http://$ELASTICSEARCH_ES_HTTP_SERVICE_HOST:$ELASTICSEARCH_ES_HTTP_SERVICE_PORT/_snapshot/$ELASTIC_BACKUP_REPOSITORY/$SET_NAME" > /dev/null 2>&1)
            # delete backup set
            s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY --region=$S3_LOCATION --no-check-certificate del $S3_PATH > /dev/null 2>&1
        else
            echo -e "    $SET_NAME - $BACKUP_DATE ($ELAPSED_DAYS days old)" | tee -a $LOG_FILE
        fi
    done
fi

echo -e "\n -- Exiting with BACKUP_EXIT_CODE: $BACKUP_EXIT_CODE ($BACKUP_STATUS)\n" | tee -a $LOG_FILE

finish $BACKUP_EXIT_CODE
