clickhouse-report
=========

Role for scheduled clickhouse reports

Role Variables
--------------

To do

Example Playbook
----------------
```
- hosts: servers
  become: yes
  gather_facts: yes

  vars:
    clickhouse_report_db_host: "localhost"
    clickhouse_report_db_user: "backup_user"
    clickhouse_report_db_password: "backup_password"
    clickhouse_report_db_name: "test"
    clickhouse_report_local_dir: "/root/clickhouse-report"
    clickhouse_report_use_compression: true
    clickhouse_report_delete_locally: true
    clickhouse_report_skip_when_delete_locally: 5
    clickhouse_report_remote_storage: "s3"
    clickhouse_report_bucket_name: "backups"
    clickhouse_report_bucket_dir: "clickhouse-reports"
      
  roles:
    - clickhouse-report
```
