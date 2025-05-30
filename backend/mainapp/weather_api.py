import base64
import sqlite3
import threading
import time
from datetime import datetime, timedelta, timezone

from django.db.utils import OperationalError

from .models import WeatherData
from dotenv import dotenv_values

env_values = dotenv_values("mainapp/bird.env")

CLIENT_ID = env_values['CLIENT_ID']
CLIENT_SECRET = env_values['CLIENT_SECRET']

import requests


# Function to get the access token
def get_access_token():
    # Encode the credentials in Base64
    credentials = f"{CLIENT_ID}:{CLIENT_SECRET}"
    encoded_credentials = base64.b64encode(credentials.encode("utf-8")).decode("utf-8")
    encoded_credentials = encoded_credentials[:-1] + "="

    # Define the API request
    url = "https://api.srgssr.ch/oauth/v1/accesstoken?grant_type=client_credentials"
    headers = {
        "Authorization": f"Basic {encoded_credentials}",
        "Content-Type": "application/x-www-form-urlencoded"
    }

    data = {
        'client_id': CLIENT_ID,
        'client_secret': CLIENT_SECRET
    }

    response = requests.post(url, headers=headers, data=data, allow_redirects=True)

    if response.status_code == 200:
        # Extract access token from the response
        token_data = response.json()
        access_token = token_data.get('access_token')
        return access_token
    else:
        print("Failed to get access token:", response.status_code, response.text)
        return None


# Function to get location data for ZIP code 3012
def get_location_data(access_token, zip_code):
    url = f"https://api.srgssr.ch/srf-meteo/v2/geolocationNames?zip={zip_code}"
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(url, headers=headers, allow_redirects=True)

    if response.status_code == 200:
        # Process and print the location data
        location_data = response.json()
        id = location_data[0]["geolocation"]["id"]
    else:
        print("Failed to retrieve location data:", response.status_code, response.text)
        return None
    return id


def get_weather_forecast(access_token, geolocation_id):
    url = f"https://api.srgssr.ch/srf-meteo/v2/forecastpoint/{geolocation_id}"
    headers = {
        'Authorization': f'Bearer {access_token}'
    }
    response = requests.get(url, headers=headers, allow_redirects=True)

    if response.status_code == 200:
        forecast_data = response.json()
        # Get the current time and round to the next full hour
        current_time = datetime.now(timezone.utc)  # Use UTC for consistency
        next_hour = (current_time + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)

        # Convert to the correct ISO format with timezone offset
        next_hour_iso = next_hour.isoformat(timespec='seconds')

        # Loop through the 'hours' list to find the entry closest to the next hour
        for entry in forecast_data["hours"]:
            # Convert the 'date_time' to a datetime object
            entry_time = datetime.fromisoformat(entry["date_time"])

            # Check if the entry's time matches the next hour
            if entry_time == next_hour:
                return entry.get('TTT_C', 'N/A')
    else:
        print("Failed to retrieve weather forecast:", response.status_code, response.text)
        return None


# Function to store sensor data in the database
def store_weather_data(temperature):
    try:
        WeatherData.objects.create(
            temperature=temperature,
        )
    except (OperationalError, sqlite3.OperationalError):
        pass


# Background thread for temperature/humidity logging (runs every 60s)
def periodic_data_logger():
    # Register interrupt for motion detection (FALLING or RISING can be used)
    while True:
        access_token = get_access_token()  # Get the access token
        if access_token:
            # id = get_location_data(access_token, 3012)  # Use the token to fetch weather data in Bern
            id = "46.9548,7.4320"  # id of Bern
            temperature = get_weather_forecast(access_token, id)
            if temperature is not None:
                store_weather_data(temperature)
        time.sleep(60 * 60)


# Start background thread
data_thread = threading.Thread(target=periodic_data_logger, daemon=True)
data_thread.start()
