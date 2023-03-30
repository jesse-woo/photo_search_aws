import json
import os
import boto3
from opensearchpy import OpenSearch, RequestsHttpConnection
from requests_aws4auth import AWS4Auth
from botocore.exceptions import ClientError
from inflection import singularize
import re
import uuid

REGION = 'us-east-1'
HOST = 'search-photos-werz5sjzmsxjmnxz2ctmkbbtiu.us-east-1.es.amazonaws.com'
INDEX = 'photos'

session = boto3.Session()

def generate_presigned_url(bucket, object_key):
    s3_client = boto3.client('s3')
    try:
        url = s3_client.generate_presigned_url(
            'get_object',
            Params={
                'Bucket': bucket,
                'Key': object_key},
            ExpiresIn=3600,
        )
    except ClientError as e:
        print(e)
        print("Couldn't generate presigned url")
        return None
    print("The pre-signed url is", url)
    return url

def query_photos(keywords):
    keywords = clean_keywords(keywords)
    print("Cleaned up keywords:", keywords)
    
    to_query = {
        "query": {
            "bool": {
                "must": [
                    {"match": {"labels": {"query": keyword, "boost": 1.0}}}
                    for keyword in keywords
                ]
            }
        },
        "size": 100,
        "_source": ["objectKey", "bucket", "createdTimestamp", "labels"],
    }
    '''
    # this will search with logical OR
    to_query = {
        "query": {
            "bool": {
                "minimum_should_match": 1,
                    "should":
                        [
                            {"match": {"labels": {"query": keyword, "boost": 1.0}}}
                            for keyword in keywords
                        ]
            }
        },
        "size": 100,
        "_source": ["objectKey", "bucket", "createdTimestamp", "labels"],
    }
    '''
    print("The query is", to_query)
    client = OpenSearch(hosts=[{
        'host': HOST,
        'port': 443
    }],
                        http_auth=get_awsauth(REGION, 'es'),
                        use_ssl=True,
                        verify_certs=True,
                        connection_class=RequestsHttpConnection)
    
    res = client.search(index=INDEX, body=to_query)
    print("res is", res)

    hits = res['hits']['hits']
    results = []
    '''
    for hit in hits:
        results.append(hit['_source'])
    '''

    for hit in hits:
        bucket = hit['_source']['bucket']
        object_key = hit['_source']['objectKey']
        url = generate_presigned_url(bucket, object_key)
        if url:
            hit['_source']['url'] = url
            results.append(hit['_source'])
    print("The results are:", results)
    return results
    
    
def clean_keywords(keywords):
    keywords = [
        part.strip()
        for keyword in keywords
        for part in re.sub(r"(?: and | in | the | a )", ",", keyword).split(",")
        ]
    keywords = list(filter(bool, keywords))
    keywords = [re.sub(r"\s+", "", keyword) for keyword in keywords]
    keywords = [keyword.lower() for keyword in keywords]
    keywords = [singularize(keyword) for keyword in keywords]
  
    return keywords


def get_awsauth(region, service):
    cred = session.get_credentials()
    return AWS4Auth(cred.access_key,
                    cred.secret_key,
                    region,
                    service,
                    session_token=cred.token)
                    
                    
                    
def lex_keywords(user_str):
    lex_client = boto3.client('lexv2-runtime', region_name=REGION)
    if not user_str:
        raise ValueError("No string to disambiguate")
        
    sess_id = str(uuid.uuid4())
    
    response = lex_client.recognize_text(
        botId = "41LW6D3J1B",
        botAliasId = "2SB4OODZ8G",
        localeId="en_US",
        sessionId = sess_id,
        text = user_str
    )
    
    msg = response.get("messages", [])
    print("RESPONSE",response)
    print("msg_from_lex",msg)
    
    slots = response["interpretations"][0]["intent"]["slots"]
    print("SLOTS:",slots)
    
    keywords = [slot["value"]["interpretedValue"] for slot in slots.values() if slot and "value" in slot]
    
    return keywords
    

def lambda_handler(event, context):

    user_query = event.get("q")
    
    cors = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Credientials": "true",
        "Access-Control-Allow-Methods": "GET, OPTIONS, PUT",
        "Access-Control-Allow-Headers": "Content-Type, x-amz-meta-customLabels"
    }
        
    try:
        keywords = lex_keywords(user_query)

        print("Keywords:", keywords)
        if not keywords:
            return {
                "statusCode": 200,
                "headers": cors,
                "body": "[]"
            }
            
        print("You are about to query photos")
        results = query_photos(keywords)
    
        return {
            'statusCode': 200,
            'headers': cors,
            'body': json.dumps(results)
        }
    
    except Exception as e:
        print(e)
        return {
            'statusCode' : 500,
            'headers': cors,
            'body': json.dumps('Backend error')
        }
        