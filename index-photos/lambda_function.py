import json
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
import urllib.parse
import datetime
from requests_aws4auth import AWS4Auth

REGION = 'us-east-1'
HOST = "search-opensearch-photos-ctyskw2pihv2jjow4k6adja6h4.us-east-1.es.amazonaws.com"
INDEX = 'photos'

session = boto3.Session()

def get_awsauth(region, service):
    cred = session.get_credentials()
    return AWS4Auth(cred.access_key,
                    cred.secret_key,
                    region,
                    service,
                    session_token=cred.token)

def index_photo(b, name):
    client = OpenSearch(hosts=[{
        'host': HOST,
        'port': 443
    }],
                        http_auth=get_awsauth(REGION, 'es'),
                        use_ssl=True,
                        verify_certs=True,
                        connection_class=RequestsHttpConnection)

    res = client.create(index=INDEX, body=b, id=name)

def lambda_handler(event, context):
    s3_client = boto3.client('s3')
    rek_client = boto3.client('rekognition')
    bucket = bucket = event['Records'][0]['s3']['bucket']['name']
    # key_name should be the name of the photo
    key_name = urllib.parse.unquote_plus(event['Records'][0]['s3']['object']['key'], encoding='utf-8')
    
    
    # code adapted from https://serverlessland.com/snippets/integration-s3-to-lambda?utm_source=aws&utm_medium=link&utm_campaign=python&utm_id=docsamples
    try:
        response = s3_client.head_object(Bucket = bucket, Key = key_name)
        
        custom_labels = []
        if response["Metadata"]:
            print("METADATA IS:", response["Metadata"])
            
            if response["Metadata"]['customlabels']:
                json_labels = json.loads(response["Metadata"]['customlabels'])
                to_append = json_labels['labels']
                print("the custom labels are:", to_append)
                custom_labels = to_append
                
        
        print("The custom labels are", custom_labels)
        timestamp = str(response["LastModified"])
        img_object = {'S3Object': {'Bucket': bucket, 'Name': key_name}}
    
        label_response = rek_client.detect_labels(
            Image=img_object)
        
        # build list of only the labels from the response
        labels = []
        for l in label_response["Labels"]:
            labels.append(l['Name'])
        
        print("the Rekognition labels are", labels)
        
        for c in custom_labels:
            labels.append(c)
        
        print("Full set of labels are", labels)
        
        to_idx = {
            "objectKey": key_name, 
            "bucket": bucket, 
            "createdTimestamp": timestamp, 
            "labels": labels
        }
        
        index = json.dumps(to_idx, default=str)
        index_photo(index, key_name)
        print("this is what you indexed", index)
        
    except Exception as e:
        print(e)
        print('Error getting object {} from bucket {}. Make sure they exist and your bucket is in the same region as this function.'.format(key_name, bucket))
        raise e
    
    return {
        'statusCode': 200,
        'body': json.dumps('Successfully indexed photo')
    }


