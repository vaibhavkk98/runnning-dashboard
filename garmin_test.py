import os
import streamlit as st
from garminconnect import Garmin
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

st.set_page_config(page_title="Garmin 5K Running Dashboard", page_icon="🏃", layout="wide")

st.title("🏃 Garmin 5K Dashboard - Forerunner 165")
st.subheader("Target Pace: 7:00 min/km")

email = os.getenv("GARMIN_EMAIL")
password = os.getenv("GARMIN_PASSWORD")

if not email or not password or email == "your_email@example.com":
    st.warning("Please configure your GARMIN_EMAIL and GARMIN_PASSWORD in the `.env` file.")
else:
    st.success("Credentials detected. Ready to connect to Garmin!")
