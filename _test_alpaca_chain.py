import os
from dotenv import load_dotenv
load_dotenv()
from engine.config import API_KEY, API_SECRET, PAPER
print(f"Key: {API_KEY[:6]}..." if API_KEY else "No key")
print(f"Secret: {API_SECRET[:6]}..." if API_SECRET else "No secret")
