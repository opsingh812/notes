import boto3
import logging
from botocore.exceptions import ClientError
import psycopg2
from psycopg2 import sql

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS resources
dynamodb = boto3.resource('dynamodb')
ses_client = boto3.client('ses')

# Environment variables
RDS_HOST = 'your-rds-endpoint'  # Replace with your RDS endpoint
RDS_DB = 'your-database-name'  # Replace with your database name
RDS_USER = 'your-username'  # Replace with your RDS username
RDS_PASSWORD = 'your-password'  # Replace with your RDS password

def scan_table_for_new_records(table, status_attribute, status_value):
    """
    Scan a DynamoDB table for records with a specific status.

    Args:
        table (dynamodb.Table): The DynamoDB table object.
        status_attribute (str): The attribute name for status.
        status_value (str): The status value to filter.

    Returns:
        list: A list of matching items.
    """
    try:
        response = table.scan(
            FilterExpression=f"{status_attribute} = :val",
            ExpressionAttributeValues={':val': status_value}
        )
        items = response.get('Items', [])
        logger.info(f"Found {len(items)} records with status '{status_value}'.")
        return items
    except ClientError as e:
        logger.error(f"Error scanning table: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error during scanning: {e}")
        raise

def perform_action_in_rds(record_id):
    """
    Perform an action in RDS based on the record ID.

    Args:
        record_id (str): The record identifier.

    Returns:
        bool: True if the action is successful, False otherwise.
    """
    try:
        connection = psycopg2.connect(
            host=RDS_HOST,
            database=RDS_DB,
            user=RDS_USER,
            password=RDS_PASSWORD
        )
        cursor = connection.cursor()

        # Example RDS action: Insert or update a record
        query = sql.SQL("INSERT INTO your_table (record_id) VALUES (%s) ON CONFLICT (record_id) DO NOTHING")
        cursor.execute(query, (record_id,))
        connection.commit()

        logger.info(f"Action performed successfully for record ID: {record_id}")
        cursor.close()
        connection.close()
        return True
    except Exception as e:
        logger.exception(f"Error performing action in RDS for record ID {record_id}: {e}")
        return False

def update_record_status(table, record_key, status_attribute, new_status):
    """
    Update the status of a record in DynamoDB.

    Args:
        table (dynamodb.Table): The DynamoDB table object.
        record_key (dict): The key of the record to update.
        status_attribute (str): The status attribute name.
        new_status (str): The new status value.

    Returns:
        None
    """
    try:
        table.update_item(
            Key=record_key,
            UpdateExpression=f"SET {status_attribute} = :val",
            ExpressionAttributeValues={':val': new_status}
        )
        logger.info(f"Updated record {record_key} status to '{new_status}'.")
    except ClientError as e:
        logger.error(f"Error updating record {record_key}: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while updating record: {e}")
        raise

def send_email(recipient, subject, body):
    """
    Send an email using SES.

    Args:
        recipient (str): The email recipient.
        subject (str): The email subject.
        body (str): The email body.

    Returns:
        None
    """
    try:
        ses_client.send_email(
            Source='your-email@example.com',  # Replace with your verified SES email
            Destination={'ToAddresses': [recipient]},
            Message={
                'Subject': {'Data': subject},
                'Body': {'Text': {'Data': body}}
            }
        )
        logger.info(f"Email sent to {recipient}: {subject}")
    except ClientError as e:
        logger.error(f"Error sending email to {recipient}: {e}")
        raise
    except Exception as e:
        logger.exception(f"Unexpected error while sending email: {e}")
        raise

def lambda_handler(event, context):
    """
    Main Lambda function handler.

    Args:
        event (dict): The event payload.
        context: The Lambda context.

    Returns:
        dict: The response.
    """
    try:
        # Table name and attributes
        table_name = 'YourTableName'  # Replace with your table name
        status_attribute = 'status'
        new_status = 'new'
        table = dynamodb.Table(table_name)

        # Scan for new records
        records = scan_table_for_new_records(table, status_attribute, new_status)
        if not records:
            return {"statusCode": 200, "body": "No records with status 'new'."}

        # Process each record
        for record in records:
            record_id = record.get('record_id')  # Replace with your record's unique key attribute
            if not record_id:
                logger.warning("Record missing 'record_id'. Skipping.")
                continue

            success = perform_action_in_rds(record_id)

            # Update record status in DynamoDB
            record_key = {'record_id': record_id}  # Replace with your table's primary key schema
            new_status_value = 'complete' if success else 'failed'
            update_record_status(table, record_key, status_attribute, new_status_value)

            # Send email
            if success:
                send_email('client@example.com', 'Action Completed', f"Record {record_id} processed successfully.")
            else:
                send_email('infra-team@example.com', 'Action Failed', f"Failed to process record {record_id}.")

        return {"statusCode": 200, "body": "Processing completed."}

    except Exception as e:
        logger.exception(f"Unexpected error in Lambda: {e}")
        send_email('infra-team@example.com', 'Lambda Function Error', f"An error occurred: {str(e)}")
        return {"statusCode": 500, "body": "An unexpected error occurred."}
