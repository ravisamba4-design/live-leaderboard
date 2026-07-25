import json
import boto3
import os
from datetime import datetime, timezone
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
CONNECTIONS_TABLE = os.environ.get('CONNECTIONS_TABLE')
SCORES_TABLE = os.environ.get('SCORES_TABLE')

connections_table = dynamodb.Table(CONNECTIONS_TABLE)
scores_table = dynamodb.Table(SCORES_TABLE)


class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super().default(obj)


def lambda_handler(event, context):
    body = json.loads(event.get('body', '{}'))
    player_name = body.get('player_name')
    reaction_time_ms = body.get('reaction_time_ms')

    if not player_name or reaction_time_ms is None:
        return {'statusCode': 400, 'body': 'player_name and reaction_time_ms are required'}

    # 1. Save the score (only keep each player's BEST time)
    existing = scores_table.get_item(Key={'player_id': player_name}).get('Item')

    if not existing or reaction_time_ms < existing.get('reaction_time_ms', float('inf')):
        scores_table.put_item(Item={
            'player_id': player_name,
            'reaction_time_ms': reaction_time_ms,
            'updated_at': datetime.now(timezone.utc).isoformat()
        })

    # 2. Fetch the current top 10 leaderboard
    result = scores_table.scan()
    items = result.get('Items', [])
    items.sort(key=lambda x: x['reaction_time_ms'])
    top_scores = items[:10]

    # 3. Push the updated leaderboard to every connected client
    domain = event['requestContext']['domainName']
    stage = event['requestContext']['stage']
    endpoint_url = f"https://{domain}/{stage}"

    apigw_management = boto3.client('apigatewaymanagementapi', endpoint_url=endpoint_url)

    connections = connections_table.scan().get('Items', [])
    payload = json.dumps({'leaderboard': top_scores}, cls=DecimalEncoder).encode('utf-8')

    for conn in connections:
        connection_id = conn['connection_id']
        try:
            apigw_management.post_to_connection(
                ConnectionId=connection_id,
                Data=payload
            )
        except apigw_management.exceptions.GoneException:
            # This connection is stale (client disconnected without us catching it) — clean it up
            connections_table.delete_item(Key={'connection_id': connection_id})

    return {'statusCode': 200, 'body': 'Score submitted'}
