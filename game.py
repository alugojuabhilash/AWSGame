import json
import random
import os
import boto3
from datetime import datetime
import logging
from decimal import Decimal
from boto3.dynamodb.conditions import Key

# Custom JSON encoder to handle Decimal
class DecimalEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return int(obj) if obj % 1 == 0 else float(obj)
        return super(DecimalEncoder, self).default(obj)

# Initialize AWS services
dynamodb = boto3.resource('dynamodb')
sns = boto3.client('sns')
ssm = boto3.client('ssm')
cloudwatch = boto3.client('cloudwatch')

# Initialize logger
logger = logging.getLogger()
logger.setLevel(logging.INFO)

class Game:
    def __init__(self):
        self.scores_table = dynamodb.Table(os.environ['SCORES_TABLE'])
        self.sns_topic_arn = os.environ['SNS_TOPIC_ARN']
        
    def get_game_config(self):
        try:
            response = ssm.get_parameter(Name='/game/config', WithDecryption=True)
            return json.loads(response['Parameter']['Value'])
        except Exception as e:
            logger.error(f"Error getting game config: {str(e)}")
            return {"min": 1, "max": 100}

    def generate_number(self):
        config = self.get_game_config()
        return random.randint(config["min"], config["max"])

    def save_score(self, player_name, attempts, timestamp):
        try:
            self.scores_table.put_item(
                Item={
                    'player_name': player_name,
                    'attempts': attempts,
                    'timestamp': timestamp
                }
            )
            
            # Publish high score notification if attempts is low
            if attempts <= 5:
                self.publish_high_score(player_name, attempts)
                
            # Send metrics to CloudWatch
            self.record_metrics(attempts)
            
        except Exception as e:
            logger.error(f"Error saving score: {str(e)}")

    def get_leaderboard(self):
        try:
            response = self.scores_table.scan(
                ProjectionExpression="player_name, attempts",
                Limit=10
            )
            # Convert Decimal to int for attempts
            items = response['Items']
            for item in items:
                if isinstance(item.get('attempts'), Decimal):
                    item['attempts'] = int(item['attempts'])
            return sorted(items, key=lambda x: x['attempts'])
        except Exception as e:
            logger.error(f"Error getting leaderboard: {str(e)}")
            return []

    def publish_high_score(self, player_name, attempts):
        try:
            message = f"New high score! Player {player_name} won in {attempts} attempts!"
            sns.publish(
                TopicArn=self.sns_topic_arn,
                Message=message,
                Subject='New High Score!'
            )
        except Exception as e:
            logger.error(f"Error publishing to SNS: {str(e)}")

    def record_metrics(self, attempts):
        try:
            cloudwatch.put_metric_data(
                Namespace='GameMetrics',
                MetricData=[
                    {
                        'MetricName': 'AttemptsToWin',
                        'Value': attempts,
                        'Unit': 'Count'
                    }
                ]
            )
        except Exception as e:
            logger.error(f"Error recording metrics: {str(e)}")

def lambda_handler(event, context):
    game = Game()
    
    # Define CORS headers
    cors_headers = {
        'Access-Control-Allow-Origin': os.environ.get('CORS_ORIGIN', '*'),
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'OPTIONS,POST,GET',
        'Access-Control-Allow-Credentials': 'true'
    }
    
    # Log API request
    logger.info(f"Received event: {json.dumps(event)}")
    
    try:
        # Handle OPTIONS request for CORS
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({'message': 'OK'})
            }

        # Verify user is authenticated
        if 'requestContext' not in event or 'authorizer' not in event['requestContext']:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'message': 'Unauthorized'})
            }

        # Get player info from Cognito authorizer
        try:
            player_name = event['requestContext']['authorizer']['claims']['email']
        except KeyError:
            logger.error("Unable to get player email from claims")
            player_name = "anonymous"

        # Check if this is a new game request (no body) or a guess
        if 'body' not in event or not event['body']:
            # Start new game
            config = game.get_game_config()
            target_number = game.generate_number()
            logger.info(f"New game started with target number: {target_number}")
            
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'message': f'Welcome to the Number Guessing Game! I have selected a number between {config["min"]} and {config["max"]}.',
                    'gameId': str(target_number),
                    'leaderboard': game.get_leaderboard()
                }, cls=DecimalEncoder)
            }
        
        # Handle guess
        try:
            body = json.loads(event['body'])
            guess = int(body.get('guess', 0))
            target = int(body.get('gameId', 0))
            attempts = int(body.get('attempts', 0)) + 1
            
            logger.info(f"Player: {player_name}, Guess: {guess}, Target: {target}, Attempts: {attempts}")

            if guess == target:
                # Save score when player wins
                game.save_score(player_name, attempts, datetime.now().isoformat())
                message = f'Congratulations! You found the number {target} in {attempts} attempts!'
                game_over = True
            elif guess < target:
                message = f'Try higher! Your guess ({guess}) is too low.'
                game_over = False
            else:
                message = f'Try lower! Your guess ({guess}) is too high.'
                game_over = False

            response_body = {
                'message': message,
                'attempts': attempts,
                'gameOver': game_over,
                'leaderboard': game.get_leaderboard() if game_over else None,
                'lastGuess': guess,
                'gameId': str(target)
            }

            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps(response_body, cls=DecimalEncoder)
            }
            
        except (ValueError, TypeError, json.JSONDecodeError) as e:
            logger.error(f"Error processing guess: {str(e)}")
            return {
                'statusCode': 400,
                'headers': cors_headers,
                'body': json.dumps({'message': 'Invalid guess format'})
            }
        
    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({'message': f'Internal server error: {str(e)}'})
        }
