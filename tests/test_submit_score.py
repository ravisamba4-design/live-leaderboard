import os
import json
import importlib.util
from unittest.mock import MagicMock, patch

LAMBDA_PATH = os.path.join(os.path.dirname(__file__), '..', 'lambda', 'submit_score', 'lambda_function.py')


def load_module():
    spec = importlib.util.spec_from_file_location("submit_score_module", LAMBDA_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def make_event(player_name, reaction_time_ms):
    return {
        'body': json.dumps({
            'player_name': player_name,
            'reaction_time_ms': reaction_time_ms
        }),
        'requestContext': {
            'domainName': 'test.execute-api.eu-north-1.amazonaws.com',
            'stage': 'prod'
        }
    }


@patch.dict(os.environ, {'CONNECTIONS_TABLE': 'test-connections', 'SCORES_TABLE': 'test-scores'})
@patch('boto3.client')
@patch('boto3.resource')
def test_submit_score_saves_new_best(mock_boto_resource, mock_boto_client):
    mock_scores_table = MagicMock()
    mock_connections_table = MagicMock()

    mock_scores_table.get_item.return_value = {}
    mock_scores_table.scan.return_value = {'Items': [
        {'player_id': 'Ravi', 'reaction_time_ms': 250}
    ]}
    mock_connections_table.scan.return_value = {'Items': []}

    def table_side_effect(name):
        if name == 'test-scores':
            return mock_scores_table
        return mock_connections_table

    mock_boto_resource.return_value.Table.side_effect = table_side_effect

    lambda_function = load_module()

    event = make_event('Ravi', 250)
    response = lambda_function.lambda_handler(event, {})

    mock_scores_table.put_item.assert_called_once()
    assert response['statusCode'] == 200


@patch.dict(os.environ, {'CONNECTIONS_TABLE': 'test-connections', 'SCORES_TABLE': 'test-scores'})
@patch('boto3.client')
@patch('boto3.resource')
def test_submit_score_ignores_worse_time(mock_boto_resource, mock_boto_client):
    mock_scores_table = MagicMock()
    mock_connections_table = MagicMock()

    mock_scores_table.get_item.return_value = {'Item': {'player_id': 'Ravi', 'reaction_time_ms': 200}}
    mock_scores_table.scan.return_value = {'Items': [
        {'player_id': 'Ravi', 'reaction_time_ms': 200}
    ]}
    mock_connections_table.scan.return_value = {'Items': []}

    def table_side_effect(name):
        if name == 'test-scores':
            return mock_scores_table
        return mock_connections_table

    mock_boto_resource.return_value.Table.side_effect = table_side_effect

    lambda_function = load_module()

    event = make_event('Ravi', 300)
    response = lambda_function.lambda_handler(event, {})

    mock_scores_table.put_item.assert_not_called()
    assert response['statusCode'] == 200


@patch.dict(os.environ, {'CONNECTIONS_TABLE': 'test-connections', 'SCORES_TABLE': 'test-scores'})
@patch('boto3.client')
@patch('boto3.resource')
def test_submit_score_missing_fields_returns_400(mock_boto_resource, mock_boto_client):
    mock_boto_resource.return_value.Table.return_value = MagicMock()

    lambda_function = load_module()

    event = {
        'body': json.dumps({'player_name': 'Ravi'}),
        'requestContext': {'domainName': 'x', 'stage': 'prod'}
    }
    response = lambda_function.lambda_handler(event, {})

    assert response['statusCode'] == 400
