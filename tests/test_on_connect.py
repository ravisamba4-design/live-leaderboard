import os
import importlib.util
from unittest.mock import MagicMock, patch

LAMBDA_PATH = os.path.join(os.path.dirname(__file__), '..', 'lambda', 'on_connect', 'lambda_function.py')


def load_module():
    spec = importlib.util.spec_from_file_location("on_connect_module", LAMBDA_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@patch.dict(os.environ, {'CONNECTIONS_TABLE': 'test-connections'})
@patch('boto3.resource')
def test_on_connect_saves_connection_id(mock_boto_resource):
    mock_table = MagicMock()
    mock_boto_resource.return_value.Table.return_value = mock_table

    lambda_function = load_module()

    event = {
        'requestContext': {'connectionId': 'abc123'}
    }

    response = lambda_function.lambda_handler(event, {})

    mock_table.put_item.assert_called_once_with(Item={'connection_id': 'abc123'})
    assert response['statusCode'] == 200
