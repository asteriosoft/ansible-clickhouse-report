#!/usr/bin/python3

import sys
import os
import shutil
import tarfile
import logging
import subprocess
import time
import requests
import boto3
from botocore.errorfactory import ClientError
from google.cloud import storage
from google import api_core

logging.basicConfig(format="%(asctime)s:%(levelname)s:%(message)s", level=logging.INFO)

reportDir = "{{ clickhouse_report_local_dir }}"
reportDiskThreshold = "{{ clickhouse_report_disk_space_threshold }}"
reportQuery = "{{ clickhouse_report_query }}"
remoteStorage = "{{ clickhouse_report_remote_storage }}"
bucketName = "{{ clickhouse_report_bucket_name }}"
reportName = {{ "f\'" + clickhouse_report_filename_template + "\'" }}
reportFormat = "{{ clickhouse_report_file_format }}"
bucketDir = "{{ clickhouse_report_bucket_dir }}"
deleteLocally = {{ clickhouse_report_delete_locally }}
skipWhenDelete = {{ clickhouse_report_skip_when_delete_locally }}
clickhouselHost = "{{ clickhouse_report_db_host }}"
clickhouselUser = "{{ clickhouse_report_db_user}}"
clickhouselPassword = "{{ clickhouse_report_db_password  }}"
clickhouselDBName = "{{ clickhouse_report_db_name }}"
telergamApiToken = "{{ clickhouse_report_telergam_api_token }}"
telegramChatId = "{{ clickhouse_report_telegram_chat_id }}"

if remoteStorage == "gcs":
    # Use GOOGLE_APPLICATION_CREDENTIALS env variable for GCP access
    gcs_client = storage.Client()

if remoteStorage == "s3":
    # Use AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY and AWS_DEFAULT_REGION env variables for AWS access
    s3_client = boto3.client('s3')

def send_to_telegram(api_token,chat_id,message):
    if ( api_token and chat_id ):
        api_url = f"https://api.telegram.org/bot{api_token}/sendMessage"
        try:
            requests.post(api_url, json={"chat_id": chat_id, "text": message})
        except Exception as error:
            logging.error(f"Failed send message to telegram with error: {error}")

def disk_space_check(path, threshold):
    total, used, free = shutil.disk_usage(path)
    percent = 100 * used / total
    if percent > float(threshold):
        logging.error(f"Backup disk is more than {percent} percent full. Skip backup creation")
        send_to_telegram(telergamApiToken, telegramChatId, "Clickhouse-report: Not enough disk space to create a clickhouse report")
        sys.exit(1)

def create_clickhouse_report(clickhouse_db_host, clichouse_user, clickhouse_password, clickhouse_db_name, report_query, report_dir, report_name, report_format):
    query = f"{report_query} INTO OUTFILE '{report_dir}/{report_name}' FORMAT {report_format}"
    cmd = f'clickhouse-client --host {clickhouse_db_host} --user {clichouse_user} --password {clickhouse_password} --database {clickhouse_db_name} --query "{query}"'
    process=subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, universal_newlines=True)
    if process.returncode == 0:
        logging.info(f"Successfully executed clickhouse query")
    else:
        logging.error(f"Clickhouse error while execute query: '{format(str(process.stdout.strip()))}'")
        send_to_telegram(telergamApiToken, telegramChatId, "Clickhouse-report: execute query failed")
        sys.exit(1)

def check_remote_exists_s3(bucket_name, bucket_dir, report_name):
    try:
        s3_client.head_bucket(Bucket=bucket_name)
    except ClientError as error:
        if error.response['Error']['Code'] == "404":
            logging.error(f"The s3 bucket {bucket_name} does not exist")
            send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: the s3 bucket {bucket_name} does not exist. Skip upload")
            sys.exit(1)
        elif error.response['Error']['Code'] == "403":
            logging.error(f"AWS boto3 client unauthorized. {format(str(error))}")
            send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: AWS boto3 client unauthorized. {format(str(error))}")
            sys.exit(1)
        else:
            logging.error(f"Exception raised. {format(str(error))}")
            send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: Exception raised. {format(str(error))}")
            sys.exit(1)
    else:
        try:
            s3_client.head_object(Bucket=bucket_name, Key=f"{bucket_dir}/{report_name}")
        except ClientError as error:
            if error.response['Error']['Code'] == "404":
                return False
            elif error.response['Error']['Code'] == "403":
                logging.error(f"AWS boto3 client unauthorized. {format(str(error))}")
                send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: AWS boto3 client unauthorized. {format(str(error))}")
                sys.exit(1)
            else:
                logging.error(f'Exception raised. {format(str(error))}')
                send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: Exception raised. {format(str(error))}")
                sys.exit(1)
        else:
            return True

def upload_to_s3(bucket_name, bucket_dir, report_name):
    if os.path.isfile(report_name):
        try: 
            s3_client.upload_file(report_name, bucket_name, f"{bucket_dir}/{report_name}")
            logging.info(f"Uploaded {report_name} to s3://{bucket_name}/{bucket_dir}")
        except boto3.exceptions.S3UploadFailedError as error:
            logging.error(f"Failed upload {report_name} to s3://{bucket_name}/{bucket_dir} with error: {format(str(error))}")
            send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: failed upload {report_name} to s3://{bucket_name}/{bucket_dir}")
            sys.exit(1)
    else:
        logging.error(f"Cant find {bucket_dir}/{report_name} locally. Skip upload")
        sys.exit(1)

def check_remote_exists_gcs(bucket_name, bucket_dir, report_name):
    try:
        bucket = gcs_client.bucket(bucket_name)
        if bucket.exists():
            stats = storage.Blob(bucket=bucket, name=f"{bucket_dir}/{report_name}").exists(gcs_client)
            return stats
        else:
            logging.error(f"The gcs bucket {bucket_name} does not exist")
            send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: the gcs bucket {bucket_name} does not exist. Skip upload")
            sys.exit(1)
    except api_core.exceptions.Forbidden as error:
        logging.error(f'Permission denied. {format(str(error))}')
        send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: permission denied. {format(str(error))}")
        sys.exit(1)
    except Exception as error:
        logging.error(f'Exception raised. {format(str(error))}')
        send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: exception raised. {format(str(error))}")
        sys.exit(1)

def upload_to_gcs(bucket_name, bucket_dir, report_name):
    bucket = gcs_client.bucket(bucket_name)
    if os.path.isfile(report_name):
        try:
            blob = bucket.blob(f"{bucket_dir}/{report_name}")
            blob.upload_from_filename(f"{report_name}")
            logging.info(f"Uploaded {report_name} to gs://{bucket_name}/{bucket_dir}")
        except Exception as error:
            logging.error(f"Failed upload {report_name} to gs://{bucket_name}/{bucket_dir} with error: {format(str(error))}")
            send_to_telegram(telergamApiToken, telegramChatId, f"Clickhouse-report: failed upload {report_name} to gs://{bucket_name}/{bucket_dir}")
            sys.exit(1)
    else:
        logging.error(f"Cant find {bucket_dir}/{report_name} locally. Skip upload")
        sys.exit(1)

def make_tarball_and_compress(report_name):
    with tarfile.open(f"{report_name}.tar.gz", "w:gz") as tar:
        tar.add(f"{report_name}", arcname=report_name)
    logging.info(f"Created compressed tarball {report_name}.tar.gz")

def delete_local_backup(backup_path):
    if os.path.isfile(backup_path):
        os.remove(backup_path)
        logging.info(f"Deleted {backup_path} locally")
    elif os.path.isdir(backup_path):
        shutil.rmtree(backup_path)
        logging.info(f"Deleted {backup_path} locally")
    else:
        logging.info(f"Cant find {backup_path} locally. Skip deletion")

def main():
    disk_space_check(reportDir, reportDiskThreshold)
    os.chdir(reportDir)
    create_clickhouse_report(clickhouselHost, clickhouselUser, clickhouselPassword, clickhouselDBName, reportQuery, reportDir, reportName, reportFormat)
    for index, file in enumerate(sorted(os.listdir(reportDir), reverse=True, key=os.path.getmtime)):
        if remoteStorage == "gcs":
            if not check_remote_exists_gcs(bucketName, bucketDir, file):
                upload_to_gcs(bucketName, bucketDir, file)
        if remoteStorage == "s3":
            if not check_remote_exists_s3(bucketName, bucketDir, file):
                upload_to_s3(bucketName, bucketDir, file)
        if deleteLocally and index >= skipWhenDelete:
            delete_local_backup(file)


if __name__ == "__main__":
    main()