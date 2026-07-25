import os
import importlib.util
from unittest.mock import MagicMock, patch

LAMBDA_PATH = os.path.join(os.path.dirname(__file__), '..', 'lambda', 'on_disconnect', 'lambda_function.py')


def load_module():
    spec = importlib.util.spec_from_file_location("on_disconnect_module", LAMBDA_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@patch.dict(os.environ, {'CONNECTIONS_TABLE': 'test-connections'})
@patch('boto3.resource')
def test_on_disconnect_removes_connection_id(mock_boto_resource):
    mock_table = MagicMock()
    mock_boto_resource.return_value.Table.return_value = mock_table

    lambda_function = load_module()

    event = {
        'requestContext': {'connectionId': 'abc123'}
    }

    response = lambda_function.lambda_handler(event, {})

    mock_table.delete_item.assert_called_once_with(Key={'connection_id': 'abc123'})
    assert response['statusCode'] == 200
