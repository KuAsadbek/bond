import requests
import json

BASE_URL = "http://localhost:8000/api"

def test_login_fail():
    print("Testing login with wrong credentials...")
    url = f"{BASE_URL}/login/"
    data = {
        "phone_number": "998905577511",
        "password": "wrong_password"
    }
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

def test_send_code_exists():
    print("\nTesting send-code for existing number...")
    url = f"{BASE_URL}/send-code/"
    data = {
        "phone_number": "998905577511"
    }
    response = requests.post(url, json=data)
    print(f"Status: {response.status_code}")
    print(f"Response: {response.json()}")

if __name__ == "__main__":
    try:
        test_login_fail()
        test_send_code_exists()
    except Exception as e:
        print(f"Error: {e}")
