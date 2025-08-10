#!/usr/bin/python3

import base64
import csv
import hashlib
import json
import os
import random
import re
import string
import uuid
import argparse
from collections import defaultdict
from urllib.parse import urlparse
import datetime
import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from fake_useragent import UserAgent
from future.backports.urllib.parse import parse_qs
from rich import print_json, print
from rich.console import Console
import time

from medihunter_notifiers import pushbullet_notify, pushover_notify, telegram_notify, gotify_notify

console = Console()

# Load environment variables
load_dotenv()

class Authenticator:
    def __init__(self, username, password):
        self.username = username
        self.password = password
        self.session = requests.Session()
        self.headers = {
            "User-Agent": UserAgent().random,
            "Accept": "application/json",
            "Authorization": None
        }
        self.tokenA = None

    def generate_code_challenge(self, input):
        sha256 = hashlib.sha256(input.encode("utf-8")).digest()
        return base64.urlsafe_b64encode(sha256).decode("utf-8").rstrip("=")

    def login(self):
        state = "".join(random.choices(string.ascii_lowercase + string.digits, k=32))
        device_id = str(uuid.uuid4())
        code_verifier = "".join(uuid.uuid4().hex for _ in range(3))
        code_challenge = self.generate_code_challenge(code_verifier)
        epoch_time = int(time.time()) * 1000

        login_url = "https://login-online24.medicover.pl"
        oidc_redirect = "https://online24.medicover.pl/signin-oidc"
        auth_params = (
            f"?client_id=web&redirect_uri={oidc_redirect}&response_type=code"
            f"&scope=openid+offline_access+profile&state={state}&code_challenge={code_challenge}"
            f"&code_challenge_method=S256&response_mode=query&ui_locales=pl&app_version=3.4.0-beta.1.0"
            f"&previous_app_version=3.4.0-beta.1.0&device_id={device_id}&device_name=Chrome&ts={epoch_time}"
        )

        # Step 1: Initialize login
        response = self.session.get(f"{login_url}/connect/authorize{auth_params}", headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")

        # Step 2: Extract CSRF token
        response = self.session.get(next_url, headers=self.headers, allow_redirects=False)
        soup = BeautifulSoup(response.content, "html.parser")
        csrf_input = soup.find("input", {"name": "__RequestVerificationToken"})
        if csrf_input:
            csrf_token = csrf_input.get("value")
        else:
            raise ValueError("CSRF token not found in the login page.")

        # Step 3: Submit login form
        login_data = {
            "Input.ReturnUrl": f"/connect/authorize/callback{auth_params}",
            "Input.LoginType": "FullLogin",
            "Input.Username": self.username,
            "Input.Password": self.password,
            "Input.Button": "login",
            "__RequestVerificationToken": csrf_token,
        }
        response = self.session.post(next_url, data=login_data, headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")

        # Step 4: Fetch authorization code
        response = self.session.get(f"{login_url}{next_url}", headers=self.headers, allow_redirects=False)
        next_url = response.headers.get("Location")
        code = parse_qs(urlparse(next_url).query)["code"][0]

        # Step 5: Exchange code for tokens
        token_data = {
            "grant_type": "authorization_code",
            "redirect_uri": oidc_redirect,
            "code": code,
            "code_verifier": code_verifier,
            "client_id": "web",
        }
        response = self.session.post(f"{login_url}/connect/token", data=token_data, headers=self.headers)
        tokens = response.json()
        self.tokenA = tokens["access_token"]
        self.headers["Authorization"] = f"Bearer {self.tokenA}"

class AppointmentFinder:
    def __init__(self, session, headers):
        self.session = session
        self.headers = headers

    def http_get(self, url, params):
        response = self.session.get(url, headers=self.headers, params=params)
        if response.status_code == 200:
            return response.json()
        else:
            console.print(
                f"[bold red]Error {response.status_code}[/bold red]: {response.text}"
            )
            return {}

    def find_appointments(self, region, specialty, clinic, start_date, end_date, language, search_type, doctor=None):
        appointment_url = "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/slots"
        params = {
            "RegionIds": region,
            "SpecialtyIds": specialty,
            "ClinicIds": clinic,
            "Page": 1,
            "PageSize": 5000,
            "StartTime": start_date.isoformat(),
            "SlotSearchType": search_type,
            "VisitType": "Center",
        }

        if language:
            params["DoctorLanguageIds"] = language

        if doctor:
            params["DoctorIds"] = doctor

        response = self.http_get(appointment_url, params)

        items = response.get("items", [])

        if end_date:
            items = [x for x in items if datetime.datetime.fromisoformat(x["appointmentDate"]).date() <= end_date]

        return items

    def find_filters(self, region=None, specialty=None):
        filters_url = "https://api-gateway-online24.medicover.pl/appointments/api/search-appointments/filters"

        params = {"SlotSearchType": 0}
        if region:
            params["RegionIds"] = region
        if specialty:
            params["SpecialtyIds"] = specialty

        response = self.http_get(filters_url, params)
        return response

class Notifier:
    def relative_day_label(date):
        """Return a human-friendly label like 'today', 'tomorrow', 'in 2 days', etc."""
        today = datetime.date.today()
        delta = (date - today).days

        if delta == 0:
            return "today"
        elif delta == 1:
            return "tomorrow"
        elif delta > 1:
            return f"in {delta} days"
        elif delta == -1:
            return "yesterday"
        else:
            return f"{abs(delta)} days ago"
    
    @staticmethod
    def format_appointments(appointments, stars=None):
        """Format appointments into a human-readable string."""
        if not appointments:
            return "No appointments found."

        grouped = defaultdict(list)

        for appointment in appointments:
            date_str = appointment.get("appointmentDate", "")
            try:
                dt = datetime.datetime.fromisoformat(date_str)
            except Exception:
                continue  # Skip invalid dates
            grouped[dt.date()].append(appointment)

        messages = []
        for date, items in sorted(grouped.items()):
            doctor_names = sorted(set(item.get("doctor", {}).get("name", "N/A") for item in items))
            doctor = ", ".join(doctor_names)
            clinic = items[0].get("clinic", {}).get("name", "N/A")
            specialty = items[0].get("specialty", {}).get("name", "N/A")
            count = len(items)
            star_visual = "★" * stars + "☆" * (3 - stars) if stars else "N/A"

            message = (
                    f"Date: {date.strftime('%d.%m.%Y')} ({Notifier.relative_day_label(date)})\n"
                    f"Doctor: {doctor}\n"
                    f"Specialty: {specialty}\n"
                    f"Clinic: {clinic}\n"
                    f"Appointments: {count} ({', '.join(sorted([datetime.datetime.fromisoformat(item.get('appointmentDate')).strftime('%H:%M') for item in items]))})\n"
                    f"Stars: {star_visual}\n"
                    + "-" * 25
            )
            messages.append(message)

        return "\n".join(messages)

    @staticmethod
    def send_notification(appointments, notifier, title, stars):
        """Send a notification with formatted appointments."""
        notifier = notifier.strip()
        message = Notifier.format_appointments(appointments, stars)
        if notifier == "pushbullet":
            pushbullet_notify(message, title)
        elif notifier == "pushover":
            pushover_notify(message, title)
        elif notifier == "telegram":
            telegram_notify(message, title)
        elif notifier == "gotify":
            gotify_notify(message, title)


def display_appointments(appointments):
    console.print()
    console.print("-" * 50)
    if not appointments:
        console.print("No new appointments found.")
    else:
        console.print("New appointments found:")
        console.print("-" * 50)
        for appointment in appointments:
            date = appointment.get("appointmentDate", "N/A")
            clinic = appointment.get("clinic", {}).get("name", "N/A")
            doctor = appointment.get("doctor", {}).get("name", "N/A")
            specialty = appointment.get("specialty", {}).get("name", "N/A")
            doctor_languages = appointment.get("doctorLanguages", [])
            languages = ", ".join([lang.get("name", "N/A") for lang in doctor_languages]) if doctor_languages else "N/A"
            console.print(f"Date: {date}")
            console.print(f"  Clinic: {clinic}")
            console.print(f"  Doctor: {doctor}")
            console.print(f"  Specialty: {specialty}")
            console.print(f"  Languages: {languages}")
            console.print("-" * 50)

def exclude_today_only(appointments):
    """Return True if all appointments are for today (i.e., nothing beyond today)."""
    today = datetime.date.today()
    for appt in appointments:
        try:
            date = datetime.datetime.fromisoformat(appt.get("appointmentDate", "")).date()
            if date != today:
                return False
        except Exception:
            continue
    return True

def main():
    parser = argparse.ArgumentParser(description="Find appointment slots.")
    subparsers = parser.add_subparsers(dest="command", required=True, help="Command to execute")

    find_appointment = subparsers.add_parser("find-appointment", help="Find appointment")
    find_appointment.add_argument("-r", "--region", required=False, type=int, help="Region ID")
    find_appointment.add_argument("-s", "--specialty", required=False, type=int, action="extend", nargs="+", help="Specialty ID",)
    find_appointment.add_argument("-c", "--clinic", required=False, type=int, help="Clinic ID")
    find_appointment.add_argument("-d", "--doctor", required=False, type=int, help="Doctor ID")
    find_appointment.add_argument("-f", "--date", type=datetime.date.fromisoformat, default=datetime.date.today(), help="Start date in YYYY-MM-DD format")
    find_appointment.add_argument("-e", "--enddate", type=datetime.date.fromisoformat, help="End date in YYYY-MM-DD format")
    find_appointment.add_argument("-n", "--notification", required=False, help="Notification method")
    find_appointment.add_argument("-t", "--title", required=False, help="Notification title")
    find_appointment.add_argument("-l", "--language", required=False, type=int, help="4=Polski, 6=Angielski, 60=Ukraiński")
    find_appointment.add_argument("-i", "--interval", required=False, type=int, help="Repeat interval in minutes")
    find_appointment.add_argument("--stars", type=int,  required=False, help="Preferred doctor rating (1 to 3 stars)")
    find_appointment.add_argument("--exclude-today", action="store_true", help="Skip displaying appointments that are only for today",)

    list_filters = subparsers.add_parser("list-filters", help="List filters")
    list_filters_subparsers = list_filters.add_subparsers(dest="filter_type", required=True, help="Type of filter to list")

    regions = list_filters_subparsers.add_parser("regions", help="List available regions")
    specialties = list_filters_subparsers.add_parser("specialties", help="List available specialties")
    doctors = list_filters_subparsers.add_parser("doctors", help="List available doctors")
    doctors.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    doctors.add_argument("-s", "--specialty", required=True, type=int, help="Specialty ID")
    clinics = list_filters_subparsers.add_parser("clinics", help="List available clinics")
    clinics.add_argument("-r", "--region", required=True, type=int, help="Region ID")
    clinics.add_argument("-s", "--specialty", required=True, type=int, nargs="+", help="Specialty ID(s)")


    args = parser.parse_args()

    username = os.environ.get("MEDICOVER_USER")
    password = os.environ.get("MEDICOVER_PASS")

    if not username or not password:
        console.print("[bold red]Error:[/bold red] MEDICOVER_USER and MEDICOVER_PASS environment variables must be set.")
        exit(1)

    docker_path = '/app/shared'
    filename_doctors = f'{docker_path}/doctor_data.json'
    params_file = f'{docker_path}/params.csv'
    #filename_doctors = 'doctor_data.json'
    #params_file = 'params.csv'
    count_times = 0
    while True:
        # Authenticate
        auth = Authenticator(username, password)
        auth.login()
    
        finder = AppointmentFinder(auth.session, auth.headers)

        if args.command == "find-appointment":
            if os.path.exists(params_file) and os.path.getsize(params_file) > 0:
                with open(params_file, "r", newline="") as f:
                    reader = csv.DictReader(f)
                    params_from_file = list(reader)
            else:
                params_from_file = []

            for param in params_from_file:
                if param['run'] == "no":
                    continue

                args.region = 202
                args.specialty = int(param['service_id'])
                args.doctor = int(param['doctor_id'])
                args.star = int(param['stars'])
                args.notification = 'telegram'

                # Find appointments
                if args.specialty == [519]:
                    search_type = "DiagnosticProcedure"
                else:
                    search_type = 0
                appointments = finder.find_appointments(args.region, args.specialty, args.clinic, args.date, args.enddate, args.language, search_type, args.doctor)
                filtered_appointments = []

                #Read file with reminders of appointments
                if os.path.exists(filename_doctors) and os.path.getsize(filename_doctors) > 0:
                    with open(filename_doctors, "r") as f:
                        doctors_from_file = json.load(f)
                else:
                    doctors_from_file = {}

                #Filter appointments
                for appt in appointments:
                    doctor_id = appt['doctor']['id']
                    app_date =  appt['appointmentDate']

                    if doctor_id not in doctors_from_file:
                        doctors_from_file[doctor_id] = []

                    # Look for matching appointment date
                    for existing_appt in doctors_from_file[doctor_id]:
                        if existing_appt["appointmentDate"] == app_date:
                            existing_appt["reminderCount"] += 1
                            if existing_appt["reminderCount"] <= 3:
                                filtered_appointments.append(appt)
                            break
                    else:
                        # No existing appointment found, add new one
                        doctors_from_file[doctor_id].append({
                            "appointmentDate": app_date,
                            "reminderCount": 1
                        })
                        filtered_appointments.append(appt)

                #Save file with reminders of appointments
                with open(filename_doctors, "w") as f:
                    json.dump(doctors_from_file, f, indent=4)

                # Display appointments
                display_appointments(filtered_appointments)
                console.print(f"All appointments: {len(appointments)}")
                console.print(f"Filtered appointments: {len(filtered_appointments)}")

                # Send notification if appointments are found
                if filtered_appointments and (
                        not args.exclude_today or not exclude_today_only(filtered_appointments)):
                    Notifier.send_notification(filtered_appointments, args.notification, args.title, stars=args.stars)

            if count_times <= 3:
                time.sleep(60)
                count_times += 1
                continue
    
        elif args.command == "list-filters":
    
            if args.filter_type in ("doctors", "clinics"):
                filters = finder.find_filters(args.region, args.specialty)
            else:
                filters = finder.find_filters()

    
            for r in filters[args.filter_type]:
                print(f"{r['id']} - {r['value']}")


        break

if __name__ == "__main__":
    main()
