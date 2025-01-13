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
            # Create a short name from email
            short_name = player_name.split('@')[0]  # Gets the part before @
            # Optional: Make it even shorter by taking first 8 chars
            display_name = short_name[:8] + "..." if len(short_name) > 8 else short_name
            
            # Create a userId from player_name and timestamp
            user_id = f"{player_name}_{timestamp}"
            
            self.scores_table.put_item(
                Item={
                    'userId': user_id,
                    'player_name': player_name,  # Original email
                    'display_name': display_name,  # Short name for display
                    'attempts': attempts,
                    'timestamp': timestamp
                }
            )
            
            # Publish high score notification if attempts is low
            if attempts <= 5:
                self.publish_high_score(display_name, attempts)  # Use display_name here
                
            # Send metrics to CloudWatch
            self.record_metrics(attempts)
            
        except Exception as e:
            logger.error(f"Error saving score: {str(e)}")

    def get_leaderboard(self):
        try:
            response = self.scores_table.scan(
                ProjectionExpression="display_name, attempts",  # Changed to display_name
                Limit=10
            )
            # Convert Decimal to int for attempts
            items = response['Items']
            for item in items:
                if isinstance(item.get('attempts'), Decimal):
                    item['attempts'] = int(item['attempts'])
            
            # Sort by attempts in ascending order
            sorted_items = sorted(items, key=lambda x: x['attempts'])
            logger.info(f"Leaderboard items: {sorted_items}")
            return sorted_items
        except Exception as e:
            logger.error(f"Error getting leaderboard: {str(e)}")
            return []

    def get_leaderboard1(self):
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
            
            # Sort by attempts in ascending order
            sorted_items = sorted(items, key=lambda x: x['attempts'])
            logger.info(f"Leaderboard items: {sorted_items}")
            return sorted_items
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
    # Define CORS headers
    cors_headers = {
        'Access-Control-Allow-Origin': os.environ.get('CORS_ORIGIN', '*'),
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'OPTIONS,POST',
        'Access-Control-Allow-Credentials': 'true'
    }
    
    game = Game()
    
    try:
        # Handle OPTIONS request for CORS
        if event.get('httpMethod') == 'OPTIONS':
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({'message': 'OK'})
            }

        # Get player info from Cognito authorizer
        if 'requestContext' not in event or 'authorizer' not in event['requestContext']:
            return {
                'statusCode': 401,
                'headers': cors_headers,
                'body': json.dumps({'message': 'Unauthorized'})
            }

        try:
            player_name = event['requestContext']['authorizer']['claims']['email']
            logger.info(f"Player authenticated: {player_name}")
        except KeyError:
            logger.error("Unable to get player email from claims")
            player_name = "anonymous"

        # Parse request body
        body = {}
        if event.get('body'):
            body = json.loads(event['body'])
            logger.info(f"Request body: {body}")

        # Check if this is a new game request or a guess
        if not body:  # New game request
            # Generate new target number
            target_number = game.generate_number()
            config = game.get_game_config()
            
            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'message': f'Game started! Guess a number between {config["min"]} and {config["max"]}.',
                    'gameId': str(target_number),  # Store target as gameId
                    'leaderboard': game.get_leaderboard()
                }, cls=DecimalEncoder)
            }
        else:  # This is a guess
            guess = int(body.get('guess', 0))
            target = int(body.get('gameId', 0))
            attempts = int(body.get('attempts', 1))

            logger.info(f"Player: {player_name}, Guess: {guess}, Target: {target}, Attempts: {attempts}")

            # Validate target number
            if target == 0:
                return {
                    'statusCode': 400,
                    'headers': cors_headers,
                    'body': json.dumps({
                        'message': 'Invalid game state. Please start a new game.'
                    })
                }

            # Compare guess with target
            if guess == target:
                game.save_score(player_name, attempts, datetime.now().isoformat())
                message = f'Congratulations! You found the number {target} in {attempts} attempts!'
                game_over = True
            elif guess < target:
                message = f'Try higher! Your guess ({guess}) is too low.'
                game_over = False
            else:
                message = f'Try lower! Your guess ({guess}) is too high.'
                game_over = False

            return {
                'statusCode': 200,
                'headers': cors_headers,
                'body': json.dumps({
                    'message': message,
                    'attempts': attempts,
                    'gameOver': game_over,
                    'leaderboard': game.get_leaderboard() if game_over else None,
                    'gameId': str(target)
                }, cls=DecimalEncoder)
            }

    except Exception as e:
        logger.error(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': cors_headers,
            'body': json.dumps({
                'message': f'Internal server error: {str(e)}'
            })
        }

