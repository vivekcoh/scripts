# OneHelios Backup Service

## Requirements

* S3 Target - an S3 compatible object storage bucket. This can be an S3 view on a Cohesity cluster, an S3 bucket in AWS, etc.
* Access Key and Secret Key to access the bucket

## Setup

Setup requires intervention by support, who will need to enable host shell access to the OneHelios appliance so that we can SSH into it.

```bash
ssh support@myappliance -p 2222
sudo su - cohesity
```

## Create Configuration

Now we must create a file backup-config.yaml. Example:

```yaml
apiVersion: v1
stringData:
  accesskey: xHAcEUiSJYcOqD9zOQSzYE4I3QirjlWVc1mF2vjdCYh
  secretkey: yko-e81fNMPaZdgy73AWo-D7ht6lOcz9I0Rh6dqQksR
  host: 10.1.1.100:3000
  bucket: OneHelios
  location: US
  retention: "7"
  elastic-backup-repository: elastic-backups-repo
  smtp-server: "10.1.1.200"
  smtp-port: "25"
  send-from: "fromuser@mydomain.com"
  send-to: "touser@mydomain.com"
kind: Secret
metadata:
  creationTimestamp: null
  name: backup-config
```

Populate the yaml file with the appropriate values:

* Access Key to access the S3 bucket
* Secret Key to access the S3 bucket
* host where S3 bucket is located (use host:port format for non-standard port)
* Bucket name
* location (region name for AWS, otherwise this is ignored)
* retention (number of days to keep backups)
* Elastic backup reporitory name (we will create this repository later)
* SMTP relay to send email through
* SMTP port (usually port 25)
* Send from email address
* Send to enail address

Once complete, apply the yaml to Kubernetes:

```bash
kubectl apply -f backup-config.yaml -n cohesity-onehelios-onehelios
```

## Start the Backup Service Pod

Find the backup-service.yaml file and apply it to Kubernetes:

```bash
kubectl apply -f backup-service.yaml -n cohesity-onehelios-onehelios
```

Then exec into the pod:

```bash
kubectl exec --stdin --tty -n cohesity-onehelios-onehelios backup-service -- /bin/bash
```

## Test Access to S3

You can test access to your S3 bucket using the command:

```bash
s3cmd --host=$S3_HOST --access_key=$S3_ACCESS_KEY --secret_key=$S3_SECRET_KEY ls s3://$S3_BUCKET --no-check-certificate
```

Note that at this point the bucket is empty, so no items will be returned, but if no error is shown, then access is working.

## Create the Elastic S3 Repository

Review, modify and execute the create-repository.sh

```bash
curl -X PUT -k \
    --url "http://$ELASTICSEARCH_ES_HTTP_SERVICE_HOST:$ELASTICSEARCH_ES_HTTP_PORT_9200_TCP_PORT/_snapshot/$ELASTIC_BACKUP_REPOSITORY"  \
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
```

## Test the Backup

Now at the bash prompt inside the pod, we can test the backup:

```bash
./backup.sh
```

Most issues will be caused by incorrect settings in backup-config.yaml. Review and fix any settings, and if any changes are made, re-apply and restart:

```bash
kubectl apply -f backup-config.yaml -n cohesity-onehelios-onehelios
kubectl delete pod backup-service -n cohesity-onehelios-onehelios
kubectl apply -f backup-service.yaml -n cohesity-onehelios-onehelios
```

Then exec into the pod and test again:

```bash
kubectl exec --stdin --tty -n cohesity-onehelios-onehelios backup-service -- /bin/bash
```

```bash
./backup.sh
```

Once the backup is working as expected we can shutdown the pod:

```bash
kubectl delete pod backup-service -n cohesity-onehelios-onehelios
```

## Schedule Backups

Review the backup-cronjob.yaml file:

```yaml
apiVersion: batch/v1
kind: CronJob
metadata:
  name: backup
spec:
  schedule: "0 */4 * * *"
  successfulJobsHistoryLimit: 7
  failedJobsHistoryLimit: 7
  concurrencyPolicy: Forbid
  jobTemplate:
    spec:
      ttlSecondsAfterFinished: 86400
      template:
        spec:
          containers:
          - name: backup-service
            image: backup-service
            imagePullPolicy: Never
            command:
            - /bin/bash
            - -c
            - /backup.sh
            ...
```

Modify the schedule to specify the frequency of backups. The schedule is defined in CRON format. The example above backs up every 4 hours.

Also review the command. If you need to pass any command line arguments to the script, append them to the command. for example, to disable email reports add the `-n` switch:

```yaml
            command:
            - /bin/bash
            - -c
            - /backup.sh -n
```

After saving any changes, apply to Kubernetes:

```bash
kubectl apply -f backup-cronjob.yaml -n cohesity-onehelios-onehelios
```

Now the backup should run on schedule.

After the schedule has been triggered, You can review logs from completed backups:

```bash
kubectl get jobs -n cohesity-onehelios-onehelios
kubectl logs job.batch/jobname -n cohesity-onehelios-onehelios
```
