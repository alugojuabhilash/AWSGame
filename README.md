**Number Guessing Game Documentation**

**Overview**

A serverless number guessing game built using AWS services where players try to guess a randomly generated number between 1 and 100.

**Architecture**
**AWS Services Used**
AWS Lambda - Game logic execution

Amazon DynamoDB - Score storage

Amazon SNS - High score notifications

AWS CloudWatch - Game metrics and logging

AWS Systems Manager Parameter Store - Game configuration

Amazon Cognito - User authentication

API Gateway - RESTful API interface

Components
1. Lambda Function (game.py)
class Game:
    def __init__(self):
        self.scores_table = dynamodb.Table(os.environ['SCORES_TABLE'])
        self.sns_topic_arn = os.environ['SNS_TOPIC_ARN']

Main components:

Game configuration management

Random number generation

Score tracking

Leaderboard management

High score notifications

Metrics recording

2. Game Flow
**Start Game**

# No request body needed
# Returns:
{
    "message": "Welcome to the Number Guessing Game!",
    "gameId": "75",  # Target number
    "leaderboard": []
}


**Make Guess**

# Request:
{
    "guess": 50,
    "gameId": "75",
    "attempts": 0
}
# Response:
{
    "message": "Try higher!",
    "attempts": 1,
    "gameOver": false,
    "lastGuess": 50,
    "gameId": "75"
}


3. Features
Persistent leaderboard

High score notifications

Game metrics tracking

User authentication

CORS support

Error handling

CloudFormation Template Structure
Resources:
  # Lambda Function
  GameFunction:
    Type: AWS::Lambda::Function
    Properties:
      Handler: game.lambda_handler
      Environment:
        Variables:
          SCORES_TABLE: !Ref ScoresTable
          SNS_TOPIC_ARN: !Ref HighScoreTopic
          CORS_ORIGIN: '*'

  # DynamoDB Table
  ScoresTable:
    Type: AWS::DynamoDB::Table
    Properties:
      AttributeDefinitions:
        - AttributeName: player_name
          AttributeType: S
      KeySchema:
        - AttributeName: player_name
          KeyType: HASH

  # SNS Topic
  HighScoreTopic:
    Type: AWS::SNS::Topic

  # API Gateway
  GameApi:
    Type: AWS::ApiGateway::RestApi

  # Cognito User Pool
  GameUserPool:
    Type: AWS::Cognito::UserPool


**API Endpoints**
POST /game
**Start New Game (no body)**

curl -X POST https://api-endpoint/game \
-H "Authorization: Bearer YOUR_ID_TOKEN"

curl -X POST https://api-endpoint/game \
-H "Authorization: Bearer YOUR_ID_TOKEN" \
-H "Content-Type: application/json" \
-d '{
    "guess": 50,
    "gameId": "75",
    "attempts": 0
}'


**Environment Variables**
SCORES_TABLE - DynamoDB table name

SNS_TOPIC_ARN - SNS topic ARN for notifications

CORS_ORIGIN - Allowed CORS origins

**Game Logic**
Player starts new game (receives target number)

Player makes guess:

If correct: Game ends, score saved

If too low: "Try higher"

If too high: "Try lower"

Score saved when player wins

High score notification if attempts ≤ 5

**Error Handling**
Invalid input validation

Authentication errors

Service errors

CORS handling

**Metrics and Monitoring**
CloudWatch metrics for attempts

Logging for debugging

High score notifications

**Security**
Cognito user authentication

API Gateway authorization

Environment variables for configuration

CORS protection

Deployment Process
Deploy CloudFormation template [1]

Configure environment variables

Set up API Gateway

Configure Cognito

**Test endpoints**

Testing
# Start new game
curl -X POST https://api-endpoint/game \
-H "Authorization: Bearer TOKEN"

# Make guess
curl -X POST https://api-endpoint/game \
-H "Authorization: Bearer TOKEN" \
-H "Content-Type: application/json" \
-d '{
    "guess": 50,
    "gameId": "75",
    "attempts": 0
}'


**Future Improvements**:
Multiple difficulty levels

Time-based scoring

Multiplayer support

Achievement system

