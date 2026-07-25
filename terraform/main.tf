terraform {
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.0"
    }
    archive = {
      source  = "hashicorp/archive"
      version = "~> 2.0"
    }
  }
}

provider "aws" {
  region = var.aws_region
}

# ---------- DynamoDB tables ----------

resource "aws_dynamodb_table" "connections" {
  name         = "${var.project_name}-connections"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "connection_id"

  attribute {
    name = "connection_id"
    type = "S"
  }
}

resource "aws_dynamodb_table" "scores" {
  name         = "${var.project_name}-scores"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "player_id"

  attribute {
    name = "player_id"
    type = "S"
  }
}

# ---------- Package Lambda code ----------

data "archive_file" "on_connect_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/on_connect"
  output_path = "${path.module}/on_connect.zip"
}

data "archive_file" "on_disconnect_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/on_disconnect"
  output_path = "${path.module}/on_disconnect.zip"
}

data "archive_file" "submit_score_zip" {
  type        = "zip"
  source_dir  = "${path.module}/../lambda/submit_score"
  output_path = "${path.module}/submit_score.zip"
}

# ---------- IAM role shared by all three Lambdas ----------

resource "aws_iam_role" "lambda_role" {
  name = "${var.project_name}-lambda-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Action = "sts:AssumeRole"
      Effect = "Allow"
      Principal = {
        Service = "lambda.amazonaws.com"
      }
    }]
  })
}

resource "aws_iam_role_policy" "lambda_policy" {
  name = "${var.project_name}-lambda-policy"
  role = aws_iam_role.lambda_role.id

  policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Effect   = "Allow"
        Action   = ["logs:CreateLogGroup", "logs:CreateLogStream", "logs:PutLogEvents"]
        Resource = "arn:aws:logs:*:*:*"
      },
      {
        Effect = "Allow"
        Action = [
          "dynamodb:PutItem",
          "dynamodb:GetItem",
          "dynamodb:DeleteItem",
          "dynamodb:Scan"
        ]
        Resource = [
          aws_dynamodb_table.connections.arn,
          aws_dynamodb_table.scores.arn
        ]
      },
      {
        Effect   = "Allow"
        Action   = ["execute-api:ManageConnections"]
        Resource = "arn:aws:execute-api:${var.aws_region}:*:*/*"
      }
    ]
  })
}

# ---------- Lambda functions ----------

resource "aws_lambda_function" "on_connect" {
  function_name    = "${var.project_name}-on-connect"
  filename         = data.archive_file.on_connect_zip.output_path
  source_code_hash = data.archive_file.on_connect_zip.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_role.arn
  timeout          = 10

  environment {
    variables = {
      CONNECTIONS_TABLE = aws_dynamodb_table.connections.name
    }
  }
}

resource "aws_lambda_function" "on_disconnect" {
  function_name    = "${var.project_name}-on-disconnect"
  filename         = data.archive_file.on_disconnect_zip.output_path
  source_code_hash = data.archive_file.on_disconnect_zip.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_role.arn
  timeout          = 10

  environment {
    variables = {
      CONNECTIONS_TABLE = aws_dynamodb_table.connections.name
    }
  }
}

resource "aws_lambda_function" "submit_score" {
  function_name    = "${var.project_name}-submit-score"
  filename         = data.archive_file.submit_score_zip.output_path
  source_code_hash = data.archive_file.submit_score_zip.output_base64sha256
  handler          = "lambda_function.lambda_handler"
  runtime          = "python3.12"
  role             = aws_iam_role.lambda_role.arn
  timeout          = 15

  environment {
    variables = {
      CONNECTIONS_TABLE = aws_dynamodb_table.connections.name
      SCORES_TABLE       = aws_dynamodb_table.scores.name
    }
  }
}

# ---------- WebSocket API Gateway ----------

resource "aws_apigatewayv2_api" "websocket" {
  name                       = "${var.project_name}-ws-api"
  protocol_type              = "WEBSOCKET"
  route_selection_expression = "$request.body.action"
}

resource "aws_apigatewayv2_stage" "prod" {
  api_id      = aws_apigatewayv2_api.websocket.id
  name        = "prod"
  auto_deploy = true
}

# --- $connect route ---

resource "aws_apigatewayv2_integration" "connect" {
  api_id           = aws_apigatewayv2_api.websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.on_connect.invoke_arn
}

resource "aws_apigatewayv2_route" "connect" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "$connect"
  target    = "integrations/${aws_apigatewayv2_integration.connect.id}"
}

resource "aws_lambda_permission" "connect_permission" {
  statement_id  = "AllowAPIGatewayInvokeConnect"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.on_connect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/*/*"
}

# --- $disconnect route ---

resource "aws_apigatewayv2_integration" "disconnect" {
  api_id           = aws_apigatewayv2_api.websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.on_disconnect.invoke_arn
}

resource "aws_apigatewayv2_route" "disconnect" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "$disconnect"
  target    = "integrations/${aws_apigatewayv2_integration.disconnect.id}"
}

resource "aws_lambda_permission" "disconnect_permission" {
  statement_id  = "AllowAPIGatewayInvokeDisconnect"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.on_disconnect.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/*/*"
}

# --- submitScore route ---

resource "aws_apigatewayv2_integration" "submit_score" {
  api_id           = aws_apigatewayv2_api.websocket.id
  integration_type = "AWS_PROXY"
  integration_uri  = aws_lambda_function.submit_score.invoke_arn
}

resource "aws_apigatewayv2_route" "submit_score" {
  api_id    = aws_apigatewayv2_api.websocket.id
  route_key = "submitScore"
  target    = "integrations/${aws_apigatewayv2_integration.submit_score.id}"
}

resource "aws_lambda_permission" "submit_score_permission" {
  statement_id  = "AllowAPIGatewayInvokeSubmitScore"
  action        = "lambda:InvokeFunction"
  function_name = aws_lambda_function.submit_score.function_name
  principal     = "apigateway.amazonaws.com"
  source_arn    = "${aws_apigatewayv2_api.websocket.execution_arn}/*/*"
}

# ----------
output "websocket_url" {
  value = "${aws_apigatewayv2_stage.prod.invoke_url}"
}
