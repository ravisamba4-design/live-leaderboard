import boto3
import os

dynamodb = boto3.resource('dynamodb')
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')
table = dynamodb.Table(CONNECTIONS_TABLE)


def lambda_handler(event, context):
    connection_id = event['requestContext']['connectionId']

    table.delete_item(Key={
        'connection_id': connection_id
    })

    return {
        'statusCode': 200,
        'body': 'Disconnected'
    }
