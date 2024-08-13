# Backup Using rsync and a Remote Adapter Script

Warning: this code is provided on a best effort basis and is not in any way officially supported or sanctioned by Cohesity. The code is intentionally kept simple to retain value as example code. The code in this repository is provided as-is and the author accepts no liability for damages resulting from its use.

This bash script can be used as a pre-script in a remote adapter job to backup any data.

## Download the script

```bash
# Begin download commands
curl -O https://raw.githubusercontent.com/cohesity/community-automation-samples/main/remoteAdapter/rsyncBackup/backup.sh
chmod +x backup.sh
# End download commands
```

## Create a Cohesity View

Create a Cohesity View to store the backups for your GitHub repositories. Recommend that you use the "File Share" template, which enables NFS access (required) and uses the TestAndDevHigh performance profile (recommended).

## Choose a Linux Host to Run the Script

Select a Linux host where we can run the bash script. The script will mount the view and rsync files/folders into the View. On the Linux host, create or select the desired user account and place the bash file in the user's home directory.

Note that the selected user will require password-less sudo access in order to mount/unmount the View when the script runs.

## Review and Modify the Bash Script

The script contains some example commands to use rsync to copy data onto the NFS mounted Cohesity view. Modify the commands as needed.

## Create a Remote Adapter Protection Group

After the script is working, we can create a Remote Adapter protection group to run our script on a schedule.

When creating the protection group:

* Select our Linux host and username
* Copy the cluster ssh public key provided and add this to the ~/.ssh/authorized_keys file of our Linux user
* Select the desired Policy, which will define the frequency and retention of the backups.
* Select our Cohesity View
* In the script information fields, enter the full path to the script, for example: `/home//backup.sh`
