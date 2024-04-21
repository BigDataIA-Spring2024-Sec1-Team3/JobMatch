import boto3
import configparser
from pymongo import MongoClient

config = configparser.RawConfigParser()
config.read('configuration.properties')

def aws_connection():
    try:
        # s3 connection details
        aws_access_key = config['AWS']['access_key']
        aws_secret_key = config['AWS']['secret_key']
        bucket_name = config['s3-bucket']['bucket']

        s3_client = boto3.client(
            's3', aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)

        return s3_client, bucket_name

    except Exception as e:
        print("Exception in aws_connection function: ", e)
        return

def mongo_connection():
    try:
        client = MongoClient(config['MONGODB']['MONGODB_URL'])
        db = client[config['MONGODB']["DATABASE_NAME"]]
        return db
    except Exception as e:
        print(e)