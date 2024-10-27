FROM almalinux
RUN dnf localinstall -y https://fastdl.mongodb.org/tools/db/mongodb-database-tools-rhel93-x86_64-100.10.0.rpm
RUN dnf install -y epel-release
RUN dnf install -y postgresql
RUN dnf install -y s3cmd
RUN dnf install -y jq
RUN dnf install -y s-nail
COPY backup.sh /
COPY restore.sh /